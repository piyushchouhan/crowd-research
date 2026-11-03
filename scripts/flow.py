"""Flow-based warning from sparse phone pings (Phase 4, third pass).

Instead of how many people are in a place (density), watch whether people enter a place
faster than they leave it. Block = a zone and its 8 neighbours. From consecutive pings of
each phone, count crossings into and out of every block over the last window_s:
- a phone's first ping counts as entering, its track ending as leaving
  (bathers leave the simulation at the goal; in reality they would stay or walk on);
- surplus = in - out, scaled by 1 / phone share.
Alarm when (all held for hold_s):
- the surplus is beyond chance: in - out >= sigmas * sqrt(in + out) (phone counts);
- at the current surplus rate the block reaches dense_ppm2 within forecast_min,
  starting from the count estimate of the people in it now.
No map or road network is needed. Settings in config/sim.json -> warning.flow; pass/fail
in warning.go; same protocol as rules.py (choose on training runs, check on holdout runs).

Writes out/<name>/results.json and flow.png.
"""
import argparse
import itertools
import json
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from pings import P, Run, draw
from rules import SHARES, verdict
from warn import DENSE, ROOT, W, Truth, density_error, estimate, first_held, score, summarise

F = W["flow"]
GO = W["go"]


def block_sum(truth, a):
    """Sum of a (time x zones) over each zone and its 8 neighbours."""
    g = a.reshape(len(a), truth.zy, truth.zx)
    p = np.pad(g, ((0, 0), (1, 1), (1, 1)))
    s = sum(p[:, 1 + dj:1 + dj + truth.zy, 1 + di:1 + di + truth.zx] for dj in (-1, 0, 1) for di in (-1, 0, 1))
    return s.reshape(a.shape)


def crossings(truth, pings, end_s):
    """Times and blocks of phones entering (+1) and leaving (-1) each block."""
    t, ph = pings["t"], pings["phone"]
    zone = truth.zone_of(np.column_stack([pings["x"], pings["y"]]))
    o = np.lexsort((t, ph))
    t, ph, zone = t[o], ph[o], zone[o]
    new = np.r_[True, ph[1:] != ph[:-1]]
    last = np.r_[new[1:], True]
    zj, zi = zone // truth.zx, zone % truth.zx
    times, blocks, signs = [], [], []

    def emit(mask, tt, fj, fi, other_j, other_i, sign):
        # Blocks around (fj, fi) that do not contain (other_j, other_i); other = None for all.
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                bj, bi = fj + dj, fi + di
                m = mask & (bj >= 0) & (bj < truth.zy) & (bi >= 0) & (bi < truth.zx)
                if other_j is not None:
                    m &= (np.abs(bj - other_j) > 1) | (np.abs(bi - other_i) > 1)
                times.append(tt[m]); blocks.append(bj[m] * truth.zx + bi[m]); signs.append(np.full(m.sum(), sign))

    # Appearing and disappearing phones.
    emit(new, t, zj, zi, None, None, 1)
    gone = last & (t < end_s - 2 * pings["interval"])
    emit(gone, t + pings["interval"], zj, zi, None, None, -1)
    # Moves between consecutive pings of the same phone.
    move = ~new
    pj, pi = np.r_[0, zj[:-1]], np.r_[0, zi[:-1]]
    emit(move, t, zj, zi, pj, pi, 1)       # entering blocks around the new zone
    emit(move, t, pj, pi, zj, zi, -1)      # leaving blocks around the old zone
    return np.concatenate(times), np.concatenate(blocks), np.concatenate(signs)


