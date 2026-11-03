"""Two fixes for the bottleneck warning's false alarms (Phase 4).

1. Longer window: more phones per count, less noise (window_s up to 5 min).
2. Two alerts: amber when demand nears the learned capacity (amber_frac x capacity), red when
   it exceeds it. Days near capacity that do not jam should get amber, not red.

Capacity is learned per draw from the history runs, as in calibrate.py. Every rule in
config/sim.json -> warning.two_level is scored on the history runs; the best one is chosen
there and reported unchanged on the test runs. Days are classed by what happened at the
merge (jam / busy / calm, see the config note); truth only scores.

Writes out/<name>/results.json and two_level.png.
"""
import argparse
import itertools
import json
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from bottleneck import demand
from calibrate import SHARE, SITE, day_demand, learn
from pings import Run, draw
from warn import ROOT, W, Truth, first_held

T = W["two_level"]
GO = T["go"]


def rules():
    for window, k, a, hold in itertools.product(T["window_s"], T["sigmas"], T["amber_frac"], T["hold_s"]):
        yield {"window_s": window, "sigmas": k, "amber_frac": a, "hold_s": hold}


def phones(run, share, seed):
    if share == "oracle":
        return next(draw(run, [1.0], 10, [0.0], seed=seed))[2]
    return next(draw(run, [share], 15, [10], seed=seed))[2]


class Day:
    """One run: its class at the merge, and the phones of every draw."""

    def __init__(self, name, seeds):
        run = Run(name)
        self.name = name
        self.truth = truth = Truth(run, 20)
        z = self.z = truth.zone_of(np.array([SITE["xy"]], float))[0]
        onset = float(truth.onset[truth.near[z]].min())
        self.onset_min = onset / 60 if np.isfinite(onset) else None
        d = truth.density[:, truth.near[z] & truth.valid]
        hold = W["event_hold_s"] // W["eval_step_s"]
        self.peak = float(max(d[i:i + hold].min(0).max() for i in range(len(d) - hold)))
        self.kind = "jam" if self.onset_min is not None else ("busy" if self.peak >= T["busy_ppm2"] else "calm")
        self.pings = {share: [phones(run, share, s) for s in ss] for share, ss in seeds.items()}

    def alerts(self, share, i, cap, rule, cache):
        """(amber, red) first times in minutes, None = never."""
        key = (share, i, rule["window_s"])
        if key not in cache:
            cache[key] = demand(self.truth, self.pings[share][i], SITE, rule["window_s"], "gates")
        d, se = cache[key]
        out = []
        for c in (rule["amber_frac"] * cap, cap):
            cond = np.zeros((len(self.truth.times), len(self.truth.area)), bool)
            cond[:, self.z] = d - c >= rule["sigmas"] * se
            t = first_held(self.truth, cond, rule["hold_s"])[self.z]
            out.append(float(t / 60) if np.isfinite(t) else None)
        return out


def score(day, al):
    """al: list of (amber, red) per draw."""
    amber = [a for a, _ in al]
    red = [r for _, r in al]
    first = [min(x for x in (a, r) if x is not None) if (a, r) != (None, None) else None for a, r in al]
    s = {"run": day.name, "kind": day.kind, "peak_ppm2": day.peak, "onset_min": day.onset_min,
         "amber_share": float(np.mean([a is not None for a in amber])),
         "red_share": float(np.mean([r is not None for r in red])), "alerts": al}
    if day.kind == "jam":
        leads = [day.onset_min - f for f in first if f is not None]
        s["lead_min_median"] = float(np.median(leads)) if leads else None
        s["lead_ok_share"] = float(np.mean([f is not None and day.onset_min - f >= GO["lead_min"] for f in first]))
        s["red_before_jam_share"] = float(np.mean([r is not None and r < day.onset_min for r in red]))
        s["pass"] = s["lead_ok_share"] >= GO["lead_ok_share"] and s["red_before_jam_share"] >= GO["red_before_jam_share"]
    else:
        s["pass"] = s["red_share"] <= GO["false_red_share"] and \
            (day.kind == "busy" or s["amber_share"] <= GO["false_amber_calm_share"])
    return s


