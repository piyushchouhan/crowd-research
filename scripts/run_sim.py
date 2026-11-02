"""Simulate pilgrims walking to and from the Sangam nose bathing ghat.

Inbound people enter at the inbound gates and walk to the bathing goal at the
nose tip (reaching it = bathing, they leave the simulation). After bathing_min,
a share of them (--outflow-frac) reappear on the ghat and walk out through an
outbound gate. With routing one_way (config) the two directions use different
gates, since the model is not validated for dense counter-flow.

Writes out/<name>/snapshots.npz (positions and direction every second) and run.json.
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
ROUTING = CFG["routing"]
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
    ap.add_argument("--outflow-frac", type=float, default=0.6,
                    help="share of bathers who walk back out through the area")
    ap.add_argument("--routing", choices=["one_way", "two_way"], default=ROUTING["mode"])
    ap.add_argument("--gate-weights", type=float, nargs="*", default=GATE_WEIGHTS,
                    help="inbound share per gate G0..G5 (renormalised over the inbound gates)")
    ap.add_argument("--minutes", type=float, default=45)
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
    if len(args.gate_weights) != len(gates):
        raise SystemExit(f"gate weights have {len(args.gate_weights)} entries but the hotspot has {len(gates)} gates")
    if args.routing == "one_way":
        in_gates, out_gates = ROUTING["inbound_gates"], ROUTING["outbound_gates"]
    else:
        in_gates = out_gates = list(range(len(gates)))
    weights = np.array([w if i in in_gates else 0 for i, w in enumerate(args.gate_weights)], dtype=float)
    weights /= weights.sum()

    # Inbound demand per gate against its free-flow capacity (width x specific flow).
    # Over capacity is allowed: queues and backlog are what we want to see.
    gate_load = []
    for i, (w, cap) in enumerate(zip(weights, hs["gate_capacity"])):
        if not w:
            continue
        demand = args.inflow * w
        gate_load.append({"gate": i, "demand_ppm": round(demand), "capacity_ppm": cap["capacity_ppm"],
                          "load": round(demand / cap["capacity_ppm"], 2)})
        print(f"G{i}: demand {demand:6.0f}/min vs capacity {cap['capacity_ppm']:5d}/min "
              f"({demand / cap['capacity_ppm']:.0%}){'  OVER' if demand > cap['capacity_ppm'] else ''}")

    sim = jps.Simulation(model=jps.CollisionFreeSpeedModel(**CFG["model"]), geometry=walk, dt=args.dt)
    goal_id = sim.add_exit_stage(goal)
    in_journey = sim.add_journey(jps.JourneyDescription([goal_id]))
    # JuPedSim exits must be convex: use the largest circle that fits inside each gate.
    gate_ids = []
    for g in gates:
        centre, edge = shapely.get_coordinates(shapely.maximum_inscribed_circle(g))
        gate_ids.append(sim.add_exit_stage(shapely.Point(centre).buffer(0.9 * np.linalg.norm(edge - centre), 8)))
    out_journeys = [sim.add_journey(jps.JourneyDescription([gid])) for gid in gate_ids]

    in_rate = args.inflow / 60 * weights                        # people/s per gate
    backlog_in = np.zeros(len(gates))
    backlog_out = 0                                             # bathed, waiting to step onto the ghat
    returns = []                                                # times (s) when bathers start back
    bathe_s = ROUTING["bathing_min"] * 60
    steps = int(args.minutes * 60 / args.dt)
    per_second = int(round(1 / args.dt))

    frames, frame_ids, frame_out, series = [], [], [], []
    added_in = added_out = bathed = 0
    inbound = set()                                             # ids of inbound agents still walking
    t0 = time.time()

    def positions():
        return np.array([a.position for a in sim.agents()]).reshape(-1, 2)

    def place(poly, n, pos, journey, stage, ids=None):
        placed = 0
        if n <= 0:
            return 0
        for p in random_points(poly, n * 3, rng):
            if placed >= n:
                break
            if len(pos) and np.min(np.sum((pos - p) ** 2, axis=1)) < MIN_SPAWN_GAP_M ** 2:
                continue
            try:
                aid = sim.add_agent(jps.CollisionFreeSpeedModelAgentParameters(
                    journey_id=journey, stage_id=stage, position=tuple(p),
                    desired_speed=float(np.clip(rng.normal(SPEED["mean"], SPEED["sd"]), SPEED["min"], SPEED["max"])),
                    radius=AGENT_RADIUS_M, time_gap=CFG["agents"]["time_gap_s"]))
            except RuntimeError:
                continue
            if ids is not None:
                ids.add(aid)
            pos = np.vstack([pos, p])
            placed += 1
        return placed

    for step in range(steps):
        if step % per_second == 0:
            # Arrivals for the next second; whoever cannot fit waits outside (backlog).
            backlog_in += rng.poisson(in_rate)
            now = sim.elapsed_time()
            backlog_out += sum(t <= now for t in returns)
            returns = [t for t in returns if t > now]
            pos = positions()
            for i, g in enumerate(gates):
                n = place(g, int(backlog_in[i]), pos, in_journey, goal_id, inbound)
                backlog_in[i] -= n
                added_in += n
                pos = positions() if n else pos
            k = int(rng.choice(out_gates))
            n = place(ghat, backlog_out, pos, out_journeys[k], gate_ids[k])
            backlog_out -= n
            added_out += n

            ids = np.array([a.id for a in sim.agents()], dtype=np.int64)
            frames.append(positions().astype(np.float32))
            frame_ids.append(ids)
            frame_out.append(np.array([a not in inbound for a in ids], dtype=bool))
            series.append({"t": round(now), "agents": int(sim.agent_count()),
                           "backlog_in": int(backlog_in.sum()), "backlog_out": int(backlog_out),
                           "added_in": added_in, "added_out": added_out, "bathed": bathed})
            if step % (60 * per_second) == 0:
                print(f"t={sim.elapsed_time():5.0f}s agents={sim.agent_count():6d} "
                      f"waiting_outside={int(backlog_in.sum()):6d} bathed={bathed:6d} out={added_out:6d} "
                      f"wall={time.time() - t0:5.0f}s", flush=True)
        sim.iterate()
        # Inbound agents removed at the goal have bathed; some walk back out after bathing_min.
        for aid in sim.removed_agents():
            if aid in inbound:
                inbound.discard(aid)
                bathed += 1
                if rng.random() < args.outflow_frac:
                    returns.append(sim.elapsed_time() + bathe_s)

    np.savez_compressed(out / "snapshots.npz",
                        offsets=np.cumsum([0] + [len(f) for f in frames]),
                        xy=np.concatenate(frames), ids=np.concatenate(frame_ids),
                        outbound=np.concatenate(frame_out))
    run = {"args": vars(args), "gate_weights": weights.tolist(), "routing": ROUTING, "agent_radius_m": AGENT_RADIUS_M,
           "model": "CollisionFreeSpeedModel", "wall_seconds": round(time.time() - t0, 1),
           "model_params": CFG["model"], "agents": CFG["agents"], "gate_load": gate_load,
           "assumptions": hs["assumptions"], "series": series}
    (out / "run.json").write_text(json.dumps(run))
    print(f"done {name}: wall {run['wall_seconds']}s, peak agents {max(s['agents'] for s in series)}")


if __name__ == "__main__":
    main()
