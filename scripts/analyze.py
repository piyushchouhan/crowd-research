"""Turn a simulation run into crowd-safety numbers and pictures.

Per 4 m grid cell and per second: density (people/m2 of walkable ground),
mean speed, and Helbing's crowd pressure = density x speed variance.
Writes out/<name>/metrics.json and three PNGs.
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shapely
from shapely.geometry import box, shape

from plot_hotspot import background, outline

import config

ROOT = config.ROOT
_A = config.load()["analysis"]
CELL_M = _A["cell_m"]
MIN_WALKABLE_M2 = _A["min_walkable_m2"]  # ignore cells that are mostly wall/water
DENSE = _A["dense_ppm2"]                 # people/m2: free walking stops
CRITICAL = _A["critical_ppm2"]           # people/m2: crush risk


def main(name):
    run_dir = ROOT / "out" / name
    hs = json.load(open(ROOT / "data/hotspot/sangam_nose.json"))
    walk = shape(hs["walkable"])
    snap = np.load(run_dir / "snapshots.npz")
    off, xy, ids = snap["offsets"], snap["xy"], snap["ids"]
    run = json.load(open(run_dir / "run.json"))

    x0, y0, x1, y1 = walk.bounds
    nx, ny = int(np.ceil((x1 - x0) / CELL_M)), int(np.ceil((y1 - y0) / CELL_M))
    cells = [box(x0 + i * CELL_M, y0 + j * CELL_M, x0 + (i + 1) * CELL_M, y0 + (j + 1) * CELL_M)
             for j in range(ny) for i in range(nx)]
    area = shapely.area(shapely.intersection(cells, walk)).reshape(ny, nx)
    valid = area >= MIN_WALKABLE_M2

    max_density = np.zeros((ny, nx))
    seconds_dense = np.zeros((ny, nx))
    max_pressure = np.zeros((ny, nx))
    series = []
    prev = {}
    for t in range(len(off) - 1):
        p, pid = xy[off[t]:off[t + 1]], ids[off[t]:off[t + 1]]
        i = np.clip(((p[:, 0] - x0) // CELL_M).astype(int), 0, nx - 1)
        j = np.clip(((p[:, 1] - y0) // CELL_M).astype(int), 0, ny - 1)
        count = np.zeros((ny, nx))
        np.add.at(count, (j, i), 1)
        dens = np.where(valid, count / np.maximum(area, 1e-9), 0)

        # Speed from the 1 s displacement of agents seen in both frames.
        speed = np.full(len(p), np.nan)
        for k, a in enumerate(pid):
            q = prev.get(a)
            if q is not None:
                speed[k] = np.hypot(*(p[k] - q))
        prev = dict(zip(pid, p))
        has = ~np.isnan(speed)
        s1, s2, n = (np.zeros((ny, nx)) for _ in range(3))
        np.add.at(s1, (j[has], i[has]), speed[has])
        np.add.at(s2, (j[has], i[has]), speed[has] ** 2)
        np.add.at(n, (j[has], i[has]), 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean_v = s1 / n
            var_v = np.maximum(s2 / n - mean_v ** 2, 0)
        pressure = np.where((n >= 3) & valid, dens * np.nan_to_num(var_v), 0)

        max_density = np.maximum(max_density, dens)
        max_pressure = np.maximum(max_pressure, pressure)
        seconds_dense += dens >= DENSE
        occupied = dens[valid & (count > 0)]
        series.append({
            "t": t,
            "agents": int(len(p)),
            "max_density": float(dens.max()),
            "p99_density": float(np.percentile(occupied, 99)) if occupied.size else 0.0,
            "cells_dense": int((dens >= DENSE).sum()),
            "cells_critical": int((dens >= CRITICAL).sum()),
            "max_pressure": float(pressure.max()),
            "median_speed": float(np.nanmedian(speed)) if has.any() else None,
        })

    peak_t = int(np.argmax([s["cells_dense"] for s in series]))
    jmax, imax = np.unravel_index(np.argmax(max_density), max_density.shape)
    sim_series = run["series"]
    metrics = {
        "run": name, "args": run["args"], "cell_m": CELL_M,
        "peak_agents": max(s["agents"] for s in series),
        "max_density": float(max_density.max()),
        "max_density_at_local_xy": [float(x0 + (imax + 0.5) * CELL_M), float(y0 + (jmax + 0.5) * CELL_M)],
        "first_t_dense": next((s["t"] for s in series if s["cells_dense"]), None),
        "first_t_critical": next((s["t"] for s in series if s["cells_critical"]), None),
        "peak_cells_dense": series[peak_t]["cells_dense"],
        "peak_area_dense_m2": float(area[(max_density >= DENSE)].sum()),
        "max_pressure": float(max_pressure.max()),
        "entered_inbound": sim_series[-1]["added_in"],
        "waiting_outside_end": sim_series[-1]["backlog_in"],
        "series": series,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics))

    # 1. Map of the worst density each cell reached.
    fig, ax = plt.subplots(figsize=(9, 11))
    background(ax, hs, walk)
    shown = np.ma.masked_where(~valid | (max_density < 0.5), max_density)
    im = ax.imshow(shown, origin="lower", extent=(x0, x0 + nx * CELL_M, y0, y0 + ny * CELL_M),
                   cmap="inferno", vmin=0, vmax=8, alpha=0.85)
    outline(ax, walk, color="white", lw=0.5)
    fig.colorbar(im, ax=ax, shrink=0.6, label="max density (people/m²)")
    ax.set_title(f"{name}: worst density per 4 m cell over {len(series) // 60} min")
    fig.savefig(run_dir / "max_density.png", dpi=80, bbox_inches="tight")
    plt.close(fig)

    # 2. Time series.
    t = [s["t"] / 60 for s in series]
    fig, axs = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
    axs[0].plot(t, [s["agents"] for s in series], label="people in area")
    axs[0].plot(t, [s["backlog_in"] for s in sim_series[:len(t)]], label="waiting outside gates")
    axs[0].legend(); axs[0].set_ylabel("people")
    axs[1].plot(t, [s["max_density"] for s in series], label="max cell")
    axs[1].plot(t, [s["p99_density"] for s in series], label="99th pct occupied cell")
    axs[1].axhline(DENSE, color="orange", ls="--"); axs[1].axhline(CRITICAL, color="red", ls="--")
    axs[1].legend(); axs[1].set_ylabel("people/m²")
    axs[2].plot(t, [s["cells_dense"] for s in series], color="orange", label=f"cells ≥ {DENSE}/m²")
    axs[2].plot(t, [s["cells_critical"] for s in series], color="red", label=f"cells ≥ {CRITICAL}/m²")
    axs[2].legend(); axs[2].set_ylabel("cells"); axs[2].set_xlabel("minutes")
    fig.suptitle(name)
    fig.savefig(run_dir / "timeseries.png", dpi=80, bbox_inches="tight")
    plt.close(fig)

    # 3. Snapshot of everyone at the worst moment, coloured by speed.
    p = xy[off[peak_t]:off[peak_t + 1]]
    pid = ids[off[peak_t]:off[peak_t + 1]]
    q = xy[off[max(peak_t - 1, 0)]:off[max(peak_t, 1)]]
    qid = ids[off[max(peak_t - 1, 0)]:off[max(peak_t, 1)]]
    lookup = dict(zip(qid, q))
    v = np.array([np.hypot(*(a - lookup[k])) if k in lookup else np.nan for k, a in zip(pid, p)])
    fig, ax = plt.subplots(figsize=(9, 11))
    background(ax, hs, walk)
    sc = ax.scatter(p[:, 0], p[:, 1], c=v, s=0.6, cmap="RdYlGn", vmin=0, vmax=1.4)
    fig.colorbar(sc, ax=ax, shrink=0.6, label="speed (m/s)")
    ax.set_title(f"{name}: t = {peak_t // 60}:{peak_t % 60:02d}, {len(p)} people")
    fig.savefig(run_dir / "peak_snapshot.png", dpi=80, bbox_inches="tight")
    plt.close(fig)

    print(json.dumps({k: v for k, v in metrics.items() if k != "series"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
