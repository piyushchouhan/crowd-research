"""Smarter warning rules for sparse phone pings (Phase 4, second pass).

Each rule = base condition (count or trend, from warn.py) estimated over window_s,
+ held for hold_s, + optionally at least one neighbouring zone meeting it too,
+ optionally phones slowing (median speed over the zone and its neighbours < slow_mps).
Grid in config/sim.json -> warning.rules; pass/fail in warning.go.

Protocol: score every rule on the training runs (one jam, one calm day), pick the rule
that passes the false-alarm limit at go.phone_share with the most draws warned
>= go.lead_min ahead, then report that rule unchanged on the holdout runs.

Writes out/<name>/results.json and rules.png.
"""
import argparse
import itertools
import json
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from pings import Run, draw
from warn import ROOT, W, Truth, base_conditions, density_error, estimate, first_held, score, summarise

R = W["rules"]
GO = W["go"]
SHARES = [0.01, 0.02, 0.05]


def rules():
    for base, window, hold, nb, slow in itertools.product(R["base"], R["window_s"], R["hold_s"],
                                                          R["neighbour"], R["slow_mps"]):
        yield {"base": base, "window_s": window, "hold_s": hold, "neighbour": nb, "slow_mps": slow}


def label(r):
    return (f"{r['base']} {r['window_s']}s win, hold {r['hold_s']}s"
            + (", +neighbour" if r["neighbour"] else "") + (f", +slow<{r['slow_mps']}" if r["slow_mps"] else ""))


def with_neighbour(truth, cond):
    """cond and at least one of the 8 neighbouring zones meeting cond at the same time."""
    g = cond.reshape(len(cond), truth.zy, truth.zx)
    p = np.pad(g, ((0, 0), (1, 1), (1, 1)))
    n = sum(p[:, 1 + dj:1 + dj + truth.zy, 1 + di:1 + di + truth.zx]
            for dj in (-1, 0, 1) for di in (-1, 0, 1) if dj or di)
    return (g & (n > 0)).reshape(cond.shape)


def score_rules(run, truths, p, zone_rows):
    """All rules for one set of pings, every zone size."""
    rows = []
    for zone_m, truth in truths.items():
        for window in R["window_s"]:
            dens, _, speed_nb = estimate(truth, p, window)
            err = density_error(truth, dens)
            base = base_conditions(truth, dens)
            slow = {s: np.nan_to_num(speed_nb, nan=np.inf) < s for s in R["slow_mps"] if s}
            for r in rules():
                if r["window_s"] != window:
                    continue
                c = base[r["base"]]
                if r["neighbour"]:
                    c = with_neighbour(truth, c)
                if r["slow_mps"]:
                    c = c & slow[r["slow_mps"]]
                first = first_held(truth, c, r["hold_s"])
                rows.append({**zone_rows, "zone_m": zone_m, **r, "density_error": err,
                             "hours": run.seconds / 3600, **score(truth, dens, first)})
    return rows


def evaluate(name, draws, zones, log):
    run = Run(name)
    truths, cell_first = {}, None
    for zone_m in zones:
        truths[zone_m] = Truth(run, zone_m, cell_first)
        cell_first = truths[zone_m].cell_first
    rows = []
    for _, _, p in draw(run, [1.0], 10, [0.0], seed=0):
        rows += score_rules(run, truths, p, {"run": name, "share": "oracle", "draw": 0})
    for d in range(draws):
        for share, _, p in draw(run, SHARES, 15, [10], seed=7000 + d):
            rows += score_rules(run, truths, p, {"run": name, "share": share, "draw": d})
        log(f"{name}: draw {d + 1}/{draws}")
    return rows


def summary(rows):
    keys = {}
    for r in rows:
        k = (r["run"], r["share"], r["zone_m"], r["base"], r["window_s"], r["hold_s"], r["neighbour"], r["slow_mps"])
        keys.setdefault(k, []).append(r)
    out = []
    for k, rs in keys.items():
        out.append({"run": k[0], "share": k[1], "zone_m": k[2],
                    "rule": {"base": k[3], "window_s": k[4], "hold_s": k[5], "neighbour": k[6], "slow_mps": k[7]},
                    "draws": len(rs),
                    "lead_min": summarise([r["lead_min"] for r in rs]),
                    "lead_ok_share": float(np.mean([(r["lead_min"] or -1e9) >= GO["lead_min"] for r in rs])),
                    "warned_share": float(np.mean([r["lead_min"] is not None for r in rs])),
                    "false_alarms_per_hour": summarise([r["false_alarm_zones"] / r["hours"] for r in rs]),
                    "density_error": summarise([r["density_error"] for r in rs])})
    return out


