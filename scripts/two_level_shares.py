"""How many phones does the two-level alert need? (Phase 4)

Same protocol as two_level.py, repeated for several phone shares: capacity learned per draw
from the history runs, rule chosen on the history, tested unchanged on the test runs. Two
rules per share: the one chosen at 2% in two_level.py (fixed, read from its results) and the
one chosen on the history at that share.
Phones are nested (the 5% phones include the 2% ones, same draw), so this 2% set is a new
draw of the one in two_level.py and should give similar numbers.

--interval and --sigma change the phones' ping interval and GPS error (default 15 s, 10 m);
capacity is then learned with those phones too.

Writes out/<name>/results.json and shares.png.
"""
import argparse
import json
import time
from multiprocessing import Pool

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from bottleneck import demand
from calibrate import SITE, day_demand, learn
from pings import Run, draw
from two_level import GO, T, rules, score
from warn import ROOT, W, Truth


def held_first(times, cond, hold_s):
    """First time (min) at which cond has held for hold_s; None = never."""
    hold = hold_s // W["eval_step_s"] + 1
    cs = np.concatenate([[0], np.cumsum(cond)])
    i = np.flatnonzero(cs[hold:] - cs[:-hold] >= hold)
    return float(times[i[0] + hold - 1] / 60) if len(i) else None


class Day:
    """One run: its class at the merge and, per share and draw, the demand for every window."""

    def __init__(self, name, shares, seeds, learn_seeds=(), interval=15, sigma=10):
        run = Run(name)
        self.interval, self.sigma = interval, sigma
        self.name = name
        truth = Truth(run, 20)
        self.times = truth.times
        z = truth.zone_of(np.array([SITE["xy"]], float))[0]
        onset = float(truth.onset[truth.near[z]].min())
        self.onset_min = onset / 60 if np.isfinite(onset) else None
        d = truth.density[:, truth.near[z] & truth.valid]
        hold = W["event_hold_s"] // W["eval_step_s"]
        self.peak = float(max(d[i:i + hold].min(0).max() for i in range(len(d) - hold)))
        self.kind = "jam" if self.onset_min is not None else ("busy" if self.peak >= T["busy_ppm2"] else "calm")
        self.dem = {s: [] for s in shares}
        for i, seed in enumerate(seeds):     # everyone's phones: one draw only
            for share, p in self.pings(run, shares if i == 0 else [s for s in shares if s != "oracle"], seed):
                self.dem[share].append({w: demand(truth, p, SITE, w, "gates") for w in T["window_s"]})
        # What the phones saw for learning (separate draws): (demand, queue seen) per share and draw.
        self.seen = {s: [] for s in shares}
        for i, seed in enumerate(learn_seeds):
            for share, p in self.pings(run, shares if i == 0 else [s for s in shares if s != "oracle"], seed):
                dd, q = day_demand(truth, p)
                self.seen[share].append((dd, bool(np.isfinite(q))))

    def pings(self, run, shares, seed):
        if "oracle" in shares:
            yield "oracle", next(draw(run, [1.0], 10, [0.0], seed=seed))[2]
        real = [s for s in shares if s != "oracle"]
        for share, _, p in draw(run, real, self.interval, [self.sigma], seed=seed):
            yield share, p

    def alerts(self, share, cap, rule):
        out = []
        for i, c in enumerate(cap):
            d, se = self.dem[share][i][rule["window_s"]]
            out.append(tuple(held_first(self.times, d - lvl >= rule["sigmas"] * se, rule["hold_s"])
                             for lvl in (rule["amber_frac"] * c, c)))
        return out


def choose(history, share, cap):
    cands = []
    for rule in rules():
        res = [score(d, d.alerts(share, cap, rule)) for d in history]
        cands.append({"rule": rule, "n_fail": sum(not r["pass"] for r in res),
                      "min_lead_ok": min(r["lead_ok_share"] for r in res if r["kind"] == "jam"),
                      "worst_false_red": max([r["red_share"] for r in res if r["kind"] != "jam"], default=0)})
    cands.sort(key=lambda c: (c["n_fail"], -c["min_lead_ok"], c["worst_false_red"]))
    return cands[0]


