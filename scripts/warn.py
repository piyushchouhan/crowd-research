"""Can sparse phone pings warn of a jam before it forms? (Phase 4)

For one or more runs with saved snapshots:
1. Truth. Danger event = a 4 m cell at >= analysis.dense_ppm2 for event_hold_s in a row;
   a zone's onset is the earliest event in its cells. True zone density every eval step.
2. Pings from pings.py for every share x interval x GPS error, `draws` times.
3. Three warnings per zone, each evaluated every eval_step_s over the last window_s:
   - count: pings in zone x interval / (window x share x (1 - dropout)) / walkable area,
     alarm at >= alarm_density_ppm2 (needs the phone share, unknown in practice);
   - speed: median phone speed (straight-line distance between its first and last ping in
     the window, span >= min_speed_span_s), alarm below alarm_speed_mps (no share needed);
   - trend: linear fit of the count estimate over trend_window_s; alarm when it reaches
     dense_ppm2 within forecast_min (and is at least trend_min_ppm2 now).
   An alarm starts once its condition has held for alarm_hold_s.
4. Scores, per run and setting, over draws:
   - lead: minutes from the first alarm in the first event's zone (or a neighbour zone)
     to that event's onset; negative = late, None = never warned;
   - zone hits: share of event zones warned >= go.lead_min ahead (zone or neighbour);
   - false alarms: alarmed zones with no event in the zone or a neighbour;
   - density error: median |estimate - truth| / truth where the true zone density >= 1/m².
   "oracle": every person reports every 10 s with no GPS error, the best any phone could do.

Writes out/phase4/results.json and figures. Settings in config/sim.json -> pings, warning.
"""
import argparse
import json
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shapely
from shapely.geometry import box

import config
from pings import P, Run, draw

ROOT = config.ROOT
CFG = config.load()
W = CFG["warning"]
CELL_M = CFG["analysis"]["cell_m"]
DENSE = CFG["analysis"]["dense_ppm2"]
MIN_CELL_M2 = CFG["analysis"]["min_walkable_m2"]
METHODS = ["count", "speed", "trend"]


