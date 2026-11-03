"""Synthetic phone pings from a simulation run (Phase 4).

A random share of the simulated people carry a phone. Each phone reports its
position every interval_s seconds (random phase per phone), with GPS error
(Gaussian per axis, a few large outliers), some reports lost, and positions
off the walkable area snapped back onto it. Settings in config/sim.json -> pings.

Phones are drawn with one uniform number per person, so for the same draw the
1% phones are a subset of the 2% phones, and those of the 5% phones.

Run as a script to write one set of pings: out/<run>/pings_<share>_<interval>_<sigma>.npz
"""
import argparse
import json

import numpy as np
import shapely
from shapely.geometry import shape

import config

ROOT = config.ROOT
P = config.load()["pings"]


class Run:
    """Snapshots of one run: every person's position each second."""

    def __init__(self, name):
        snap = np.load(ROOT / "out" / name / "snapshots.npz")
        self.name = name
        self.off = snap["offsets"]
        self.xy = snap["xy"]
        self.ids = snap["ids"]
        self.t = np.repeat(np.arange(len(self.off) - 1), np.diff(self.off)).astype(np.int32)
        self.seconds = len(self.off) - 1
        hs = json.load(open(ROOT / "data/hotspot/sangam_nose.json"))
        self.walk = shape(hs["walkable"])
        shapely.prepare(self.walk)


def phone_rows(run, max_share, interval, rng):
    """Rows (person-seconds) at which a phone reports, for the largest share.

    Returns row indices and each row's uniform number u: a row belongs to share p if u < p.
    """
    people = np.unique(run.ids)
    u = rng.random(len(people))
    phase = rng.integers(0, interval, len(people))
    k = np.searchsorted(people, run.ids)
    keep = (u[k] < max_share) & ((run.t - phase[k]) % interval == 0)
    rows = np.nonzero(keep)[0]
    rows = rows[rng.random(len(rows)) >= P["dropout_frac"]]
    return rows, u[k[rows]]


def gps(run, rows, sigma, rng):
    """Observed positions: true position + GPS error, snapped onto the walkable area."""
    err = rng.normal(0, sigma, (len(rows), 2))
    out = rng.random(len(rows)) < P["outlier_frac"]
    err[out] *= P["outlier_scale"]
    xy = run.xy[rows].astype(np.float64) + err
    off_walk = ~shapely.contains_xy(run.walk, xy[:, 0], xy[:, 1])
    if off_walk.any():
        lines = shapely.shortest_line(shapely.points(xy[off_walk]), run.walk)
        xy[off_walk] = shapely.get_coordinates(lines)[1::2]
    return xy


def draw(run, shares, interval, sigmas, seed):
    """Pings for every share and GPS error of one draw.

    Yields (share, sigma, pings) with pings = dict(t, phone, x, y), sorted by time.
    """
    rng = np.random.default_rng(seed)
    rows, u = phone_rows(run, max(shares), interval, rng)
    for sigma in sigmas:
        xy = gps(run, rows, sigma, rng)
        for share in shares:
            m = u < share
            yield share, sigma, {"t": run.t[rows[m]], "phone": run.ids[rows[m]],
                                 "x": xy[m, 0], "y": xy[m, 1], "share": share,
                                 "interval": interval, "sigma": sigma}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--share", type=float, default=0.02)
    ap.add_argument("--interval", type=int, default=15)
    ap.add_argument("--sigma", type=float, default=10)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    run = Run(args.run)
    (_, _, p), = draw(run, [args.share], args.interval, [args.sigma], args.seed)
    path = ROOT / "out" / args.run / f"pings_{args.share}_{args.interval}_{args.sigma:g}.npz"
    np.savez_compressed(path, **p)
    print(f"{len(p['t'])} pings from {len(np.unique(p['phone']))} phones -> {path}")


if __name__ == "__main__":
    main()
