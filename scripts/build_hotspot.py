"""Build the walkable area around the Sangam nose for JuPedSim.

Reads the Sentinel-traced layers from the Sangam Command map project and writes
data/hotspot/sangam_nose.json in local metres (UTM 44N minus an origin).

Each corridor uses its own width from the map (approx_width_m, with width_source
saying where it came from). Features without one fall back to default_width_m in
config/sim.json; width_override_m forces a width for a whole kind. Capacity is
width x specific_flow_pms (free flow, ~1.3 people/m/s).
"""
import json
from pathlib import Path

import numpy as np
import shapely
import shapely.affinity
from pyproj import Transformer
from shapely.geometry import box, mapping, shape

import config

OUT = Path(__file__).resolve().parent.parent / "data" / "hotspot"

_tr = Transformer.from_crs(4326, 32644, always_xy=True)


def to_utm(geom):
    return shapely.transform(geom, lambda c: np.column_stack(_tr.transform(c[:, 0], c[:, 1])))


def load(map_dir, name):
    feats = json.load(open(map_dir / "mela" / f"{name}.geojson"))["features"]
    return [(f["properties"], to_utm(shape(f["geometry"]))) for f in feats if f["geometry"]]


def width_of(props, kind, hcfg):
    """Width in metres and where it came from: override > map > default."""
    if hcfg["width_override_m"].get(kind) is not None:
        return hcfg["width_override_m"][kind], "config_override"
    if props.get("approx_width_m") is not None:
        return float(props["approx_width_m"]), props.get("width_source") or "map"
    return hcfg["default_width_m"][kind], "config_default"


def main():
    cfg = config.load()
    hcfg = cfg["hotspot"]
    map_dir = cfg["map_data_dir"]
    half = hcfg["half_window_m"]

    nose = load(map_dir, "sangam_nose")[0][1]
    win = box(nose.x - half, nose.y - 150, nose.x + half + 100, nose.y + 2 * half - 150)
    river = shapely.union_all([g for _, g in load(map_dir, "river_banks")]).buffer(0)
    land = win.difference(river)

    # (id, kind, width, source, polygon) for every corridor inside the window.
    corridors = []
    for layer, kind in [("mela_roads", "mela_road"), ("pontoon_approaches", "approach")]:
        for props, line in load(map_dir, layer):
            if line.intersects(win):
                w, src = width_of(props, kind, hcfg)
                corridors.append((props["id"], kind, w, src, line.buffer(w / 2, cap_style="flat").intersection(land)))
    bathing = nose.buffer(hcfg["bathing_radius_m"]).intersection(land)

    # Pontoon decks cross the water, so they are not clipped by the river mask.
    # Extend each deck a little at both ends so it overlaps the bank corridors.
    ext_m = hcfg["pontoon_end_extension_m"]
    for props, line in load(map_dir, "pontoon_bridges"):
        if not line.intersects(win):
            continue
        a, b = shapely.get_coordinates(line)[[0, -1]]
        d = (b - a) / max(line.length, 1e-6)
        ext = shapely.LineString([a - d * ext_m, *shapely.get_coordinates(line)[1:-1], b + d * ext_m])
        w, src = width_of(props, "pontoon", hcfg)
        corridors.append((props["id"], "pontoon", w, src, ext.buffer(w / 2, cap_style="flat").intersection(win)))

    walk = shapely.union_all([c[4] for c in corridors] + [bathing]).buffer(0.5).buffer(-0.5).simplify(0.5)
    parts = sorted(getattr(walk, "geoms", [walk]), key=lambda p: p.area, reverse=True)
    walk = parts[0]  # one connected walkable area; drop islands nothing can reach
    corridors = [c for c in corridors if c[4].intersects(walk)]

    # Where corridors cross the window edge, people enter and leave.
    edge = win.exterior.buffer(hcfg["spawn_depth_m"]).intersection(walk)
    gates = [g for g in getattr(edge, "geoms", [edge]) if g.area > 50]
    goal = nose.buffer(hcfg["goal_radius_m"]).intersection(walk)

    # A gate's capacity is that of the corridors feeding it (summed if several meet there).
    gate_info = []
    for g in gates:
        feeding = [c for c in corridors if c[4].intersection(g).area > 1]
        width = sum(c[2] for c in feeding)
        gate_info.append({"corridors": [c[0] for c in feeding], "width_m": width,
                          "capacity_ppm": round(config.capacity_ppm(width, cfg))})

    ox, oy = round(win.bounds[0]), round(win.bounds[1])
    local = lambda g: shapely.affinity.translate(g, -ox, -oy)
    OUT.mkdir(parents=True, exist_ok=True)
    out = {
        "origin_utm44n": [ox, oy],
        "assumptions": {"hotspot": hcfg, "capacity": cfg["capacity"],
                        "source": "Sangam Command traced layers, Sentinel-2 2025-01-27; widths from map approx_width_m"},
        "walkable": mapping(local(walk)),
        "bathing_area": mapping(local(bathing.intersection(walk))),
        "goal": mapping(local(goal)),
        "gates": [mapping(local(g)) for g in gates],
        "gate_capacity": gate_info,
        "corridors": [{"id": i, "kind": k, "width_m": w, "width_source": s,
                       "capacity_ppm": round(config.capacity_ppm(w, cfg))} for i, k, w, s, _ in corridors],
        "pontoon_ids": [c[0] for c in corridors if c[1] == "pontoon"],
    }
    (OUT / "sangam_nose.json").write_text(json.dumps(out))
    print(f"walkable {walk.area / 1e4:.2f} ha, parts dropped {len(parts) - 1}, "
          f"corridors {len(corridors)}, pontoons {len(out['pontoon_ids'])}, goal {goal.area:.0f} m2, "
          f"bathing {bathing.area:.0f} m2, vertices {len(shapely.get_coordinates(walk))}")
    for i, gi in enumerate(gate_info):
        print(f"  G{i}: width {gi['width_m']:.1f} m, capacity {gi['capacity_ppm']} people/min, via {', '.join(gi['corridors'])}")


if __name__ == "__main__":
    main()
