"""Demand-vs-capacity warning at known bottlenecks (Phase 4, fourth pass).

A jam forms where more people arrive than a narrow stretch can pass. For each bottleneck
in config/sim.json -> warning.bottleneck.sites (taken from the map: roads joining into a
narrower one), count the unique phones seen inside circles on the feeding roads over the
last window_s. Demand = unique phones / window / phone share. Capacity = width x
capacity.specific_flow_pms. Alarm when demand - capacity >= sigmas standard errors
(sqrt of the phone count, scaled the same way) for hold_s.

Scored with warn.score like the other rules (alarm placed in the bottleneck's zone), on the
same training and holdout runs, with the go criteria in warning.go. Unique phones slightly
undercount flow (a phone whose few pings in the circle are all lost is missed), which errs
towards a later warning.

Writes out/<name>/results.json and bottleneck.png.
"""
import argparse
import itertools
import json
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import config
from pings import Run, draw
from rules import SHARES, verdict
from warn import CFG, ROOT, W, Truth, density_error, estimate, first_held, score, summarise

B = W["bottleneck"]
GO = W["go"]
FEEDERS = list(B["sites"][0]["feeders"])


def demand(truth, pings, site, window, where):
    """Per eval time: estimated demand (people/min) and its standard error."""
    t, ph = pings["t"], pings["phone"]
    xy = np.column_stack([pings["x"], pings["y"]])
    inside = np.zeros(len(t), bool)
    for f in site["feeders"][where]:
        inside |= np.hypot(*(xy - f).T) <= site["radius_m"]
    t, ph = t[inside], ph[inside]
    d = np.zeros(len(truth.times))
    se = np.zeros(len(truth.times))
    for n, now in enumerate(truth.times):
        a, b = np.searchsorted(t, [now - window, now], side="right")
        k = len(np.unique(ph[a:b]))
        d[n] = k / pings["share"] / (window / 60)
        se[n] = np.sqrt(max(k, 1)) / pings["share"] / (window / 60)
    return d, se