def verdict(jam, calm):
    return {"density_ok": jam["density_error"]["median"] is not None
            and jam["density_error"]["median"] <= GO["density_error"],
            "lead_ok": jam["lead_ok_share"] >= GO["lead_ok_share"],
            "false_alarms_ok": calm["false_alarms_per_hour"]["median"] <= GO["false_alarms_per_hour"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", nargs=2, default=["oneway_in1000", "calm_in500"], metavar=("JAM", "CALM"))
    ap.add_argument("--test", nargs=2, default=["holdout_jam", "holdout_calm"], metavar=("JAM", "CALM"))
    ap.add_argument("--draws", type=int, default=20)
    ap.add_argument("--zones", type=int, nargs="*", default=[20, 32])
    ap.add_argument("--name", default="phase4_rules")
    args = ap.parse_args()
    out = ROOT / "out" / args.name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)

    rows = []
    for name in args.train + args.test:
        rows += evaluate(name, args.draws, args.zones, log)
    S = summary(rows)
    find = lambda run, share, zone_m, rule: next(s for s in S if s["run"] == run and s["share"] == share
                                                 and s["zone_m"] == zone_m and s["rule"] == rule)

    # Choose on the training runs at the go share.
    (tj, tc), (hj, hc) = args.train, args.test
    cands = []
    for zone_m in args.zones:
        for r in rules():
            jam, calm = find(tj, GO["phone_share"], zone_m, r), find(tc, GO["phone_share"], zone_m, r)
            cands.append({"zone_m": zone_m, "rule": r, "train_jam": jam, "train_calm": calm,
                          "train_verdict": verdict(jam, calm)})
    passing = [c for c in cands if c["train_verdict"]["false_alarms_ok"]]
    key = lambda c: (c["train_jam"]["lead_ok_share"], c["train_jam"]["lead_min"]["median"] or -99)
    ranked = sorted(passing, key=key, reverse=True)
    chosen = ranked[0] if ranked else None
    report = {"go": GO, "rules_grid": R, "train": args.train, "test": args.test, "draws": args.draws,
              "n_rules": len(cands), "n_pass_false_alarms": len(passing)}
    if chosen:
        z, r = chosen["zone_m"], chosen["rule"]
        report["chosen"] = {"zone_m": z, "rule": r, "label": label(r), "train_verdict": chosen["train_verdict"],
                            "by_share": {}}
        for share in SHARES + ["oracle"]:
            res = {k: find(run, share, z, r) for k, run in
                   [("train_jam", tj), ("train_calm", tc), ("test_jam", hj), ("test_calm", hc)]}
            res["test_verdict"] = verdict(res["test_jam"], res["test_calm"])
            report["chosen"]["by_share"][str(share)] = res
        report["top10_train"] = [{"zone_m": c["zone_m"], "label": label(c["rule"]),
                                  "lead_ok_share": c["train_jam"]["lead_ok_share"],
                                  "lead_min": c["train_jam"]["lead_min"]["median"],
                                  "false_alarms_per_hour": c["train_calm"]["false_alarms_per_hour"]["median"]}
                                 for c in ranked[:10]]
    (out / "results.json").write_text(json.dumps({"report": report, "summary": S}, indent=1))

    # Every rule at the go share: false alarms on the calm day vs share of draws warned in time.
    fig, axs = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for ax, (jam_run, calm_run, title) in zip(axs, [(tj, tc, "training runs"), (hj, hc, "holdout runs")]):
        for c in cands:
            jam = find(jam_run, GO["phone_share"], c["zone_m"], c["rule"])
            calm = find(calm_run, GO["phone_share"], c["zone_m"], c["rule"])
            is_chosen = chosen and c["zone_m"] == chosen["zone_m"] and c["rule"] == chosen["rule"]
            ax.scatter(max(calm["false_alarms_per_hour"]["median"], 0.1), jam["lead_ok_share"],
                       s=80 if is_chosen else 18, c="red" if is_chosen else
                       ("C0" if c["rule"]["base"] == "count" else "C2"), alpha=0.9 if is_chosen else 0.5,
                       marker="*" if is_chosen else ("o" if c["zone_m"] == 20 else "s"))
        ax.axvline(GO["false_alarms_per_hour"], color="red", ls=":", lw=0.8)
        ax.axhline(GO["lead_ok_share"], color="red", ls=":", lw=0.8)
        ax.set_xscale("log")
        ax.set_xlabel("false alarms per hour on the calm day (median zones; 0 shown at 0.1)")
        ax.set_title(f"{title}: {jam_run} / {calm_run}")
    axs[0].set_ylabel(f"share of draws warned ≥ {GO['lead_min']} min before the first jam")
    fig.suptitle(f"{len(cands)} rules at {GO['phone_share']:.0%} phones (blue count, green trend; "
                 f"circle 20 m, square 32 m zones; red star = chosen on training)")
    fig.tight_layout(); fig.savefig(out / "rules.png", dpi=100); plt.close(fig)

    print(json.dumps({k: v for k, v in report.items() if k not in ("rules_grid", "go")}, indent=1)[:6000])
    log(f"wrote {out / 'results.json'}")


if __name__ == "__main__":
    main()
