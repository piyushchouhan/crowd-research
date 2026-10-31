"""Re-run Jülich lab experiments in JuPedSim and compare with the real trajectories.

bottleneck: 2006 Caserne bottleneck series (DOI 10.34735/ped.2006.2), widths 0.9-2.5 m.
            Compares the flow through the bottleneck (N-t at a line across its middle).
corridor:   2009 Hermes unidirectional corridor, open boundary (DOI 10.34735/ped.2009.14).
            Compares Voronoi speed against density in a 2 m area mid-corridor.

Real and simulated trajectories go through the same PedPy functions. Model and agent
parameters come from config/sim.json, the same as the Sangam runs; --set overrides
them for calibration, e.g. --set agents.time_gap_s=0.8.

Writes out/validation/<name>/summary.json and PNGs. Simulated trajectories (SQLite in
out/validation/<name>/sim/) are deleted after analysis unless --keep-sim is given.
"""
import argparse
import json
import re
import time

import jupedsim as jps
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pedpy
import shapely
from shapely import wkt
from shapely.geometry import box

import config

ROOT = config.ROOT
DATA = ROOT / "data" / "juelich"
TOLERANCE = 0.15             # pass if simulated flow is within +-15% of the real one
START_DENSITY = 3.0          # people/m2 in the holding area before release; not in the data, assumed
STEADY = (0.1, 0.9)          # flow is measured between these shares of people having passed
MAX_SIM_S = 600
SPEED_WINDOW_S = 0.5         # individual speed from displacement over this window
VORONOI_EVERY = 4            # frames between Voronoi samples (16 fps -> 4 per second)
DENSITY_BINS = np.arange(0, 6.25, 0.25)
MIN_BIN_SAMPLES = 20
MIN_FD_DENSITY = 0.5         # below this, 1-2 people in the area make Voronoi density/speed unreliable


def apply_overrides(cfg, sets):
    for item in sets:
        key, value = item.split("=", 1)
        node = cfg
        *path, last = key.split(".")
        for k in path:
            node = node[k]
        if last not in node:
            raise SystemExit(f"--set {key}: no such config key")
        node[last] = float(value)
    return cfg