def evaluate(name, draws, zone_m, log):
    run = Run(name)
    truth = Truth(run, zone_m)
    nz = len(truth.area)
    rows = []

    def score_all(p, tag):
        dens, _, _ = estimate(truth, p)
        err = density_error(truth, dens)
        for window, where in itertools.product(B["window_s"], FEEDERS):
            per_site = [(site, *demand(truth, p, site, window, where)) for site in B["sites"]]
            for k, hold in itertools.product(B["sigmas"], B["hold_s"]):
                cond = np.zeros((len(truth.times), nz), bool)
                for site, d, se in per_site:
                    cap = config.capacity_ppm(site["width_m"], CFG)
                    z = truth.zone_of(np.array([site["xy"]], float))[0]
                    cond[:, z] |= d - cap >= k * se
                first = first_held(truth, cond, hold)
                rows.append({**tag, "run": name, "zone_m": zone_m, "feeders": where, "window_s": window, "sigmas": k,
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
        keys.setdefault((r["run"], r["share"], r["feeders"], r["window_s"], r["sigmas"], r["hold_s"]), []).append(r)
    return [{"run": k[0], "share": k[1], "rule": {"feeders": k[2], "window_s": k[3], "sigmas": k[4], "hold_s": k[5]},
             "draws": len(rs),
             "lead_min": summarise([r["lead_min"] for r in rs]),
             "lead_ok_share": float(np.mean([(r["lead_min"] or -1e9) >= GO["lead_min"] for r in rs])),
             "warned_share": float(np.mean([r["lead_min"] is not None for r in rs])),
             "false_alarms_per_hour": summarise([r["false_alarm_zones"] / r["hours"] for r in rs]),
             "any_false_alarm_share": float(np.mean([r["false_alarm_zones"] > 0 for r in rs])),
             "density_error": summarise([r["density_error"] for r in rs])} for k, rs in keys.items()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", nargs=2, default=["oneway_in1000", "calm_in500"], metavar=("JAM", "CALM"))
    ap.add_argument("--test", nargs=2, default=["holdout_jam", "holdout_calm"], metavar=("JAM", "CALM"))
    ap.add_argument("--draws", type=int, default=20)
    ap.add_argument("--zone", type=int, default=20)
    ap.add_argument("--name", default="phase4_bottleneck")
    args = ap.parse_args()
    out = ROOT / "out" / args.name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)

    rows = []
    for name in dict.fromkeys(args.train + args.test):
        rows += evaluate(name, args.draws, args.zone, log)
    S = summary(rows)
    find = lambda run, share, rule: next(s for s in S if s["run"] == run and s["share"] == share and s["rule"] == rule)
    (tj, tc), (hj, hc) = args.train, args.test
    grid = [dict(zip(("feeders", "window_s", "sigmas", "hold_s"), v))
            for v in itertools.product(FEEDERS, B["window_s"], B["sigmas"], B["hold_s"])]
    cands = [{"rule": r, "train_jam": find(tj, GO["phone_share"], r), "train_calm": find(tc, GO["phone_share"], r)}
             for r in grid]
    for c in cands:
        c["train_verdict"] = verdict(c["train_jam"], c["train_calm"])
    passing = [c for c in cands if c["train_verdict"]["false_alarms_ok"]]
    ranked = sorted(passing, key=lambda c: (c["train_jam"]["lead_ok_share"],
                                            c["train_jam"]["lead_min"]["median"] or -99), reverse=True)
    chosen = ranked[0] if ranked else None
    report = {"go": GO, "bottleneck": B, "capacity_ppm": [config.capacity_ppm(s["width_m"], CFG) for s in B["sites"]],
              "train": args.train, "test": args.test, "draws": args.draws, "zone_m": args.zone}
    if chosen:
        r = chosen["rule"]
        report["chosen"] = {"rule": r, "train_verdict": chosen["train_verdict"], "by_share": {}}
        for share in SHARES + ["oracle"]:
            res = {k: find(run, share, r) for k, run in
                   [("train_jam", tj), ("train_calm", tc), ("test_jam", hj), ("test_calm", hc)]}
            res["test_verdict"] = verdict(res["test_jam"], res["test_calm"])
            report["chosen"]["by_share"][str(share)] = res
    (out / "results.json").write_text(json.dumps({"report": report, "summary": S}, indent=1))

    # Estimated demand over time at 2% phones (one draw) against capacity, for each jam run.
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
    site = B["sites"][0]
    cap = config.capacity_ppm(site["width_m"], CFG)
    for ax, name in zip(axs, [tj, hj]):
        run = Run(name)
        truth = Truth(run, args.zone)
        for where, c in zip(FEEDERS, ["C0", "C2"]):
            for share in [1.0, GO["phone_share"]]:
                for _, _, p in draw(run, [share], 15 if share < 1 else 10, [10 if share < 1 else 0], seed=7000):
                    d, se = demand(truth, p, site, 180, where)
                    ax.plot(truth.times / 60, d, color=c, lw=2.5 if share == 1 else 1, alpha=0.5 if share == 1 else 1,
                            label=f"{where}: " + ("everyone" if share == 1 else f"{share:.0%} phones"))
                    if share < 1:
                        ax.fill_between(truth.times / 60, d - se, d + se, color=c, alpha=0.15)
        z = truth.zone_of(np.array([site["xy"]], float))[0]
        onset = truth.onset[truth.near[z]].min()
        ax.axhline(cap, color="red", ls="--", label=f"capacity {cap:.0f}/min")
        ax.axvline(onset / 60, color="orange", ls=":", label="first ≥ 4/m² (event)")
        ax.set_title(f"{name}: demand into {site['name']} (3 min window)")
        ax.set_xlabel("minutes"); ax.legend(fontsize=8)
    axs[0].set_ylabel("people per minute")
    fig.tight_layout(); fig.savefig(out / "bottleneck.png", dpi=100); plt.close(fig)
    print(json.dumps({k: v for k, v in report.items() if k not in ("go", "bottleneck")}, indent=1)[:5000])
    log(f"wrote {out / 'results.json'}")


if __name__ == "__main__":
    main()
