"""Let the phones learn a bottleneck's capacity, then test the warning (Phase 4).

Learning, from phones only (no simulation truth), over a history of days (runs):
- demand: unique phones per minute at the feeding gates (bottleneck.demand, 5 min window);
- queue: median speed of phones within queue_radius_m of the bottleneck below queue_speed_mps
  over the last queue_hold_s (at least min_phones speeds); each speed over span_s..2*span_s,
  since GPS error over one 15 s step swamps a queue's speed;
- a day's demand: median over the 10 min before the queue started, or, with no queue, over the
  day after the first 10 min;
- learned capacity = midway between the busiest day without a queue and the quietest day with one.
Each draw of phones learns its own value, as one real history would.

Test: the alarm rule chosen on training (stress.RULE) with the learned capacity as threshold,
unchanged, on fresh runs. Truth (>= 4/m² for 60 s near the bottleneck) is used only to score.

Writes out/<name>/results.json and calibrate.png.
"""
import argparse
import json
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from bottleneck import B, demand
from pings import Run, draw
from stress import RULE
from warn import ROOT, W, Truth, first_held

SITE = B["sites"][0]
Q = {"queue_radius_m": 40, "span_s": 60, "queue_speed_mps": 0.5, "queue_hold_s": 180, "min_phones": 3,
     "demand_window_s": 300, "before_min": 10, "warmup_min": 10}
SHARE = 0.02


