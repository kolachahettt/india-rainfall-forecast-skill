"""Per-point skill, and whether per-point FAR is stable enough to map.

The pooled analysis blocks over SPACE because points are spatially
correlated. That machinery does not transfer to a single point: there is no
spatial dimension left to resample. The uncertainty in one point's FAR is
temporal-sampling uncertainty, so the correct analogue is a moving-block
bootstrap over DAYS.

Block length: measured lag-k autocorrelation of the wet/dry series within a
point decays to ~0 by lag 5-7 once the day-of-year climatology is removed
(raw r stays ~0.2 out to 30 days, but that is the seasonal cycle, not
synoptic persistence). BLOCK_DAYS = 14 is comfortably beyond that.

The question this answers is signal-to-noise: is the spread of FAR ACROSS
points bigger than the uncertainty WITHIN a point? If not, a per-point map
is painting noise, and the honest move is to aggregate.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from config import (ANALYSIS_END, ANALYSIS_START, INTERIM, LEADS, RESULTS,
                    THRESHOLDS)

BLOCK_DAYS = 14
N_BOOT = 1000
AGG_DEG = 3.0          # proxy grouping for IMD meteorological subdivisions
RNG_SEED = 20260917


def load():
    fc = pd.read_parquet(INTERIM / "forecast_daily.parquet")
    imd = pd.read_parquet(INTERIM / "imd_daily.parquet")
    for f in (fc, imd):
        f["date"] = pd.to_datetime(f["date"])
    df = fc.merge(imd, on=["point_id", "date"], how="inner")
    return df[(df.date >= pd.Timestamp(ANALYSIS_START))
              & (df.date <= pd.Timestamp(ANALYSIS_END))].sort_values(
                  ["point_id", "date"])


def metrics_from(a, b, c, d):
    a, b, c, d = float(a), float(b), float(c), float(d)
    pod = a / (a + c) if (a + c) else np.nan
    far = b / (a + b) if (a + b) else np.nan
    csi = a / (a + b + c) if (a + b + c) else np.nan
    bias = (a + b) / (a + c) if (a + c) else np.nan
    den = (a + c) * (c + d) + (a + b) * (b + d)
    hss = (2 * (a * d - b * c) / den) if den else np.nan
    return pod, far, csi, bias, hss


def block_counts(cat: np.ndarray, nblk: int) -> np.ndarray:
    """cat: per-day category 0=hit 1=FA 2=miss 3=CN. -> (nblk, 4) counts."""
    usable = nblk * BLOCK_DAYS
    c = cat[:usable].reshape(nblk, BLOCK_DAYS)
    out = np.zeros((nblk, 4), dtype=np.int64)
    for k in range(4):
        out[:, k] = (c == k).sum(axis=1)
    return out


def boot_ci(bc: np.ndarray, rng, n_boot=N_BOOT):
    nblk = bc.shape[0]
    fars = np.empty(n_boot)
    for i in range(n_boot):
        a, b, _, _ = bc[rng.integers(0, nblk, size=nblk)].sum(axis=0)
        fars[i] = b / (a + b) if (a + b) else np.nan
    if np.all(np.isnan(fars)):
        return np.nan, np.nan
    return (float(np.nanpercentile(fars, 2.5)),
            float(np.nanpercentile(fars, 97.5)))


def main() -> int:
    df = load()
    pts = pd.read_csv(INTERIM / "points.csv").set_index("point_id")
    rng = np.random.default_rng(RNG_SEED)
    rows = []
    for thr in THRESHOLDS:
        for lead in LEADS:
            col = f"precipitation_previous_day{lead}"
            for pid, g in df.groupby("point_id", sort=True):
                f = g[col].to_numpy() >= thr
                o = g["imd_mm"].to_numpy() >= thr
                cat = np.where(f & o, 0, np.where(f & ~o, 1,
                               np.where(~f & o, 2, 3)))
                a, b, c, d = [(cat == k).sum() for k in range(4)]
                pod, far, csi, bias, hss = metrics_from(a, b, c, d)
                nblk = len(cat) // BLOCK_DAYS
                lo, hi = boot_ci(block_counts(cat, nblk), rng)
                p = pts.loc[pid]
                rows.append(dict(point_id=pid, lat=p.lat, lon=p.lon,
                                 threshold_mm=thr, lead_days=lead,
                                 POD=pod, FAR=far, CSI=csi, BIAS=bias, HSS=hss,
                                 FAR_lo=lo, FAR_hi=hi,
                                 wet_days=int(a + c), n=int(len(cat))))
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "perpoint_metrics.csv", index=False)
    print(f"wrote {RESULTS/'perpoint_metrics.csv'}  ({len(out)} rows)\n")

    # ---- signal vs noise: between-point spread against within-point CI ----
    print("=== Is per-point FAR stable enough to map? ===")
    print(f"{'thr':>5} {'lead':>5} {'pts':>4} {'median CI width':>16} "
          f"{'IQR of FAR across pts':>23} {'ratio':>7}")
    verdict = []
    for thr in THRESHOLDS:
        for lead in LEADS:
            s = out[(out.threshold_mm == thr) & (out.lead_days == lead)]
            s = s.dropna(subset=["FAR", "FAR_lo", "FAR_hi"])
            w = (s.FAR_hi - s.FAR_lo).median()
            iqr = s.FAR.quantile(.75) - s.FAR.quantile(.25)
            verdict.append((thr, lead, w, iqr))
            print(f"{thr:>5} {lead:>5} {len(s):>4} {w:>16.3f} "
                  f"{iqr:>23.3f} {iqr/w:>7.2f}")

    # ---- aggregated to AGG_DEG blocks (stand-in for IMD subdivisions) ----
    print(f"\n=== Same, aggregated to {AGG_DEG:g}° groups "
          f"(proxy for IMD's 36 meteorological subdivisions) ===")
    df = df.merge(pts.reset_index()[["point_id", "lat", "lon"]],
                  on="point_id", how="left")
    df["grp"] = [f"{int(la // AGG_DEG)}_{int(lo // AGG_DEG)}"
                 for la, lo in zip(df.lat, df.lon)]
    grows = []
    print(f"{'thr':>5} {'lead':>5} {'grps':>5} {'median CI width':>16} "
          f"{'IQR of FAR across grps':>24} {'ratio':>7}")
    for thr in THRESHOLDS:
        for lead in LEADS:
            col = f"precipitation_previous_day{lead}"
            recs = []
            for grp, g in df.groupby("grp", sort=True):
                # concatenate the group's points, keeping each point's days
                # contiguous so temporal blocks stay meaningful
                cats = []
                for _, gp in g.groupby("point_id", sort=True):
                    f = gp[col].to_numpy() >= thr
                    o = gp["imd_mm"].to_numpy() >= thr
                    cats.append(np.where(f & o, 0, np.where(f & ~o, 1,
                                np.where(~f & o, 2, 3))))
                bcs = [block_counts(c, len(c) // BLOCK_DAYS) for c in cats]
                bc = np.vstack(bcs)
                a, b, c_, d = bc.sum(axis=0)
                _, far, _, _, _ = metrics_from(a, b, c_, d)
                lo, hi = boot_ci(bc, rng)
                recs.append(dict(grp=grp, threshold_mm=thr, lead_days=lead,
                                 FAR=far, FAR_lo=lo, FAR_hi=hi,
                                 n_points=g.point_id.nunique()))
            gs = pd.DataFrame(recs).dropna(subset=["FAR", "FAR_lo"])
            grows.append(gs)
            w = (gs.FAR_hi - gs.FAR_lo).median()
            iqr = gs.FAR.quantile(.75) - gs.FAR.quantile(.25)
            print(f"{thr:>5} {lead:>5} {len(gs):>5} {w:>16.3f} "
                  f"{iqr:>24.3f} {iqr/w:>7.2f}")
    pd.concat(grows, ignore_index=True).to_csv(
        RESULTS / "pergroup_metrics.csv", index=False)
    print(f"\nwrote {RESULTS/'pergroup_metrics.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
