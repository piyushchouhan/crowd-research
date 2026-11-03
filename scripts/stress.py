"""Stress test of the bottleneck warning (Phase 4).

The rule chosen on the training runs (bottleneck.py: counting at the gates, 2 min window,
1 standard error, held 60 s) is applied unchanged to other runs, with the capacity at the
configured 1.3 people/m/s and at the measured 1.86 (Jülich bottlenecks). Per run and share:
- jam: did a cell near the merge reach >= 4/m² for 60 s (truth), and when;
- warned: share of draws that alarmed, and lead time where there was a jam;
- false alarm: share of draws that alarmed in a run with no jam at the merge.
Also measures the simulated merge's real throughput: unique people per minute passing a
circle 40 m downstream while the merge is jammed.

Writes out/<name>/results.json and stress.png.
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
from rules import SHARES
from warn import CFG, ROOT, W, Truth, first_held

RULE = {"feeders": "gates", "window_s": 120, "sigmas": 1, "hold_s": 60}   # chosen in bottleneck.py
SPECIFIC_FLOW = {"config 1.3": CFG["capacity"]["specific_flow_pms"], "Jülich 1.86": 1.86}
DOWNSTREAM = ([416, 663], 12)     # 40 m below the merge on the outgoing road


def throughput(run, onset, window=180):
    """Unique people per minute passing the downstream circle, from 5 min after onset to the end."""
    (cx, cy), r = DOWNSTREAM
    rates = []
    for t0 in range(int(onset) + 300, run.seconds - window, 60):
        ids = set()
        for t in range(t0, t0 + window, 5):
            p = run.xy[run.off[t]:run.off[t + 1]]
            ids.update(run.ids[run.off[t]:run.off[t + 1]][np.hypot(p[:, 0] - cx, p[:, 1] - cy) <= r].tolist())
        rates.append(len(ids) / (window / 60))
    return float(np.median(rates)) if rates else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--draws", type=int, default=20)
    ap.add_argument("--name", default="phase4_stress")
    args = ap.parse_args()
    out = ROOT / "out" / args.name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    site = B["sites"][0]
    results = []
    for name in args.runs:
        run = Run(name)
        truth = Truth(run, 20)
        z = truth.zone_of(np.array([site["xy"]], float))[0]
        onset = float(truth.onset[truth.near[z]].min())
        jam = bool(np.isfinite(onset))
        res = {"run": name, "jam": jam, "onset_min": onset / 60 if jam else None,
               "throughput_ppm": throughput(run, onset) if jam else None, "by": {}}
        sets = [("oracle", p) for _, _, p in draw(run, [1.0], 10, [0.0], seed=0)]
        for d in range(args.draws):
            sets += [(share, p) for share, _, p in draw(run, SHARES, 15, [10], seed=9000 + d)]
        for share, p in sets:
            d, se = demand(truth, p, site, RULE["window_s"], RULE["feeders"])
            for cap_name, sf in SPECIFIC_FLOW.items():
                cap = site["width_m"] * sf * 60
                cond = np.zeros((len(truth.times), len(truth.area)), bool)
                cond[:, z] = d - cap >= RULE["sigmas"] * se
                alarm = first_held(truth, cond, RULE["hold_s"])[z]
                key = f"{share}|{cap_name}"
                res["by"].setdefault(key, {"alarm_min": []})["alarm_min"].append(
                    float(alarm / 60) if np.isfinite(alarm) else None)
        for key, v in res["by"].items():
            a = [x for x in v["alarm_min"] if x is not None]
            v["alarmed_share"] = len(a) / len(v["alarm_min"])
            if jam:
                leads = [res["onset_min"] - x if x is not None else None for x in v["alarm_min"]]
                v["lead_min_median"] = float(np.median([l for l in leads if l is not None])) if a else None
                v["lead_ok_share"] = float(np.mean([(l if l is not None else -1e9) >= W["go"]["lead_min"] for l in leads]))
        results.append(res)
        print(f"[{time.time() - t0:5.0f}s] {name}: jam {jam} at {res['onset_min']} min, "
              f"merge throughput {res['throughput_ppm']}/min", flush=True)
        for key in ("0.02|config 1.3", "0.02|Jülich 1.86", "oracle|config 1.3", "oracle|Jülich 1.86"):
            v = res["by"][key]
            print(f"   {key}: alarmed {v['alarmed_share']:.0%}" +
                  (f", lead {v['lead_min_median']}, >= 5 min {v['lead_ok_share']:.0%}" if jam else ""), flush=True)
    (out / "results.json").write_text(json.dumps({"rule": RULE, "specific_flow": SPECIFIC_FLOW, "runs": results}, indent=1))

    fig, axs = plt.subplots(1, 2, figsize=(13, 4.5), sharey=True)
    for ax, cap_name in zip(axs, SPECIFIC_FLOW):
        x = np.arange(len(results))
        for i, (share, c) in enumerate([(0.01, "C1"), (0.02, "C0"), (0.05, "C2")]):
            vals = [r["by"][f"{share}|{cap_name}"]["alarmed_share"] for r in results]
            ax.bar(x + (i - 1) * 0.25, vals, 0.25, color=c, label=f"{share:.0%} phones")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{r['run']}\n" + (f"jam at {r['onset_min']:.0f} min" if r["jam"] else "no jam")
                            for r in results], fontsize=7, rotation=20)
        ax.set_title(f"capacity at {cap_name} people/m/s ({site['width_m'] * SPECIFIC_FLOW[cap_name] * 60:.0f}/min)")
        ax.set_ylabel("share of draws that alarmed"); ax.legend(fontsize=8)
    fig.suptitle("Bottleneck warning, rule fixed on training: alarm is right on jam runs, false on no-jam runs")
    fig.tight_layout(); fig.savefig(out / "stress.png", dpi=100); plt.close(fig)


if __name__ == "__main__":
    main()
