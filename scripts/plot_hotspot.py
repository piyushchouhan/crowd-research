"""Draw the hotspot walkable area over the Sentinel-2 image (sanity check)."""
import json, subprocess
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
TIF = "/Users/piyushchauhan/Documents/ChatGPT/Crowd Control/sangam-command/data/prayagraj_sangam_2025-01-27.tif"


def background(ax, hs, walk):
    ox, oy = hs["origin_utm44n"]
    x0, y0, x1, y1 = walk.bounds
    subprocess.run(["gdal_translate", "-q", "-projwin", str(ox + x0 - 50), str(oy + y1 + 50), str(ox + x1 + 50), str(oy + y0 - 50),
                    "-of", "PNG", TIF, str(ROOT / "out/bg_hotspot.png")], check=True)
    ax.imshow(Image.open(ROOT / "out/bg_hotspot.png"), extent=(x0 - 50, x1 + 50, y0 - 50, y1 + 50))


def outline(ax, geom, **kw):
    for p in getattr(geom, "geoms", [geom]):
        ax.plot(*p.exterior.xy, **kw)
        for h in p.interiors:
            ax.plot(*h.xy, **kw)


if __name__ == "__main__":
    hs = json.load(open(ROOT / "data/hotspot/sangam_nose.json"))
    walk = shape(hs["walkable"])
    fig, ax = plt.subplots(figsize=(9, 11))
    background(ax, hs, walk)
    ax.add_patch(plt.Polygon(list(walk.exterior.coords), color="white", alpha=0.35))
    outline(ax, walk, color="white", lw=1)
    outline(ax, shape(hs["bathing_area"]), color="deepskyblue", lw=1.5)
    outline(ax, shape(hs["goal"]), color="lime", lw=2)
    for i, g in enumerate(hs["gates"]):
        g = shape(g); outline(ax, g, color="red", lw=2)
        ax.text(g.centroid.x, g.centroid.y, f"G{i}", color="red", weight="bold")
    ax.set_title("Walkable area (white), bathing zone (blue), goal (green), gates (red)")
    fig.savefig(ROOT / "out/hotspot_walkable.png", dpi=80, bbox_inches="tight")