class Truth:
    """Cells, zones, event onsets and true zone densities for one run and zone size."""

    def __init__(self, run, zone_m, cell_first=None):
        k = int(round(zone_m / CELL_M))
        x0, y0, x1, y1 = run.walk.bounds
        self.x0, self.y0, self.zone_m = x0, y0, k * CELL_M
        nx, ny = int(np.ceil((x1 - x0) / CELL_M)), int(np.ceil((y1 - y0) / CELL_M))
        cells = [box(x0 + i * CELL_M, y0 + j * CELL_M, x0 + (i + 1) * CELL_M, y0 + (j + 1) * CELL_M)
                 for j in range(ny) for i in range(nx)]
        cell_area = shapely.area(shapely.intersection(cells, run.walk)).reshape(ny, nx)
        self.zx, self.zy = int(np.ceil(nx / k)), int(np.ceil(ny / k))
        jj, ii = np.mgrid[0:ny, 0:nx]
        cell_zone = (jj // k) * self.zx + ii // k
        nz = self.zx * self.zy
        self.area = np.bincount(cell_zone.ravel(), cell_area.ravel(), nz)
        self.valid = self.area >= W["min_zone_m2"]
        if cell_first is None:
            cell_first = event_onsets(run, x0, y0, nx, ny, cell_area)
        self.cell_first = cell_first
        onset = np.full(nz, np.inf)
        np.minimum.at(onset, cell_zone.ravel(), np.where(np.isnan(cell_first), np.inf, cell_first).ravel())
        self.onset = onset                                      # s; inf = no event
        self.times = np.arange(W["window_s"], run.seconds, W["eval_step_s"])
        self.density = np.array([np.bincount(self.zone_of(run.xy[run.off[t]:run.off[t + 1]]), minlength=nz)
                                 for t in self.times]) / np.maximum(self.area, 1e-9)
        # Neighbours: the zone itself and the 8 around it.
        z = np.arange(nz)
        zj, zi = z // self.zx, z % self.zx
        self.near = (np.abs(zj[:, None] - zj[None]) <= 1) & (np.abs(zi[:, None] - zi[None]) <= 1)

    def zone_of(self, xy):
        i = np.clip(((xy[:, 0] - self.x0) // self.zone_m).astype(int), 0, self.zx - 1)
        j = np.clip(((xy[:, 1] - self.y0) // self.zone_m).astype(int), 0, self.zy - 1)
        return j * self.zx + i


def event_onsets(run, x0, y0, nx, ny, cell_area):
    """Per 4 m cell, the start of its first spell at >= DENSE lasting event_hold_s (NaN if none)."""
    valid = cell_area >= MIN_CELL_M2
    run_start = np.full((ny, nx), -1)
    first = np.full((ny, nx), np.nan)
    for t in range(run.seconds):
        p = run.xy[run.off[t]:run.off[t + 1]]
        i = np.clip(((p[:, 0] - x0) // CELL_M).astype(int), 0, nx - 1)
        j = np.clip(((p[:, 1] - y0) // CELL_M).astype(int), 0, ny - 1)
        count = np.zeros((ny, nx))
        np.add.at(count, (j, i), 1)
        dense = (count / np.maximum(cell_area, 1e-9) >= DENSE) & valid
        run_start = np.where(dense, np.where(run_start < 0, t, run_start), -1)
        done = dense & np.isnan(first) & (t - run_start + 1 >= W["event_hold_s"])
        first[done] = run_start[done]
    return first


def estimate(truth, pings, window_s=W["window_s"]):
    """Per eval time and zone: count density estimate, median phone speed in the zone, and
    median phone speed over the zone and its 8 neighbours (NaN = too few phones)."""
    t, ph = pings["t"], pings["phone"]
    xy = np.column_stack([pings["x"], pings["y"]])
    zone = truth.zone_of(xy)
    nz = len(truth.area)
    scale = pings["interval"] / (window_s * pings["share"] * (1 - P["dropout_frac"]))
    dens = np.zeros((len(truth.times), nz))
    speed = np.full((len(truth.times), nz), np.nan)
    speed_nb = np.full((len(truth.times), nz), np.nan)
    for n, now in enumerate(truth.times):
        a, b = np.searchsorted(t, [now - window_s, now], side="right")
        if a == b:
            continue
        dens[n] = np.bincount(zone[a:b], minlength=nz) * scale / np.maximum(truth.area, 1e-9)
        # Per phone: first and last ping in the window.
        o = np.lexsort((t[a:b], ph[a:b])) + a
        p_sorted = ph[o]
        start = np.r_[True, p_sorted[1:] != p_sorted[:-1]]
        end = np.r_[start[1:], True]
        f, l = o[start], o[end]
        span = (t[l] - t[f]).astype(float)
        ok = span >= W["min_speed_span_s"]
        if not ok.any():
            continue
        v = np.hypot(*(xy[l[ok]] - xy[f[ok]]).T) / span[ok]
        zl = zone[l[ok]]
        speed[n] = zone_median(zl, v, nz)
        # Each phone also counts for the 8 zones around its own.
        zj, zi = zl // truth.zx, zl % truth.zx
        nb_z, nb_v = [], []
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                m = (zj + dj >= 0) & (zj + dj < truth.zy) & (zi + di >= 0) & (zi + di < truth.zx)
                nb_z.append((zj[m] + dj) * truth.zx + zi[m] + di)
                nb_v.append(v[m])
        speed_nb[n] = zone_median(np.concatenate(nb_z), np.concatenate(nb_v), nz)
    dens[:, ~truth.valid] = 0
    speed[:, ~truth.valid] = np.nan
    speed_nb[:, ~truth.valid] = np.nan
    return dens, speed, speed_nb


def zone_median(zones, v, nz):
    """Median of v per zone, NaN where fewer than min_phones_speed values."""
    out = np.full(nz, np.nan)
    order = np.argsort(zones)
    zones, v = zones[order], v[order]
    zs, first_idx, counts = np.unique(zones, return_index=True, return_counts=True)
    for z, i0, c in zip(zs, first_idx, counts):
        if c >= W["min_phones_speed"]:
            out[z] = np.median(v[i0:i0 + c])
    return out


def base_conditions(truth, dens):
    """Per eval time and zone: count above the alarm density, and trend reaching DENSE within forecast_min."""
    steps = W["trend_window_s"] // W["eval_step_s"]
    trend = np.zeros_like(dens, dtype=bool)
    x = np.arange(steps) * W["eval_step_s"]
    for n in range(steps - 1, len(truth.times)):
        y = dens[n - steps + 1:n + 1]
        slope = ((x - x.mean())[:, None] * (y - y.mean(0))).sum(0) / ((x - x.mean()) ** 2).sum()
        trend[n] = (dens[n] >= W["trend_min_ppm2"]) & (dens[n] + slope * W["forecast_min"] * 60 >= DENSE)
    return {"count": dens >= W["alarm_density_ppm2"], "trend": trend}


def first_held(truth, cond, hold_s):
    """First time (s) per zone at which cond has held for hold_s; inf = never."""
    hold = hold_s // W["eval_step_s"] + 1
    c = cond & truth.valid
    cs = np.cumsum(np.vstack([np.zeros((1, c.shape[1])), c]), axis=0)
    held = (cs[hold:] - cs[:-hold]) >= hold
    first = np.full(c.shape[1], np.inf)
    rows, cols = np.nonzero(held)
    np.minimum.at(first, cols, truth.times[rows + hold - 1].astype(float))
    return first


def alarms(truth, dens, speed):
    """First alarm time (s) per zone for each method; inf = never."""
    cond = {**base_conditions(truth, dens),
            "speed": np.nan_to_num(speed, nan=np.inf) < W["alarm_speed_mps"]}
    return {m: first_held(truth, c, W["alarm_hold_s"]) for m, c in cond.items()}


def score(truth, dens, first_alarm):
    """Lead time for the first event, zone hit rate, false alarms, density error."""
    events = np.nonzero(np.isfinite(truth.onset) & truth.valid)[0]
    near_alarm = np.where(truth.near, first_alarm[None], np.inf).min(1)  # earliest alarm nearby
    res = {}
    if len(events):
        z0 = events[np.argmin(truth.onset[events])]
        lead = truth.onset[z0] - near_alarm[z0]
        res["first_event_s"] = float(truth.onset[z0])
        res["lead_min"] = float(lead / 60) if np.isfinite(lead) else None
        leads = truth.onset[events] - near_alarm[events]
        res["zone_hit"] = float(np.mean(leads >= CFG["warning"]["go"]["lead_min"] * 60))
    else:
        res["first_event_s"] = res["lead_min"] = res["zone_hit"] = None
    event_near = (truth.near & np.isfinite(truth.onset)[None]).any(1)
    res["false_alarm_zones"] = int((np.isfinite(first_alarm) & ~event_near & truth.valid).sum())
    return res


def density_error(truth, dens):
    m = truth.density >= 1.0
    m[:, ~truth.valid] = False
    return float(np.median(np.abs(dens[m] - truth.density[m]) / truth.density[m])) if m.any() else None


def summarise(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return {"median": None, "p10": None, "p90": None, "n": 0}
    return {"median": float(np.median(v)), "p10": float(np.percentile(v, 10)),
            "p90": float(np.percentile(v, 90)), "n": len(v)}


def evaluate(run, truths, shares, intervals, sigmas, draws, log):
    rows = []
    for interval in intervals:
        for d in range(draws):
            for share, sigma, p in draw(run, shares, interval, sigmas, seed=1000 * interval + d):
                for zone_m, truth in truths.items():
                    dens, speed, _ = estimate(truth, p)
                    first = alarms(truth, dens, speed)
                    err = density_error(truth, dens)
                    for m in METHODS:
                        rows.append({"run": run.name, "share": share, "interval_s": interval, "sigma_m": sigma,
                                     "zone_m": zone_m, "draw": d, "method": m, "density_error": err,
                                     **score(truth, dens, first[m])})
            log(f"{run.name}: interval {interval} s, draw {d + 1}/{draws}")
    return rows


def oracle(run, truths):
    rows = []
    for share, sigma, p in draw(run, [1.0], 10, [0.0], seed=0):
        for zone_m, truth in truths.items():
            dens, speed, _ = estimate(truth, p)
            first = alarms(truth, dens, speed)
            for m in METHODS:
                rows.append({"run": run.name, "share": "oracle", "interval_s": 10, "sigma_m": 0, "zone_m": zone_m,
                             "draw": 0, "method": m, "density_error": density_error(truth, dens),
                             **score(truth, dens, first[m])})
    return rows


def table(rows):
    """Group raw rows by setting and summarise over draws."""
    keys = {}
    for r in rows:
        k = (r["run"], r["share"], r["interval_s"], r["sigma_m"], r["zone_m"], r["method"])
        keys.setdefault(k, []).append(r)
    out = []
    for k, rs in keys.items():
        out.append({"run": k[0], "share": k[1], "interval_s": k[2], "sigma_m": k[3], "zone_m": k[4], "method": k[5],
                    "draws": len(rs),
                    "warned_share": float(np.mean([r["lead_min"] is not None for r in rs])),
                    "lead_min": summarise([r["lead_min"] for r in rs]),
                    "lead_ok_share": float(np.mean([(r["lead_min"] or -1e9) >= W["go"]["lead_min"] for r in rs])),
                    "zone_hit": summarise([r["zone_hit"] for r in rs]),
                    "false_alarm_zones": summarise([r["false_alarm_zones"] for r in rs]),
                    "density_error": summarise([r["density_error"] for r in rs]),
                    "first_event_s": rs[0]["first_event_s"]})
    return out


def plots(summary, out, jam_run, calm_run):
    sel = lambda **kw: [s for s in summary if all(s[k] == v for k, v in kw.items())]
    shares = sorted({s["share"] for s in summary if s["share"] != "oracle"})
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, method in zip(axs, METHODS):
        for interval, c in zip(sorted({s["interval_s"] for s in summary if s["share"] != "oracle"}),
                               ["C0", "C1", "C2"]):
            pts = [sel(run=jam_run, share=sh, interval_s=interval, sigma_m=10, zone_m=20, method=method)[0]
                   for sh in shares]
            med = [p["lead_min"]["median"] if p["lead_min"]["median"] is not None else np.nan for p in pts]
            lo = [p["lead_min"]["p10"] if p["lead_min"]["p10"] is not None else np.nan for p in pts]
            hi = [p["lead_min"]["p90"] if p["lead_min"]["p90"] is not None else np.nan for p in pts]
            ax.errorbar(np.array(shares) * 100, med, yerr=[np.subtract(med, lo), np.subtract(hi, med)],
                        fmt="o-", color=c, capsize=3, label=f"every {interval} s")
        o = sel(run=jam_run, share="oracle", zone_m=20, method=method)
        if o and o[0]["lead_min"]["median"] is not None:
            ax.axhline(o[0]["lead_min"]["median"], color="grey", ls=":", label="everyone, no GPS error")
        ax.axhline(W["go"]["lead_min"], color="red", ls="--", lw=0.8)
        ax.set_xscale("log"); ax.minorticks_off(); ax.set_xticks([1, 2, 5]); ax.set_xticklabels(["1%", "2%", "5%"])
        ax.set_xlabel("share of people with a phone"); ax.set_title(f"{method} warning")
        ax.set_ylabel("minutes of warning before first jam")
        ax.legend(fontsize=8)
    fig.suptitle(f"{jam_run}: warning time (median, 10–90% over draws); GPS error 10 m, 20 m zones")
    fig.tight_layout(); fig.savefig(out / "lead_vs_share.png", dpi=100); plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(11, 4.5))
    for sigma, c in zip([5, 10, 20], ["C0", "C1", "C2"]):
        for ax, zone_m in zip(axs, [12, 32]):
            pts = [sel(run=jam_run, share=sh, interval_s=15, sigma_m=sigma, zone_m=zone_m, method="count")[0]
                   for sh in shares]
            ax.plot(np.array(shares) * 100, [p["density_error"]["median"] for p in pts], "o-", color=c,
                    label=f"GPS error {sigma} m")
            ax.set_title(f"{zone_m} m zones, ping every 15 s")
    for ax in axs:
        ax.axhline(W["go"]["density_error"], color="red", ls="--", lw=0.8)
        ax.set_xscale("log"); ax.minorticks_off(); ax.set_xticks([1, 2, 5]); ax.set_xticklabels(["1%", "2%", "5%"])
        ax.set_xlabel("share of people with a phone"); ax.set_ylabel("median density error (where ≥ 1/m²)")
        ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / "density_error.png", dpi=100); plt.close(fig)

    if calm_run:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for method, c in zip(METHODS, ["C0", "C1", "C2"]):
            pts = [sel(run=calm_run, share=sh, interval_s=15, sigma_m=10, zone_m=20, method=method)[0]
                   for sh in shares]
            ax.plot(np.array(shares) * 100, [p["false_alarm_zones"]["median"] for p in pts], "o-", color=c,
                    label=method)
        ax.set_xscale("log"); ax.minorticks_off(); ax.set_xticks([1, 2, 5]); ax.set_xticklabels(["1%", "2%", "5%"])
        ax.set_xlabel("share of people with a phone"); ax.set_ylabel("zones alarmed (no jam anywhere)")
        ax.set_title(f"{calm_run}: false alarms; ping every 15 s, GPS error 10 m, 20 m zones")
        ax.legend(); fig.tight_layout(); fig.savefig(out / "false_alarms.png", dpi=100); plt.close(fig)


def share_plot(summary, out, jam_run, calm_run):
    """Lead time, false alarms and density error against the phone share."""
    shares = sorted({s["share"] for s in summary if s["share"] != "oracle"})
    x = np.array(shares) * 100
    get = lambda run, zone_m, method: [next(s for s in summary if s["run"] == run and s["share"] == sh
                                            and s["zone_m"] == zone_m and s["method"] == method) for sh in shares]
    med = lambda pts, key: [p[key]["median"] if p[key]["median"] is not None else np.nan for p in pts]
    fig, axs = plt.subplots(1, 3, figsize=(16, 4.5))
    for zone_m, ls in [(20, "-"), (32, "--")]:
        for method, c in [("count", "C0"), ("trend", "C2")]:
            lab = f"{method}, {zone_m} m zones"
            axs[0].plot(x, med(get(jam_run, zone_m, method), "lead_min"), "o" + ls, color=c, label=lab)
            if calm_run:
                axs[1].plot(x, med(get(calm_run, zone_m, method), "false_alarm_zones"), "o" + ls, color=c, label=lab)
        axs[2].plot(x, med(get(jam_run, zone_m, "count"), "density_error"), "o" + ls, color="k",
                    label=f"{zone_m} m zones")
    axs[0].axhline(W["go"]["lead_min"], color="red", ls=":", lw=0.8)
    axs[0].set_ylabel("minutes of warning before first jam (median)")
    axs[1].set_ylabel("zones alarmed on the calm run (median)")
    axs[1].axhline(1, color="red", ls=":", lw=0.8)
    axs[2].axhline(W["go"]["density_error"], color="red", ls=":", lw=0.8)
    axs[2].set_ylabel("median density error (where ≥ 1/m²)")
    for ax in axs:
        ax.set_xscale("log"); ax.minorticks_off(); ax.set_xticks(x); ax.set_xticklabels([f"{v:g}%" for v in x])
        ax.set_xlabel("share of people with a phone"); ax.legend(fontsize=8)
    fig.suptitle("Phone share sweep: ping every 15 s, GPS error 10 m, 20 draws")
    fig.tight_layout(); fig.savefig(out / "share_sweep.png", dpi=100); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jam_run", help="run with a jam (snapshots kept)")
    ap.add_argument("--calm-run", help="run without a jam, for false alarms")
    ap.add_argument("--draws", type=int, default=P["draws"])
    ap.add_argument("--quick", action="store_true", help="2% / 15 s / 10 m / 20 m only, 2 draws")
    ap.add_argument("--shares", type=float, nargs="*",
                    help="phone-share sweep at 15 s, 10 m GPS error, 20 and 32 m zones (instead of the full grid)")
    ap.add_argument("--name", default="phase4")
    args = ap.parse_args()
    out = ROOT / "out" / args.name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    log = lambda msg: print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)

    shares, intervals, sigmas, zones = P["phone_share"], P["interval_s"], P["gps_sigma_m"], W["zone_m"]
    draws = args.draws
    if args.quick:
        shares, intervals, sigmas, zones, draws = [0.02], [15], [10], [20], 2
    if args.shares:
        shares, intervals, sigmas, zones = args.shares, [15], [10], [20, 32]

    rows = []
    for name in [args.jam_run] + ([args.calm_run] if args.calm_run else []):
        run = Run(name)
        truths, cell_first = {}, None
        for zone_m in zones:
            truths[zone_m] = Truth(run, zone_m, cell_first)
            cell_first = truths[zone_m].cell_first
        tr = truths[zones[0]]
        log(f"{name}: {len(run.off) - 1} s, first event at "
            f"{tr.onset[np.isfinite(tr.onset)].min() if np.isfinite(tr.onset).any() else None} s, "
            f"{int(np.isfinite(tr.onset).sum())} event zones at {zones[0]} m")
        rows += oracle(run, truths)
        log(f"{name}: oracle done")
        rows += evaluate(run, truths, shares, intervals, sigmas, draws, log)
        del run

    summary = table(rows)
    (out / "results.json").write_text(json.dumps({"pings": P, "warning": W, "dense_ppm2": DENSE,
                                                  "runs": [args.jam_run, args.calm_run], "summary": summary}, indent=1))
    (out / "raw.json").write_text(json.dumps(rows))
    if args.shares:
        share_plot(summary, out, args.jam_run, args.calm_run)
    elif not args.quick:
        plots(summary, out, args.jam_run, args.calm_run)
    for s in summary:
        if s["zone_m"] == 20 and s["share"] in (0.02, "oracle") and s["interval_s"] in (10, 15) \
                and s["sigma_m"] in (0, 10):
            print(f"{s['run']} {s['share']} {s['method']:5s}: warned {s['warned_share']:.0%}, "
                  f"lead {s['lead_min']['median']} min, >= {W['go']['lead_min']} min in {s['lead_ok_share']:.0%}, "
                  f"zone hits {s['zone_hit']['median']}, false-alarm zones {s['false_alarm_zones']['median']}, "
                  f"density error {s['density_error']['median']}")
    log(f"wrote {out / 'results.json'}")


if __name__ == "__main__":
    main()