def flow_conditions(truth, pings, dens, end_s):
    """Per window, sigmas: alarm condition (time x zones) before holding."""
    ct, cb, cs = crossings(truth, pings, end_s)
    order = np.argsort(ct, kind="stable")
    ct, cb, cs = ct[order], cb[order], cs[order]
    nz = len(truth.area)
    scale = 1 / (pings["share"] * (1 - P["dropout_frac"]))
    area = block_sum(truth, truth.area[None])[0]
    people = block_sum(truth, dens * truth.area[None])           # estimated people in each block
    room = np.maximum(DENSE * area - people, 0)
    out = {}
    for window in F["window_s"]:
        n_in = np.zeros((len(truth.times), nz))
        n_out = np.zeros((len(truth.times), nz))
        for n, now in enumerate(truth.times):
            a, b = np.searchsorted(ct, [now - window, now], side="right")
            n_in[n] = np.bincount(cb[a:b][cs[a:b] > 0], minlength=nz)
            n_out[n] = np.bincount(cb[a:b][cs[a:b] < 0], minlength=nz)
        surplus = n_in - n_out
        rate = surplus * scale / (window / 60)                    # people per minute
        soon = (rate > 0) & (room <= rate * F["forecast_min"])
        for k in F["sigmas"]:
            cond = (surplus >= k * np.sqrt(n_in + n_out)) & (surplus > 0) & soon
            out[(window, k)] = cond & truth.valid
    return out


def evaluate(name, draws, zones, log):
    run = Run(name)
    truths, cell_first = {}, None
    for zone_m in zones:
        truths[zone_m] = Truth(run, zone_m, cell_first)
        cell_first = truths[zone_m].cell_first
    rows = []

    def score_all(p, tag):
        for zone_m, truth in truths.items():
            dens, _, _ = estimate(truth, p)
            err = density_error(truth, dens)
            conds = flow_conditions(truth, p, dens, run.seconds)
            for (window, k), cond in conds.items():
                for hold in F["hold_s"]:
                    first = first_held(truth, cond, hold)
                    rows.append({**tag, "run": name, "zone_m": zone_m, "window_s": window, "sigmas": k,
                                 "hold_s": hold, "density_error": err, "hours": run.seconds / 3600,
                                 **score(truth, dens, first)})

    for _, _, p in draw(run, [1.0], 10, [0.0], seed=0):
        score_all(p, {"share": "oracle", "draw": 0})
    for d in range(draws):
        for share, _, p in draw(run, SHARES, 15, [10], seed=7000 + d):
            score_all(p, {"share": share, "draw": d})
        log(f"{name}: draw {d + 1}/{draws}")
    return rows


