import json, subprocess, sys
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
from pyproj import Transformer
from shapely.geometry import shape, box
from shapely.ops import transform

import config

MAP = config.load()["map_data_dir"]
to_utm = Transformer.from_crs(4326, 32644, always_xy=True).transform
def load(p):
    return [(f["properties"], transform(to_utm, shape(f["geometry"]))) for f in json.load(open(MAP / p))["features"] if f["geometry"]]

nose = load("mela/sangam_nose.geojson")[0][1]
half = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
win = box(nose.x - half, nose.y - half, nose.x + half, nose.y + half)
x0, y0, x1, y1 = win.bounds
subprocess.run(["gdal_translate", "-q", "-projwin", str(x0), str(y1), str(x1), str(y0), "-of", "PNG",
                str(MAP.parent / "data/prayagraj_sangam_2025-01-27.tif"), "out/bg.png"], check=True)
fig, ax = plt.subplots(figsize=(11, 11))
ax.imshow(Image.open("out/bg.png"), extent=(x0, x1, y0, y1))
def draw(p, color, lw=1, label=None):
    for props, g in load(p):
        g = g.intersection(win)
        if g.is_empty: continue
        for part in getattr(g, "geoms", [g]):
            if part.geom_type == "Polygon":
                ax.plot(*part.exterior.xy, color=color, lw=lw)
                if label: ax.text(part.centroid.x, part.centroid.y, str(props.get(label)), color=color, fontsize=9, weight="bold")
            elif part.geom_type == "LineString":
                ax.plot(*part.xy, color=color, lw=lw)
                if label: ax.text(*part.interpolate(0.5, normalized=True).coords[0], str(props.get(label))[-2:], color=color, fontsize=7)
draw("mela/river_banks.geojson", "cyan")
draw("mela/sectors.geojson", "yellow", 1.2, "number")
draw("mela/mela_roads.geojson", "orange", 1.5)
draw("mela/pontoon_approaches.geojson", "magenta", 1)
draw("mela/pontoon_bridges.geojson", "red", 2.5, "id")
ax.plot(nose.x, nose.y, "w*", ms=18)
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_title(f"Sangam nose ±{half} m (UTM 44N)")
fig.savefig("out/hotspot_peek.png", dpi=90, bbox_inches="tight")
print("nose utm", round(nose.x), round(nose.y))