def evaluate(days, learned, share, rule, cache):
    return [score(d, [d.alerts(share, i, cap, rule, cache[d.name]) for i, cap in enumerate(learned[share])])
            for d in days]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", nargs="+", required=True)
    ap.add_argument("--test", nargs="*", default=[])
    ap.add_argument("--seen", nargs="*", default=[], help="runs already looked at; reported, not a clean test")
    ap.add_argument("--draws", type=int, default=20)
    ap.add_argument("--name", default="phase4_two_level")
    args = ap.parse_args()
    out = ROOT / "out" / args.name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    log = lambda msg: print(f"[{time.time() - t0:5.0f}s] {msg}", flush=True)
    learn_seeds = {"oracle": [0], SHARE: [9000 + d for d in range(args.draws)]}
    alert_seeds = {k: [s + 500 for s in v] for k, v in learn_seeds.items()}

    # Capacity, learned from the history as in calibrate.py.
    days_seen = {share: [[] for _ in ss] for share, ss in learn_seeds.items()}
    history = []
    for name in args.history:
        run = Run(name)
        truth = Truth(run, 20)
        for share, ss in learn_seeds.items():
            for i, s in enumerate(ss):
                dd, q = day_demand(truth, phones(run, share, s))
                days_seen[share][i].append((dd, np.isfinite(q)))
        history.append(Day(name, alert_seeds))
        log(f"history {name}: {history[-1].kind}, peak {history[-1].peak:.2f}/m²")
    learned = {share: [learn(d) for d in v] for share, v in days_seen.items()}
    log(f"learned capacity: everyone {learned['oracle'][0]:.0f}; {SHARE:.0%} median {np.median(learned[SHARE]):.0f}")

    # Choose on the history.
    cache = {d.name: {} for d in history}
    cands = []
    for rule in rules():
        res = evaluate(history, learned, SHARE, rule, cache)
        lead = [r["lead_ok_share"] for r in res if r["kind"] == "jam"]
        worst_red = max([r["red_share"] for r in res if r["kind"] != "jam"], default=0)
        cands.append({"rule": rule, "n_fail": sum(not r["pass"] for r in res), "min_lead_ok": min(lead),
                      "worst_false_red": worst_red, "history": res})
    cands.sort(key=lambda c: (c["n_fail"], -c["min_lead_ok"], c["worst_false_red"]))
    chosen = cands[0]
    log(f"chosen on history: {chosen['rule']} ({chosen['n_fail']} of {len(history)} days fail)")
    baseline = {"window_s": 120, "sigmas": 1, "amber_frac": 1.0, "hold_s": 60}   # calibrate.py's rule, one level

    report = {"two_level": T, "share": SHARE, "learned_capacity": learned, "chosen": chosen["rule"],
              "history": {"chosen": chosen["history"], "top5": [{k: c[k] for k in ("rule", "n_fail", "min_lead_ok",
                                                                                   "worst_false_red")}
                                                                for c in cands[:5]]}}
    groups = {}
    for label, names in (("test", args.test), ("seen", args.seen)):
        if not names:
            continue
        days = [Day(n, alert_seeds) for n in names]
        cache.update({d.name: {} for d in days})
        groups[label] = days
        report[label] = {}
        for share in (SHARE, "oracle"):
            report[label][str(share)] = {"chosen": evaluate(days, learned, share, chosen["rule"], cache),
                                         "baseline": evaluate(days, learned, share, baseline, cache)}
        for r, b in zip(report[label][str(SHARE)]["chosen"], report[label][str(SHARE)]["baseline"]):
            log(f"{label} {r['run']} ({r['kind']}, peak {r['peak_ppm2']:.1f}): amber {r['amber_share']:.0%}, "
                f"red {r['red_share']:.0%}" + (f", lead {r['lead_min_median']}, >= 5 min {r['lead_ok_share']:.0%}, "
                                              f"red before jam {r['red_before_jam_share']:.0%}" if r["kind"] == "jam" else "")
                + f", {'PASS' if r['pass'] else 'fail'}; old rule alarmed {b['red_share']:.0%}")
    (out / "results.json").write_text(json.dumps(report, indent=1))

    panels = [("history", chosen["history"])] + [(k, report[k][str(SHARE)]["chosen"]) for k in groups]
    fig, axs = plt.subplots(1, len(panels), figsize=(6 * len(panels), 4.8), sharey=True, squeeze=False)
    for ax, (label, res) in zip(axs[0], panels):
        x = np.arange(len(res))
        ax.bar(x - 0.2, [r["amber_share"] for r in res], 0.4, color="orange", label="amber")
        ax.bar(x + 0.2, [r["red_share"] for r in res], 0.4, color="red", label="red")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{r['run']}\n{r['kind']}" + (f" at {r['onset_min']:.0f} min" if r["onset_min"] else "")
                            + ("" if r["pass"] else " ✗") for r in res], fontsize=7, rotation=30, ha="right")
        ax.set_title(f"{label} runs ({SHARE:.0%} phones)"); ax.legend(fontsize=8)
    axs[0][0].set_ylabel("share of draws with the alert")
    r = chosen["rule"]
    fig.suptitle(f"Two-level alert: window {r['window_s'] // 60} min, {r['sigmas']} σ, amber at {r['amber_frac']:.0%} "
                 f"of learned capacity, hold {r['hold_s']} s (✗ = fails the go criteria)")
    fig.tight_layout(); fig.savefig(out / "two_level.png", dpi=100); plt.close(fig)


if __name__ == "__main__":
    main()