def queue_start(truth, p):
    """First time (s) the phones near the bottleneck have been slow for queue_hold_s; inf = never."""
    t, ph = p["t"], p["phone"]
    xy = np.column_stack([p["x"], p["y"]])
    o = np.lexsort((t, ph))
    t, ph, xy = t[o], ph[o], xy[o]
    # Speed of each phone over span_s..2*span_s (GPS error over a 15 s step swamps a queue's speed).
    tv, vv = [], []
    done = np.zeros(len(t), bool)
    for k in range(1, 4 * Q["span_s"] // p["interval"] + 1):
        i = np.arange(len(t) - k)
        j = i + k
        dt = (t[j] - t[i]).astype(float)
        ok = ~done[i] & (ph[j] == ph[i]) & (dt >= Q["span_s"]) & (dt <= 2 * Q["span_s"]) \
            & (np.hypot(*(xy[j] - SITE["xy"]).T) <= Q["queue_radius_m"])
        tv.append(t[j][ok]); vv.append(np.hypot(*(xy[j][ok] - xy[i][ok]).T) / dt[ok])
        done[i[ok]] = True
    tv, vv = np.concatenate(tv), np.concatenate(vv)
    order = np.argsort(tv)
    tv, vv = tv[order], vv[order]
    for now in truth.times:
        a, b = np.searchsorted(tv, [now - Q["queue_hold_s"], now], side="right")
        if b - a >= Q["min_phones"] and np.median(vv[a:b]) < Q["queue_speed_mps"]:
            return float(now)
    return np.inf


def day_demand(truth, p):
    d, _ = demand(truth, p, SITE, Q["demand_window_s"], RULE["feeders"])
    q = queue_start(truth, p)
    m = truth.times >= Q["warmup_min"] * 60
    if np.isfinite(q):
        m = (truth.times >= q - Q["before_min"] * 60) & (truth.times < q) & (truth.times >= 5 * 60)
    return float(np.median(d[m])) if m.any() else None, float(q)


def learn(days):
    """days: list of (demand, queued). Capacity midway between busiest no-queue and quietest queue day."""
    lo = max((d for d, q in days if not q and d is not None), default=None)
    hi = min((d for d, q in days if q and d is not None), default=None)
    if lo is None or hi is None:
        return lo if hi is None else hi
    return (lo + hi) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", nargs="+", required=True)
    ap.add_argument("--test", nargs="+", required=True)
    ap.add_argument("--draws", type=int, default=20)
    ap.add_argument("--name", default="phase4_calibrate")
    args = ap.parse_args()
    out = ROOT / "out" / args.name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    log = lambda msg: print(f"[{time.time() - t0:5.0f}s] {msg}", flush=True)
    seeds = {"oracle": [0]} | {SHARE: [9000 + d for d in range(args.draws)]}

    def phones(run, share, seed):
        if share == "oracle":
            return next(draw(run, [1.0], 10, [0.0], seed=seed))[2]
        return next(draw(run, [share], 15, [10], seed=seed))[2]

    # 1. History: what the phones saw each day, and whether the truth agrees.
    history = []
    for name in args.history:
        run = Run(name)
        truth = Truth(run, 20)
        z = truth.zone_of(np.array([SITE["xy"]], float))[0]
        onset = float(truth.onset[truth.near[z]].min())
        day = {"run": name, "jam_truth": bool(np.isfinite(onset)), "by": {}}
        for share, ss in seeds.items():
            day["by"][str(share)] = []
            for s in ss:
                dd, q = day_demand(truth, phones(run, share, s))
                day["by"][str(share)].append({"demand": dd, "queue_min": q / 60 if np.isfinite(q) else None})
        history.append(day)
        o = day["by"]["oracle"][0]
        log(f"history {name}: truth jam {day['jam_truth']}, phones (everyone) demand {o['demand']:.0f}/min, "
            f"queue at {o['queue_min']} min")

    learned = {}
    for share, ss in seeds.items():
        learned[str(share)] = [learn([(h["by"][str(share)][i]["demand"], h["by"][str(share)][i]["queue_min"] is not None)
                                      for h in history]) for i in range(len(ss))]
    log(f"learned capacity: everyone {learned['oracle'][0]:.0f}/min; {SHARE:.0%} phones median "
        f"{np.median(learned[str(SHARE)]):.0f} (10–90%: {np.percentile(learned[str(SHARE)], 10):.0f}–"
        f"{np.percentile(learned[str(SHARE)], 90):.0f})")

    # 2. Test: frozen rule, learned threshold, fresh runs.
    tests = []
    for name in args.test:
        run = Run(name)
        truth = Truth(run, 20)
        z = truth.zone_of(np.array([SITE["xy"]], float))[0]
        onset = float(truth.onset[truth.near[z]].min())
        res = {"run": name, "jam": bool(np.isfinite(onset)), "onset_min": onset / 60 if np.isfinite(onset) else None, "by": {}}
        for share, ss in seeds.items():
            alarms = []
            for i, s in enumerate(ss):
                cap = learned[str(share)][i]
                d, se = demand(truth, phones(run, share, s + 500), SITE, RULE["window_s"], RULE["feeders"])
                cond = np.zeros((len(truth.times), len(truth.area)), bool)
                cond[:, z] = d - cap >= RULE["sigmas"] * se
                a = first_held(truth, cond, RULE["hold_s"])[z]
                alarms.append(a / 60 if np.isfinite(a) else None)
            r = {"alarm_min": alarms, "alarmed_share": float(np.mean([a is not None for a in alarms]))}
            if res["jam"]:
                leads = [res["onset_min"] - a for a in alarms if a is not None]
                r["lead_min_median"] = float(np.median(leads)) if leads else None
                r["lead_ok_share"] = float(np.mean([a is not None and res["onset_min"] - a >= W["go"]["lead_min"]
                                                    for a in alarms]))
            res["by"][str(share)] = r
        tests.append(res)
        r = res["by"][str(SHARE)]
        log(f"test {name}: truth jam {res['jam']} at {res['onset_min']}; {SHARE:.0%} phones alarmed "
            f"{r['alarmed_share']:.0%}" + (f", lead {r['lead_min_median']}, >= 5 min {r['lead_ok_share']:.0%}"
                                          if res["jam"] else "") +
            f"; everyone alarmed {res['by']['oracle']['alarmed_share']:.0%}")

    (out / "results.json").write_text(json.dumps({"rule": RULE, "queue": Q, "share": SHARE, "history": history,
                                                  "learned_capacity": learned, "tests": tests}, indent=1))

    fig, axs = plt.subplots(1, 2, figsize=(14, 4.8))
    ax = axs[0]
    for i, h in enumerate(history):
        for e in h["by"][str(SHARE)]:
            ax.scatter(e["demand"], i, c="red" if e["queue_min"] is not None else "C0", s=10, alpha=0.5)
        o = h["by"]["oracle"][0]
        ax.scatter(o["demand"], i, marker="|", s=200, c="k")
    ax.axvspan(np.percentile(learned[str(SHARE)], 10), np.percentile(learned[str(SHARE)], 90), color="grey", alpha=0.2,
               label=f"learned capacity, {SHARE:.0%} phones (10–90%)")
    ax.set_yticks(range(len(history)))
    ax.set_yticklabels([f"{h['run']} ({'jam' if h['jam_truth'] else 'no jam'})" for h in history], fontsize=7)
    ax.set_xlabel("demand seen by phones (people/min); red = phones saw a queue, | = everyone")
    ax.set_title("History: what the phones learn from"); ax.legend(fontsize=8)
    ax = axs[1]
    x = np.arange(len(tests))
    ax.bar(x - 0.2, [t["by"][str(SHARE)]["alarmed_share"] for t in tests], 0.4,
           color=["C2" if t["jam"] else "C3" for t in tests], label=f"{SHARE:.0%} phones")
    ax.bar(x + 0.2, [t["by"]["oracle"]["alarmed_share"] for t in tests], 0.4, color="grey", label="everyone")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{t['run']}\n" + (f"jam at {t['onset_min']:.0f} min" if t["jam"] else "no jam") for t in tests],
                       fontsize=7, rotation=20)
    ax.set_ylabel("share of draws that alarmed"); ax.legend(fontsize=8)
    ax.set_title("Fresh runs: green = jam (alarm is right), red = no jam (alarm is false)")
    fig.tight_layout(); fig.savefig(out / "calibrate.png", dpi=100); plt.close(fig)


if __name__ == "__main__":
    main()
