"""Build the walkable area around the Sangam nose for JuPedSim.

Reads the Sentinel-traced layers from the Sangam Command map project and writes
data/hotspot/sangam_nose.json in local metres (UTM 44N minus an origin).

Widths are assumptions, not measurements: 10 m Sentinel-2 cannot resolve them.
Change them in WIDTHS_M and re-run.
"""
import json
from pathlib import Path

import numpy as np
import shapely
import shapely.affinity
from pyproj import Transformer
from shapely.geometry import box, mapping, shape

MAP = Path("/Users/piyushchauhan/Documents/ChatGPT/Crowd Control/sangam-command/data")
OUT = Path(__file__).resolve().parent.parent / "data" / "hotspot"

HALF_WINDOW_M = 600          # study window: nose +- this, east-shifted to include the far pontoon ends
WIDTHS_M = {
    "pontoon": 5.0,          # single-lane pontoon deck
    "mela_road": 15.0,       # main temporary road
    "approach": 25.0,        # bank margin lanes / ghat approaches
}
BATHING_RADIUS_M = 120       # land within this distance of the nose tip counts as the bathing ghat
SPAWN_DEPTH_M = 25           # strip along the window edge where people enter/leave

_tr = Transformer.from_crs(4326, 32644, always_xy=True)


def to_utm(geom):
    return shapely.transform(geom, lambda c: np.column_stack(_tr.transform(c[:, 0], c[:, 1])))


def load(name):
    feats = json.load(open(MAP / "mela" / f"{name}.geojson"))["features"]
    return [(f["properties"], to_utm(shape(f["geometry"]))) for f in feats if f["geometry"]]


def main():
    nose = load("sangam_nose")[0][1]
    win = box(nose.x - HALF_WINDOW_M, nose.y - 150, nose.x + HALF_WINDOW_M + 100, nose.y + 2 * HALF_WINDOW_M - 150)
    river = shapely.union_all([g for _, g in load("river_banks")]).buffer(0)
    land = win.difference(river)

    corridors = [g.buffer(WIDTHS_M["mela_road"] / 2, cap_style="flat") for _, g in load("mela_roads")]
    corridors += [g.buffer(WIDTHS_M["approach"] / 2, cap_style="flat") for _, g in load("pontoon_approaches")]
    bathing = nose.buffer(BATHING_RADIUS_M).intersection(land)
    on_land = shapely.union_all(corridors + [bathing]).intersection(land)

    # Pontoon decks cross the water, so they are not clipped by the river mask.
    # Extend each deck a little at both ends so it overlaps the bank corridors.
    pontoons, pontoon_ids = [], []
    for props, line in load("pontoon_bridges"):
        if not line.intersects(win):
            continue
        a, b = shapely.get_coordinates(line)[[0, -1]]
        d = (b - a) / max(line.length, 1e-6)
        ext = shapely.LineString([a - d * 15, *shapely.get_coordinates(line)[1:-1], b + d * 15])
        pontoons.append(ext.buffer(WIDTHS_M["pontoon"] / 2, cap_style="flat").intersection(win))
        pontoon_ids.append(props["id"])

    walk = shapely.union_all([on_land, *pontoons]).buffer(0.5).buffer(-0.5).simplify(0.5)
    parts = sorted(getattr(walk, "geoms", [walk]), key=lambda p: p.area, reverse=True)
    walk = parts[0]  # one connected walkable area; drop islands nothing can reach

    # Where corridors cross the window edge, people enter and leave.
    edge = win.exterior.buffer(SPAWN_DEPTH_M).intersection(walk)
    gates = [g for g in getattr(edge, "geoms", [edge]) if g.area > 50]
    goal = nose.buffer(40).intersection(walk)  # bathing edge at the tip

    ox, oy = round(win.bounds[0]), round(win.bounds[1])
    local = lambda g: shapely.affinity.translate(g, -ox, -oy)
    OUT.mkdir(parents=True, exist_ok=True)
    out = {
        "origin_utm44n": [ox, oy],
        "assumptions": {"widths_m": WIDTHS_M, "bathing_radius_m": BATHING_RADIUS_M,
                        "source": "Sangam Command traced layers, Sentinel-2 2025-01-27; widths assumed"},
        "walkable": mapping(local(walk)),
        "bathing_area": mapping(local(bathing.intersection(walk))),
        "goal": mapping(local(goal)),
        "gates": [mapping(local(g)) for g in gates],
        "pontoon_ids": pontoon_ids,
    }
    (OUT / "sangam_nose.json").write_text(json.dumps(out))
    print(f"walkable {walk.area / 1e4:.2f} ha, parts dropped {len(parts) - 1}, "
          f"gates {len(gates)}, pontoons {len(pontoons)}, goal {goal.area:.0f} m2, "
          f"bathing {bathing.area:.0f} m2, vertices {len(shapely.get_coordinates(walk))}")


if __name__ == "__main__":
    main()