def slim(r):
    return {k: v for k, v in r.items() if k != "alerts"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", nargs="+", required=True)
    ap.add_argument("--test", nargs="+", required=True)
    ap.add_argument("--shares", type=float, nargs="+", default=[0.02, 0.05, 0.1, 0.2])
    ap.add_argument("--draws", type=int, default=20)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--interval", type=int, default=15, help="ping interval (s)")
    ap.add_argument("--sigma", type=float, default=10, help="GPS error (m)")
    ap.add_argument("--name", default="phase4_two_level_shares")
    args = ap.parse_args()
    out = ROOT / "out" / args.name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    log = lambda msg: print(f"[{time.time() - t0:5.0f}s] {msg}", flush=True)
    shares = args.shares + ["oracle"]
    learn_seeds, alert_seeds = [9000 + d for d in range(args.draws)], [9500 + d for d in range(args.draws)]

    with Pool(args.workers) as pool:
        history = pool.starmap(Day, [(n, shares, alert_seeds, learn_seeds, args.interval, args.sigma)
                                              for n in args.history])
        log("history runs loaded: " + ", ".join(f"{d.name} {d.kind}" for d in history))
        tests = pool.starmap(Day, [(n, shares, alert_seeds, (), args.interval, args.sigma) for n in args.test])
    learned = {s: [learn([d.seen[s][i] for d in history]) for i in range(len(history[0].seen[s]))] for s in shares}
    log("test runs loaded")

    # The rule chosen at 2% in two_level.py and already tested there.
    fixed = json.loads((ROOT / "out" / "phase4_two_level" / "results.json").read_text())["chosen"]
    report = {"two_level": T, "shares": args.shares, "interval_s": args.interval, "sigma_m": args.sigma,
              "fixed_rule": fixed, "by_share": {}}
    for s in shares:
        ch = choose(history, s, learned[s])
        entry = {"learned_capacity_median": float(np.median(learned[s])), "chosen": ch}
        for label, rule in (("fixed", fixed), ("own", ch["rule"])):
            if rule is None:
                continue
            res = [score(d, d.alerts(s, learned[s], rule)) for d in tests]
            entry[label] = [slim(r) for r in res]
        report["by_share"][str(s)] = entry
        for label in ("fixed", "own"):
            res = entry.get(label, [])
            jam = [r for r in res if r["kind"] == "jam"]
            nojam = [r for r in res if r["kind"] != "jam"]
            log(f"{s} {label} {entry['chosen']['rule'] if label == 'own' else fixed}: "
                f"{sum(r['pass'] for r in res)}/{len(res)} pass; red before jam "
                f"{[round(r['red_before_jam_share'], 2) for r in jam]}, lead ok {[round(r['lead_ok_share'], 2) for r in jam]}, "
                f"false red {[round(r['red_share'], 2) for r in nojam]}")
    (out / "results.json").write_text(json.dumps(report, indent=1))

    # Red before the jam and false red, per share, with the fixed and the own rule.
    fig, axs = plt.subplots(1, 3, figsize=(16, 4.5))
    xs = args.shares
    for label, ls in (("fixed", "-"), ("own", "--")):
        by = [report["by_share"][str(s)].get(label, []) for s in xs]
        jams = [[r for r in b if r["kind"] == "jam"] for b in by]
        nojam = [[r for r in b if r["kind"] != "jam"] for b in by]
        for j, run in enumerate(r["run"] for r in jams[0]):
            axs[0].plot(xs, [b[j]["red_before_jam_share"] for b in jams], ls, marker="o", color=f"C{j}",
                        label=f"{run} ({label} rule)")
            axs[1].plot(xs, [b[j]["lead_min_median"] or 0 for b in jams], ls, marker="o", color=f"C{j}",
                        label=f"{run} ({label} rule)")
        axs[2].plot(xs, [max(r["red_share"] for r in b) for b in nojam], ls, marker="o", color="k",
                    label=f"worst day without a jam ({label} rule)")
    axs[0].axhline(GO["red_before_jam_share"], color="red", ls=":", lw=0.8)
    axs[2].axhline(GO["false_red_share"], color="red", ls=":", lw=0.8)
    axs[0].set_ylabel("share of draws with red before the jam")
    axs[1].set_ylabel("median lead of the first alert (min)")
    axs[2].set_ylabel("share of draws with a false red")
    for ax in axs:
        ax.set_xscale("log"); ax.set_xticks(xs); ax.set_xticklabels([f"{s:.0%}" for s in xs]); ax.minorticks_off()
        ax.set_xlabel("phone share"); ax.legend(fontsize=7)
    fig.suptitle("Two-level alert on the unseen test runs: solid = rule chosen at 2%, dashed = rule chosen at each share")
    fig.tight_layout(); fig.savefig(out / "shares.png", dpi=100); plt.close(fig)


if __name__ == "__main__":
    main()
