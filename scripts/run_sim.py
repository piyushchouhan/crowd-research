"""Simulate pilgrims walking to and from the Sangam nose bathing ghat.

Inbound people enter at the window gates and walk to the bathing goal at the
nose tip (reaching it = bathing, they leave the simulation). Outbound people
appear in the bathing area and walk back to a gate. Together they make the
counter-flow that turns dangerous at high density.

Writes out/<name>/snapshots.npz (positions every second) and run.json.
"""
import argparse
import json
import time

import jupedsim as jps
import numpy as np
import shapely
from shapely.geometry import shape

import config

ROOT = config.ROOT
CFG = config.load()
# Share of inbound arrivals per gate (G0..G5, see out/hotspot_walkable.png):
# G0/G1 east bank via pontoons, G2/G3 north lanes along the nose, G4/G5 city roads.
GATE_WEIGHTS = CFG["gate_weights"]
AGENT_RADIUS_M = CFG["agents"]["radius_m"]
MIN_SPAWN_GAP_M = CFG["agents"]["min_spawn_gap_m"]
SPEED = CFG["agents"]["desired_speed_mps"]


def random_points(poly, n, rng):
    x0, y0, x1, y1 = poly.bounds
    pts = np.empty((0, 2))
    while len(pts) < n:
        cand = rng.uniform((x0, y0), (x1, y1), size=(max(n * 4, 16), 2))
        pts = np.vstack([pts, cand[shapely.contains_xy(poly, cand[:, 0], cand[:, 1])]])
    return pts[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inflow", type=float, default=1500, help="inbound people per minute, all gates")
    ap.add_argument("--outflow-frac", type=float, default=0.6, help="outbound rate as a share of inflow")
    ap.add_argument("--minutes", type=float, default=20)
    ap.add_argument("--dt", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--name", default=None)
    args = ap.parse_args()
    name = args.name or f"in{int(args.inflow)}_out{int(args.outflow_frac * 100)}"
    out = ROOT / "out" / name
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    hs = json.load(open(ROOT / "data/hotspot/sangam_nose.json"))
    walk = shape(hs["walkable"])
    goal = shape(hs["goal"])
    gates = [shape(g) for g in hs["gates"]]
    # Outbound people start on the ghat, outside the goal circle itself.
    ghat = shape(hs["bathing_area"]).difference(goal.buffer(2)).buffer(-1)
    for g in [goal, ghat, *gates]:
        shapely.prepare(g)
    if len(GATE_WEIGHTS) != len(gates):
        raise SystemExit(f"config gate_weights has {len(GATE_WEIGHTS)} entries but the hotspot has {len(gates)} gates")

    # Inbound demand per gate against its free-flow capacity (width x specific flow).
    # Over capacity is allowed: queues and backlog are what we want to see.
    gate_load = []
    for i, (w, cap) in enumerate(zip(GATE_WEIGHTS, hs["gate_capacity"])):
        demand = args.inflow * w
        gate_load.append({"gate": i, "demand_ppm": round(demand), "capacity_ppm": cap["capacity_ppm"],
                          "load": round(demand / cap["capacity_ppm"], 2)})
        print(f"G{i}: demand {demand:6.0f}/min vs capacity {cap['capacity_ppm']:5d}/min "
              f"({demand / cap['capacity_ppm']:.0%}){'  OVER' if demand > cap['capacity_ppm'] else ''}")

    sim = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=walk, dt=args.dt)
    goal_id = sim.add_exit_stage(goal)
    in_journey = sim.add_journey(jps.JourneyDescription([goal_id]))
    # JuPedSim exits must be convex: use the largest circle that fits inside each gate.
    gate_ids = []
    for g in gates:
        centre, edge = shapely.get_coordinates(shapely.maximum_inscribed_circle(g))
        gate_ids.append(sim.add_exit_stage(shapely.Point(centre).buffer(0.9 * np.linalg.norm(edge - centre), 8)))
    out_journeys = [sim.add_journey(jps.JourneyDescription([gid])) for gid in gate_ids]

    in_rate = args.inflow / 60 * np.array(GATE_WEIGHTS)        # people/s per gate
    out_rate = args.inflow * args.outflow_frac / 60             # people/s from the ghat
    backlog_in = np.zeros(len(gates))
    backlog_out = 0.0
    steps = int(args.minutes * 60 / args.dt)
    per_second = int(round(1 / args.dt))

    frames, frame_ids, series = [], [], []
    added_in = added_out = 0
    t0 = time.time()

    def positions():
        return np.array([a.position for a in sim.agents()]).reshape(-1, 2)

    def place(poly, n, pos, journey, stage):
        placed = 0
        if n <= 0:
            return 0
        for p in random_points(poly, n * 3, rng):
            if placed >= n:
                break
            if len(pos) and np.min(np.sum((pos - p) ** 2, axis=1)) < MIN_SPAWN_GAP_M ** 2:
                continue
            try:
                sim.add_agent(jps.CollisionFreeSpeedModelAgentParameters(
                    journey_id=journey, stage_id=stage, position=tuple(p),
                    desired_speed=float(np.clip(rng.normal(SPEED["mean"], SPEED["sd"]), SPEED["min"], SPEED["max"])),
                    radius=AGENT_RADIUS_M))
            except RuntimeError:
                continue
            pos = np.vstack([pos, p])
            placed += 1
        return placed

    for step in range(steps):
        if step % per_second == 0:
            # Arrivals for the next second; whoever cannot fit waits outside (backlog).
            backlog_in += rng.poisson(in_rate)
            backlog_out += rng.poisson(out_rate)
            pos = positions()
            for i, g in enumerate(gates):
                n = place(g, int(backlog_in[i]), pos, in_journey, goal_id)
                backlog_in[i] -= n
                added_in += n
                pos = positions() if n else pos
            k = int(rng.integers(len(gates)))
            n = place(ghat, int(backlog_out), pos, out_journeys[k], gate_ids[k])
            backlog_out -= n
            added_out += n

            ids = np.array([a.id for a in sim.agents()], dtype=np.int64)
            frames.append(positions().astype(np.float32))
            frame_ids.append(ids)
            series.append({"t": round(sim.elapsed_time()), "agents": int(sim.agent_count()),
                           "backlog_in": int(backlog_in.sum()), "backlog_out": int(backlog_out),
                           "added_in": added_in, "added_out": added_out})
            if step % (60 * per_second) == 0:
                print(f"t={sim.elapsed_time():5.0f}s agents={sim.agent_count():6d} "
                      f"waiting_outside={int(backlog_in.sum()):6d} wall={time.time() - t0:5.0f}s", flush=True)
        sim.iterate()

    np.savez_compressed(out / "snapshots.npz",
                        offsets=np.cumsum([0] + [len(f) for f in frames]),
                        xy=np.concatenate(frames), ids=np.concatenate(frame_ids))
    run = {"args": vars(args), "gate_weights": GATE_WEIGHTS, "agent_radius_m": AGENT_RADIUS_M,
           "model": "CollisionFreeSpeedModel", "wall_seconds": round(time.time() - t0, 1),
           "agents": CFG["agents"], "gate_load": gate_load,
           "assumptions": hs["assumptions"], "series": series}
    (out / "run.json").write_text(json.dumps(run))
    print(f"done {name}: wall {run['wall_seconds']}s, peak agents {max(s['agents'] for s in series)}")


if __name__ == "__main__":
    main()
