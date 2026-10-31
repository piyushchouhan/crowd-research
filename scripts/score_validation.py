"""Rank validation runs (out/validation/<name>/summary.json) by mean error across the tests they include.

Usage: python scripts/score_validation.py "out/validation/sfgrid_*"
Score = mean of bottleneck flow error, corridor speed error (>= 0.5/m²) and two-way flow error.
"stuck" counts runs with deadlocks or crashes; a setting with any is not usable.
"""
import glob
import json
import sys

rows = []
for f in sorted(glob.glob(sys.argv[1] + "/summary.json")):
    s = json.load(open(f))
    b, c, d = s.get("bottleneck"), s.get("corridor"), s.get("bidirectional")
    errs = [x for x in (b and b["mean_abs_error"], c and c["mean_abs_error"], d and d["flow_mean_abs_error"])
            if x is not None]
    rows.append({
        "score": sum(errs) / len(errs), "name": f.split("/")[-2],
        "bottleneck": b and f"{b['mean_abs_error']:.0%} ({b['widths_passing']}/{b['widths_total']} pass, "
                            f"{sum(r['deadlock'] for r in b['runs'])} stuck)",
        "corridor": c and f"{c['mean_abs_error']:.0%} ({sum(1 for r in c['runs'] if sum(r['stuck']) > 5)} stuck)",
        "two-way": d and f"{d['flow_mean_abs_error']:.0%} ({d['runs_passing']}/{d['runs_total']} pass, "
                         f"{d['runs_deadlocked']} stuck)",
    })
for r in sorted(rows, key=lambda r: r["score"]):
    print(f"{r['name']:34s} score {r['score']:.2f} | bottleneck {r['bottleneck']} | "
          f"corridor {r['corridor']} | two-way {r['two-way']}")
