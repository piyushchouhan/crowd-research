"""Run one Sangam scenario over its range of inflows and summarise the danger.

For each inflow in config/sim.json -> scenarios.<name>.inflow_ppm (or --inflows):
run_sim.py, then analyze.py, then keep the key numbers. Snapshots are deleted
after analysis unless --keep-snapshots (a long peak run is large).

Writes out/sweeps/<scenario>/summary.json and summary.png.
Densities at 6/m2 are what the model indicates; it is validated only up to ~4/m2.
"""
import argparse
import json
import subprocess
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config

ROOT = config.ROOT
SCRIPTS = ROOT / "scripts"


def run(args, label):
    t0 = time.time()
    r = subprocess.run([sys.executable, *args], cwd=SCRIPTS, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"{label} failed:\n{r.stderr[-2000:]}")
    return time.time() - t0


def main():
    cfg = config.load()
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=sorted(cfg["scenarios"]))
    ap.add_argument("--inflows", type=float, nargs="*", help="override the scenario's inflow list (people/min)")
    ap.add_argument("--minutes", type=float, help="override the scenario's duration")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--keep-snapshots", action="store_true")
    args = ap.parse_args()
    sc = cfg["scenarios"][args.scenario]
    inflows = args.inflows or sc["inflow_ppm"]
    minutes = args.minutes or sc["minutes"]
    out = ROOT / "out" / "sweeps" / args.scenario
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for inflow in inflows:
        name = f"{args.scenario}_in{int(inflow)}_s{args.seed}"
        wall = run(["run_sim.py", "--inflow", str(inflow), "--outflow-frac", str(sc["outflow_frac"]),
                    "--minutes", str(minutes), "--seed", str(args.seed), "--name", name], f"run_sim {name}")
        run(["analyze.py", name], f"analyze {name}")
        run_dir = ROOT / "out" / name
        m = json.loads((run_dir / "metrics.json").read_text())
        if not args.keep_snapshots:
            (run_dir / "snapshots.npz").unlink()
        row = {"inflow_ppm": inflow, "run": name, "wall_s": round(wall),
               "peak_agents": m["peak_agents"], "max_density": round(m["max_density"], 2),
               "first_t_dense_s": m["first_t_dense"], "first_t_critical_s": m["first_t_critical"],
               "area_dense_m2": round(m["area_dense_m2"]), "area_critical_m2": round(m["area_critical_m2"]),
               "max_pressure": round(m["max_pressure"], 3),
               "waiting_outside_end": m["waiting_outside_end"], "entered_inbound": m["entered_inbound"],
               "first_cells_dense": m["first_cells_dense"][:3]}
        rows.append(row)
        print(f"{name}: max {row['max_density']}/m², ≥4/m² first at {row['first_t_dense_s']} s over "
              f"{row['area_dense_m2']} m², waiting outside {row['waiting_outside_end']}, wall {row['wall_s']} s",
              flush=True)

    summary = {"scenario": args.scenario, "note": sc["note"], "minutes": minutes, "seed": args.seed,
               "outflow_frac": sc["outflow_frac"], "model": cfg["model"], "agents": cfg["agents"], "runs": rows}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))

    x = [r["inflow_ppm"] for r in rows]
    fig, axs = plt.subplots(2, 2, figsize=(10, 7))
    axs[0, 0].plot(x, [r["max_density"] for r in rows], "o-")
    axs[0, 0].axhline(cfg["analysis"]["dense_ppm2"], color="orange", ls="--")
    axs[0, 0].axhline(cfg["analysis"]["critical_ppm2"], color="red", ls="--")
    axs[0, 0].set_ylabel("max density [people/m²]")
    axs[0, 1].plot(x, [r["area_dense_m2"] for r in rows], "o-", color="orange", label="≥ 4/m²")
    axs[0, 1].plot(x, [r["area_critical_m2"] for r in rows], "o-", color="red", label="≥ 6/m² (not validated)")
    axs[0, 1].set_ylabel("area ever over threshold [m²]")
    axs[0, 1].legend()
    axs[1, 0].plot(x, [(r["first_t_dense_s"] or float("nan")) / 60 for r in rows], "o-", color="orange")
    axs[1, 0].set_ylabel("minutes until first ≥ 4/m²")
    axs[1, 1].plot(x, [r["waiting_outside_end"] for r in rows], "o-", color="grey")
    axs[1, 1].set_ylabel("people still waiting outside at end")
    for ax in axs.flat:
        ax.set_xlabel("inflow [people/min]")
    fig.suptitle(f"{args.scenario}: {minutes:g} min per run, seed {args.seed}")
    fig.tight_layout()
    fig.savefig(out / "summary.png", dpi=100)
    print(f"wrote {out / 'summary.json'}")


if __name__ == "__main__":
    main()