def lattice(x0, x1, y_edge, n, direction, rng):
    """n start positions on a square grid at START_DENSITY, rows growing away from y_edge."""
    s = 1 / np.sqrt(START_DENSITY)
    cols = int((x1 - x0) / s)
    i = np.arange(n)
    x = x0 + s / 2 + (i % cols) * s
    y = y_edge + direction * (s / 2 + (i // cols) * s)
    return np.column_stack([x, y]) + rng.uniform(-0.05, 0.05, (n, 2)), int(np.ceil(n / cols)) * s


# --- experiment setups -------------------------------------------------------------

def bottleneck_runs():
    meta = json.load(open(DATA / "bottleneck2" / "metadata.json"))["experiment"]["parameters"]
    for r in meta:
        f = DATA / "bottleneck2" / f"{r['run_name']}.txt"
        if re.fullmatch(r"b\d{3}", r["run_name"]) and f.exists():
            yield r["run_name"], r, f


def corridor_runs():
    meta = json.load(open(DATA / "unidir_open" / "metadata.json"))["experiment"]["run"]
    for r in meta:
        f = DATA / "unidir_open" / f"{r['run_name']}.txt"
        if f.exists():
            yield r["run_name"], r, f


def bottleneck_setup(run, rng):
    """Floor of floor_width, people waiting bottleneck_distance before a b x l bottleneck at y=0."""
    p = run["parameters"]
    b, l = float(p["bottleneck_width"]), float(p["bottleneck_length"])
    half = float(p["floor_width"]) / 2
    dist = float(p["bottleneck_distance"])
    start, depth = lattice(-half + 0.2, half - 0.2, -dist, run["number_participants"], -1, rng)
    walk = shapely.union_all([box(-half, -dist - depth - 1, half, 0), box(-b / 2, 0, b / 2, l),
                              box(-4, l, 4, l + 5)])
    goal = box(-3.8, l + 4.2, 3.8, l + 4.9)
    line = pedpy.MeasurementLine([(-b / 2, l / 2), (b / 2, l / 2)])
    return walk, start, goal, {"line": line, "width_m": b}


def corridor_setup(run, rng):
    """Archive geometry, with a holding area added above y=10 and the outside of the corridor closed."""
    width = float(run["parameter"]["corridor_width [m]"].rstrip("m"))
    start, depth = lattice(-2.8, 4.52, 10.2, run["number_participants"], 1, rng)
    walk = wkt.loads(run["wkt_geometry"]).union(box(-3, 10, 4.72, 10.2 + depth + 1))
    # The archive polygon leaves the floor beside the corridor open; people never walked there.
    walk = walk.difference(box(-3.1, -7.3, 0, 4)).difference(box(width, -7.3, 4.8, 4))
    walk = max(getattr(walk, "geoms", [walk]), key=lambda g: g.area)
    goal = box(0.05, -7.1, width - 0.05, -6.6).intersection(walk)
    return walk, start, goal, {"width_m": width}


# --- simulation --------------------------------------------------------------------

def simulate(walk, start, goal, fps, out_file, cfg, rng):
    """Run until everyone has left. Frames are written at the real data's frame rate."""
    writer = jps.SqliteTrajectoryWriter(output_file=out_file, every_nth_frame=2)
    sim = jps.Simulation(model=jps.CollisionFreeSpeedModel(**cfg["model"]), geometry=walk,
                         dt=1 / (2 * fps), trajectory_writer=writer)
    exit_id = sim.add_exit_stage(goal)
    journey = sim.add_journey(jps.JourneyDescription([exit_id]))
    sp, ag = cfg["agents"]["desired_speed_mps"], cfg["agents"]
    for p in start:
        sim.add_agent(jps.CollisionFreeSpeedModelAgentParameters(
            journey_id=journey, stage_id=exit_id, position=tuple(p),
            desired_speed=float(np.clip(rng.normal(sp["mean"], sp["sd"]), sp["min"], sp["max"])),
            radius=ag["radius_m"], time_gap=ag["time_gap_s"]))
    while sim.agent_count() and sim.elapsed_time() < MAX_SIM_S:
        sim.iterate()
    stuck = sim.agent_count()
    writer.close()
    return stuck


# --- measurements (identical for real and simulated) --------------------------------

def load_real(path, fps):
    return pedpy.load_trajectory_from_txt(trajectory_file=path, default_frame_rate=fps,
                                          default_unit=pedpy.TrajectoryUnit.CENTIMETER)


def bottleneck_flow(traj, line):
    """Flow (people/s) from the steady part of the N-t curve, plus crossing times from the first one."""
    _, crossing = pedpy.compute_n_t(traj_data=traj, measurement_line=line)
    t = np.sort(crossing[pedpy.FRAME_COL].to_numpy()) / traj.frame_rate
    k0, k1 = int(STEADY[0] * len(t)), int(STEADY[1] * len(t)) - 1
    return (k1 - k0) / (t[k1] - t[k0]), t - t[0]


def corridor_fd(traj, width):
    """(density, speed) per sampled frame in the 2 m measurement area mid-corridor."""
    fps = traj.frame_rate
    speed = pedpy.compute_individual_speed(traj_data=traj, frame_step=max(1, round(fps * SPEED_WINDOW_S / 2)))
    df = traj.data
    keep = (df.x > 0) & (df.x < width) & (df.y > -4) & (df.y < 4) & (df.frame % VORONOI_EVERY == 0)
    inside = pedpy.TrajectoryData(data=df[keep].reset_index(drop=True), frame_rate=fps)
    area = pedpy.MeasurementArea(box(0, -1, width, 1))
    cells = pedpy.compute_individual_voronoi_polygons(
        traj_data=inside, walkable_area=pedpy.WalkableArea(box(0, -4, width, 4)),
        cut_off=pedpy.Cutoff(radius=1.0))
    density, cut = pedpy.compute_voronoi_density(individual_voronoi_data=cells, measurement_area=area)
    vspeed = pedpy.compute_voronoi_speed(traj_data=inside, individual_speed=speed,
                                         individual_voronoi_intersection=cut, measurement_area=area)
    fd = density.merge(vspeed, on="frame")
    fd = fd[fd[pedpy.DENSITY_COL] > 0]
    return fd[[pedpy.DENSITY_COL, pedpy.SPEED_COL]].to_numpy()


def binned_speed(samples):
    idx = np.digitize(samples[:, 0], DENSITY_BINS) - 1
    out = {}
    for i in range(len(DENSITY_BINS) - 1):
        v = samples[idx == i, 1]
        if len(v) >= MIN_BIN_SAMPLES:
            out[round(float(DENSITY_BINS[i] + 0.125), 3)] = (float(v.mean()), len(v))
    return out


# --- per dataset -------------------------------------------------------------------

def run_dataset(kind, args, cfg, out_dir):
    runs = list(bottleneck_runs() if kind == "bottleneck" else corridor_runs())
    if args.runs:
        runs = [r for r in runs if r[0] in args.runs]
    setup = bottleneck_setup if kind == "bottleneck" else corridor_setup
    fps = 25 if kind == "bottleneck" else 16
    sim_dir = out_dir / "sim"
    sim_dir.mkdir(parents=True, exist_ok=True)
    rows, nt, fd_real, fd_sim = [], {}, [], []
    for name, run, path in runs:
        t0 = time.time()
        real = load_real(path, fps)
        sims, stuck = [], []
        for seed in range(args.seeds):
            rng = np.random.default_rng(seed)
            walk, start, goal, info = setup(run, rng)
            f = sim_dir / f"{name}_s{seed}.sqlite"
            if not (args.reuse and f.exists()):
                f.unlink(missing_ok=True)
                stuck.append(simulate(walk, start, goal, fps, f, cfg, rng))
            sims.append(pedpy.load_trajectory_from_jupedsim_sqlite(trajectory_file=f))
            if not args.keep_sim:
                f.unlink()  # a full run's trajectories take gigabytes
        row = {"run": name, "n": run["number_participants"], "width_m": info["width_m"], "stuck": stuck}
        if kind == "bottleneck":
            j_real, t_real = bottleneck_flow(real, info["line"])
            flows = [bottleneck_flow(s, info["line"]) for s in sims]
            j_sim = np.array([j for j, _ in flows])
            err = j_sim.mean() / j_real - 1
            # Agents still inside after MAX_SIM_S means a permanent clog: real crowds do not do that.
            deadlock = any(stuck)
            row.update({"flow_real_ps": round(j_real, 3), "flow_sim_ps": round(float(j_sim.mean()), 3),
                        "flow_sim_sd": round(float(j_sim.std()), 3), "error": round(float(err), 3),
                        "deadlock": deadlock, "pass": bool(abs(err) <= TOLERANCE and not deadlock)})
            nt[name] = (info["width_m"], t_real, flows[0][1])
            print(f"{name}: b={info['width_m']} m  real {j_real:.2f}/s  sim {j_sim.mean():.2f}±{j_sim.std():.2f}/s "
                  f"({err:+.0%}){'  DEADLOCK' if deadlock else ''}  {time.time() - t0:.0f}s", flush=True)
        else:
            r = corridor_fd(real, info["width_m"])
            s = np.vstack([corridor_fd(x, info["width_m"]) for x in sims])
            fd_real.append(r)
            fd_sim.append(s)
            row.update({"samples_real": len(r), "samples_sim": len(s),
                        "max_density_real": round(float(r[:, 0].max()), 2) if len(r) else None,
                        "max_density_sim": round(float(s[:, 0].max()), 2) if len(s) else None})
            print(f"{name}: real {len(r)} samples (max {row['max_density_real']}/m²), "
                  f"sim {len(s)} (max {row['max_density_sim']}/m²)  {time.time() - t0:.0f}s", flush=True)
        rows.append(row)
    if kind == "bottleneck":
        return summarize_bottleneck(rows, nt, cfg, out_dir)
    return summarize_corridor(rows, np.vstack(fd_real), np.vstack(fd_sim), out_dir)


def summarize_bottleneck(rows, nt, cfg, out_dir):
    b = np.array([r["width_m"] for r in rows])
    jr = np.array([r["flow_real_ps"] for r in rows])
    js = np.array([r["flow_sim_ps"] for r in rows])
    # Specific flow: least-squares slope of J = cs * b through the origin.
    cs_real, cs_sim = float(b @ jr / (b @ b)), float(b @ js / (b @ b))

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(b, jr, "ko", label="Jülich (real)")
    ax.errorbar(b, js, yerr=[r["flow_sim_sd"] for r in rows], fmt="s", color="tab:orange", capsize=3,
                label="JuPedSim (mean ± sd)")
    bb = np.linspace(0, b.max() * 1.05, 50)
    ax.fill_between(bb, bb * cs_real * (1 - TOLERANCE), bb * cs_real * (1 + TOLERANCE), color="grey",
                    alpha=0.15, label="real fit ±15%")
    ax.plot(bb, bb * cfg["capacity"]["specific_flow_pms"], "--", color="tab:blue",
            label=f"config capacity {cfg['capacity']['specific_flow_pms']} /m/s")
    ax.set_xlabel("bottleneck width b [m]")
    ax.set_ylabel("flow J [people/s]")
    ax.set_title("Flow through the bottleneck: real vs simulated")
    ax.legend()
    fig.savefig(out_dir / "flow_vs_width.png", dpi=110, bbox_inches="tight")

    fig, ax = plt.subplots(figsize=(7, 5))
    for i, (name, (w, tr, ts)) in enumerate(sorted(nt.items(), key=lambda kv: kv[1][0])):
        c = plt.cm.viridis(i / max(len(nt) - 1, 1))
        ax.plot(tr, np.arange(1, len(tr) + 1), color=c, label=f"b={w} m")
        ax.plot(ts, np.arange(1, len(ts) + 1), color=c, ls="--")
    ax.set_xlabel("time since first crossing [s]")
    ax.set_ylabel("people passed")
    ax.set_title("N-t at the bottleneck: real (solid) vs simulated seed 0 (dashed)")
    ax.legend(fontsize=7, ncol=2)
    fig.savefig(out_dir / "nt_curves.png", dpi=110, bbox_inches="tight")

    errs = np.array([r["error"] for r in rows])
    return {"runs": rows, "specific_flow_real_pms": round(cs_real, 3), "specific_flow_sim_pms": round(cs_sim, 3),
            "config_specific_flow_pms": cfg["capacity"]["specific_flow_pms"],
            "mean_abs_error": round(float(np.abs(errs).mean()), 3), "max_abs_error": round(float(np.abs(errs).max()), 3),
            "widths_passing": int(sum(r["pass"] for r in rows)), "widths_total": len(rows),
            "pass": bool(all(r["pass"] for r in rows))}


def summarize_corridor(rows, real, sim, out_dir):
    br, bs = binned_speed(real), binned_speed(sim)
    common = sorted(d for d in set(br) & set(bs) if d >= MIN_FD_DENSITY)
    diffs = {d: round(bs[d][0] / br[d][0] - 1, 3) for d in common}

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(real[:, 0], real[:, 1], s=2, color="black", alpha=0.15, label="Jülich (real)")
    ax.scatter(sim[:, 0], sim[:, 1], s=2, color="tab:orange", alpha=0.08, label="JuPedSim")
    ax.plot(list(br), [v[0] for v in br.values()], "k-o", ms=3, label="real, mean per bin")
    ax.plot(list(bs), [v[0] for v in bs.values()], "-s", color="tab:orange", ms=3, label="sim, mean per bin")
    ax.set_xlabel("Voronoi density [people/m²]")
    ax.set_ylabel("Voronoi speed [m/s]")
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 2)
    ax.set_title("Speed–density, unidirectional corridor")
    ax.legend(markerscale=4)
    fig.savefig(out_dir / "speed_density.png", dpi=110, bbox_inches="tight")

    return {"runs": rows, "bins": [{"density": d, "speed_real": round(br[d][0], 3), "speed_sim": round(bs[d][0], 3),
                                    "n_real": br[d][1], "n_sim": bs[d][1], "error": diffs[d]} for d in common],
            "mean_abs_error": round(float(np.mean(np.abs(list(diffs.values())))), 3) if diffs else None,
            "max_density_real": round(float(real[:, 0].max()), 2), "max_density_sim": round(float(sim[:, 0].max()), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["bottleneck", "corridor", "all"], default="all")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--runs", nargs="*", help="only these run names, e.g. b100 uo-180-180-180")
    ap.add_argument("--set", nargs="*", default=[], help="config overrides, e.g. agents.time_gap_s=0.8")
    ap.add_argument("--keep-sim", action="store_true", help="keep simulated trajectories (SQLite) after analysis")
    ap.add_argument("--reuse", action="store_true", help="reuse kept simulated trajectories (needs --keep-sim)")
    ap.add_argument("--name", default="baseline")
    args = ap.parse_args()
    cfg = apply_overrides(config.load(), args.set)
    out = ROOT / "out" / "validation" / args.name
    out.mkdir(parents=True, exist_ok=True)

    summary = {"model": cfg["model"], "agents": cfg["agents"], "overrides": args.set, "seeds": args.seeds,
               "tolerance": TOLERANCE, "start_density_ppm2": START_DENSITY}
    for kind in (["bottleneck", "corridor"] if args.dataset == "all" else [args.dataset]):
        summary[kind] = run_dataset(kind, args, cfg, out)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    if "bottleneck" in summary:
        s = summary["bottleneck"]
        print(f"bottleneck: {s['widths_passing']}/{s['widths_total']} widths within ±{TOLERANCE:.0%}, "
              f"mean |error| {s['mean_abs_error']:.0%}; specific flow real {s['specific_flow_real_pms']} "
              f"sim {s['specific_flow_sim_pms']} /m/s")
    if "corridor" in summary and summary["corridor"]["mean_abs_error"] is not None:
        print(f"corridor: mean |speed error| per density bin (>= {MIN_FD_DENSITY}/m²) "
              f"{summary['corridor']['mean_abs_error']:.0%}")


if __name__ == "__main__":
    main()