def summary(rows):
    keys = {}
    for r in rows:
        keys.setdefault((r["run"], r["share"], r["zone_m"], r["window_s"], r["sigmas"], r["hold_s"]), []).append(r)
    return [{"run": k[0], "share": k[1], "zone_m": k[2],
             "rule": {"window_s": k[3], "sigmas": k[4], "hold_s": k[5]}, "draws": len(rs),
             "lead_min": summarise([r["lead_min"] for r in rs]),
             "lead_ok_share": float(np.mean([(r["lead_min"] or -1e9) >= GO["lead_min"] for r in rs])),
             "warned_share": float(np.mean([r["lead_min"] is not None for r in rs])),
             "false_alarms_per_hour": summarise([r["false_alarm_zones"] / r["hours"] for r in rs]),
             "density_error": summarise([r["density_error"] for r in rs])} for k, rs in keys.items()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", nargs=2, default=["oneway_in1000", "calm_in500"], metavar=("JAM", "CALM"))
    ap.add_argument("--test", nargs=2, default=["holdout_jam", "holdout_calm"], metavar=("JAM", "CALM"))
    ap.add_argument("--draws", type=int, default=20)
    ap.add_argument("--zones", type=int, nargs="*", default=[20, 32])
    ap.add_argument("--name", default="phase4_flow")
    args = ap.parse_args()
    out = ROOT / "out" / args.name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)

    rows = []
    for name in dict.fromkeys(args.train + args.test):
        rows += evaluate(name, args.draws, args.zones, log)
    S = summary(rows)
    find = lambda run, share, zone_m, rule: next(s for s in S if s["run"] == run and s["share"] == share
                                                 and s["zone_m"] == zone_m and s["rule"] == rule)
    (tj, tc), (hj, hc) = args.train, args.test
    grid = [dict(zip(("window_s", "sigmas", "hold_s"), v))
            for v in itertools.product(F["window_s"], F["sigmas"], F["hold_s"])]
    cands = [{"zone_m": z, "rule": r, "train_jam": find(tj, GO["phone_share"], z, r),
              "train_calm": find(tc, GO["phone_share"], z, r)} for z in args.zones for r in grid]
    for c in cands:
        c["train_verdict"] = verdict(c["train_jam"], c["train_calm"])
    passing = [c for c in cands if c["train_verdict"]["false_alarms_ok"]]
    ranked = sorted(passing, key=lambda c: (c["train_jam"]["lead_ok_share"],
                                            c["train_jam"]["lead_min"]["median"] or -99), reverse=True)
    report = {"go": GO, "flow": F, "train": args.train, "test": args.test, "draws": args.draws,
              "n_rules": len(cands), "n_pass_false_alarms": len(passing)}
    chosen = ranked[0] if ranked else None
    if chosen:
        z, r = chosen["zone_m"], chosen["rule"]
        report["chosen"] = {"zone_m": z, "rule": r, "train_verdict": chosen["train_verdict"], "by_share": {}}
        for share in SHARES + ["oracle"]:
            res = {k: find(run, share, z, r) for k, run in
                   [("train_jam", tj), ("train_calm", tc), ("test_jam", hj), ("test_calm", hc)]}
            res["test_verdict"] = verdict(res["test_jam"], res["test_calm"])
            report["chosen"]["by_share"][str(share)] = res
    report["all_at_go_share"] = [
        {"zone_m": c["zone_m"], **c["rule"],
         "train": [c["train_jam"]["lead_min"]["median"], c["train_jam"]["lead_ok_share"],
                   c["train_calm"]["false_alarms_per_hour"]["median"]],
         "test": [find(hj, GO["phone_share"], c["zone_m"], c["rule"])["lead_min"]["median"],
                  find(hj, GO["phone_share"], c["zone_m"], c["rule"])["lead_ok_share"],
                  find(hc, GO["phone_share"], c["zone_m"], c["rule"])["false_alarms_per_hour"]["median"]]}
        for c in cands]
    (out / "results.json").write_text(json.dumps({"report": report, "summary": S}, indent=1))

    fig, axs = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, (jam_run, calm_run, title) in zip(axs, [(tj, tc, "training runs"), (hj, hc, "holdout runs")]):
        for share, c in zip(SHARES, ["C1", "C0", "C2"]):
            for cand in cands:
                jam, calm = find(jam_run, share, cand["zone_m"], cand["rule"]), find(calm_run, share, cand["zone_m"], cand["rule"])
                is_chosen = chosen and cand["zone_m"] == chosen["zone_m"] and cand["rule"] == chosen["rule"]
                ax.scatter(max(calm["false_alarms_per_hour"]["median"], 0.1), jam["lead_ok_share"], c=c,
                           s=90 if is_chosen else 20, marker="*" if is_chosen else
                           ("o" if cand["zone_m"] == 20 else "s"), alpha=0.6,
                           edgecolors="k" if is_chosen else "none",
                           label=f"{share:.0%} phones" if cand is cands[0] else None)
        ax.axvline(GO["false_alarms_per_hour"], color="red", ls=":", lw=0.8)
        ax.axhline(GO["lead_ok_share"], color="red", ls=":", lw=0.8)
        ax.set_xscale("log"); ax.legend(fontsize=8)
        ax.set_xlabel("false alarms per hour on the calm day (median; 0 shown at 0.1)")
        ax.set_title(f"{title}: {jam_run} / {calm_run}")
    axs[0].set_ylabel(f"share of draws warned ≥ {GO['lead_min']} min before the first jam")
    fig.suptitle(f"Flow warning, {len(cands)} settings (circle 20 m, square 32 m zones; star = chosen on training at "
                 f"{GO['phone_share']:.0%})")
    fig.tight_layout(); fig.savefig(out / "flow.png", dpi=100); plt.close(fig)
    print(json.dumps({k: v for k, v in report.items() if k not in ("go", "flow", "all_at_go_share")}, indent=1)[:5000])
    log(f"wrote {out / 'results.json'}")


if __name__ == "__main__":
    main()
