"""Contingency-table skill verification of ECMWF IFS025 rainfall over India.

For every (truth source, threshold, lead) cell:

    a = hits            forecast wet, observed wet
    b = false alarms    forecast wet, observed DRY   <- the farmer's wasted spray
    c = misses          forecast dry, observed wet
    d = correct negatives

    POD  = a / (a + c)                      hit rate
    FAR  = b / (a + b)                      HEADLINE
    CSI  = a / (a + b + c)
    BIAS = (a + b) / (a + c)                >1 over-forecasts rain
    HSS  = 2(ad - bc) / [(a+c)(c+d) + (a+b)(b+d)]

Both truth sources are run: IMD gridded (primary) and ERA5 (robustness).
The difference between them is reported as a result in its own right,
because ERA5's one-directional wet bias converts real false alarms into
apparent hits and therefore understates FAR.

Uncertainty is a cluster bootstrap over SPATIAL BLOCKS, not over point-days
and not over individual points. Two distinct dependences have to be handled,
and it is easy to state them backwards:

  * TEMPORAL dependence, within a location. Consecutive wet days at one point
    are correlated. A cluster bootstrap handles this automatically, because a
    whole point time series moves as one unit and is never broken up. Nothing
    extra is required.

  * SPATIAL dependence, between locations. Rainfall on a given day is
    correlated across neighbouring points, and over India the monsoon's
    seasonal cycle keeps that correlation non-zero even at continental
    separations (measured: mean r = 0.24 over all pairs of wet/dry series,
    0.50 for neighbours ~165 km apart, still ~0.11 at 1800-4000 km).
    Resampling individual points does NOT handle this: it treats 139
    correlated points as 139 independent clusters and understates the
    variance.

Clustering on BLOCK_DEG-degree blocks addresses the spatial part. Measured
against the old point-level resampling, block clustering widens the FAR
interval by about a factor of two and plateaus by 8 degrees, implying roughly
37 effective independent locations rather than 139.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from config import (ANALYSIS_END, ANALYSIS_START, BLOCK_DEG, INTERIM, LEADS,
                    RESULTS, THRESHOLDS)

N_BOOT = 4000          # 500 left ~0.005 of Monte Carlo noise on CI endpoints
RNG = np.random.default_rng(20260914)


def metrics(a, b, c, d) -> dict[str, float]:
    a, b, c, d = float(a), float(b), float(c), float(d)
    pod = a / (a + c) if (a + c) else np.nan
    far = b / (a + b) if (a + b) else np.nan
    csi = a / (a + b + c) if (a + b + c) else np.nan
    bias = (a + b) / (a + c) if (a + c) else np.nan
    den = (a + c) * (c + d) + (a + b) * (b + d)
    hss = (2 * (a * d - b * c) / den) if den else np.nan
    # the other direction: it said dry -- did it stay dry?
    npv = d / (c + d) if (c + d) else np.nan
    return {"POD": pod, "FAR": far, "CSI": csi, "BIAS": bias, "HSS": hss,
            "NPV": npv,
            "hits": a, "false_alarms": b, "misses": c, "correct_neg": d,
            "n": a + b + c + d}


def table(fc_wet: np.ndarray, ob_wet: np.ndarray):
    a = int(np.sum(fc_wet & ob_wet))
    b = int(np.sum(fc_wet & ~ob_wet))
    c = int(np.sum(~fc_wet & ob_wet))
    d = int(np.sum(~fc_wet & ~ob_wet))
    return a, b, c, d


def block_labels(point_ids) -> np.ndarray:
    """Map each point to its BLOCK_DEG-degree lat/lon block."""
    pts = pd.read_csv(INTERIM / "points.csv").set_index("point_id")
    p = pts.loc[list(point_ids)]
    return np.array([f"{int(la // BLOCK_DEG)}_{int(lo // BLOCK_DEG)}"
                     for la, lo in zip(p.lat, p.lon)])


def bootstrap_ci(df, fc_col, ob_col, thr, n_boot=N_BOOT):
    """Resample SPATIAL BLOCKS with replacement; return 2.5/97.5 pct per metric.

    The contingency table is additive, so each point is reduced to its own
    (a, b, c, d) once and a bootstrap draw is a sum of the rows belonging to
    the drawn blocks. Each iteration is then O(points) rather than
    O(point-days).

    Blocks, not individual points, are the resampling unit: rainfall is
    spatially correlated, so points are not independent clusters and
    resampling them singly gives intervals about half their proper width.
    Temporal correlation within a point needs no special handling here --
    a point's whole series always travels with its block.
    """
    fc_wet = df[fc_col].to_numpy() >= thr
    ob_wet = df[ob_col].to_numpy() >= thr
    codes, uniq = pd.factorize(df["point_id"], sort=False)
    npts = len(uniq)
    # per-point counts: columns are hits, false alarms, misses, correct negs
    counts = np.zeros((npts, 4), dtype=np.int64)
    np.add.at(counts, (codes, 0), (fc_wet & ob_wet))
    np.add.at(counts, (codes, 1), (fc_wet & ~ob_wet))
    np.add.at(counts, (codes, 2), (~fc_wet & ob_wet))
    np.add.at(counts, (codes, 3), (~fc_wet & ~ob_wet))

    blocks = block_labels(uniq)
    ublocks = np.unique(blocks)
    rows_by_block = [np.where(blocks == b)[0] for b in ublocks]
    nb = len(ublocks)

    keys = ["POD", "FAR", "CSI", "BIAS", "HSS", "NPV"]
    acc = {k: np.empty(n_boot) for k in keys}
    for i in range(n_boot):
        pick = RNG.integers(0, nb, size=nb)
        sel = np.concatenate([rows_by_block[k] for k in pick])
        a, b, c, d = counts[sel].sum(axis=0)
        m = metrics(a, b, c, d)
        for k in keys:
            acc[k][i] = m[k]
    return {f"{k}_lo": float(np.nanpercentile(acc[k], 2.5)) for k in keys} | \
           {f"{k}_hi": float(np.nanpercentile(acc[k], 97.5)) for k in keys}


def _combine_parts(source: str) -> pd.DataFrame:
    """Prefer the combined parquet; fall back to per-point parts so a partial
    fetch can still be analysed while the rest is still downloading."""
    whole = INTERIM / f"{source}_daily.parquet"
    if whole.exists():
        return pd.read_parquet(whole)
    parts = sorted((INTERIM / f"{source}_parts").glob("*.parquet"))
    if not parts:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)


def load():
    fc = _combine_parts("forecast")
    if fc.empty:
        sys.exit("no forecast data yet -- run fetch_openmeteo.py --source forecast")
    imd = pd.read_parquet(INTERIM / "imd_daily.parquet")
    for f in (fc, imd):
        f["date"] = pd.to_datetime(f["date"])
    df = fc.merge(imd, on=["point_id", "date"], how="inner")

    era = _combine_parts("era5")
    if era.empty:
        # ERA5 is the robustness arm only; the primary IMD result stands
        # without it. Analysing early beats waiting on a throttled fetch.
        print("WARNING: no ERA5 data -- skipping the robustness arm")
        df["era5_mm"] = pd.NA
    else:
        era = era.rename(columns={"precipitation": "era5_mm"})
        era["date"] = pd.to_datetime(era["date"])
        df = df.merge(era[["point_id", "date", "era5_mm"]],
                      on=["point_id", "date"], how="left")
    lo, hi = pd.Timestamp(ANALYSIS_START), pd.Timestamp(ANALYSIS_END)
    return df[(df.date >= lo) & (df.date <= hi)].reset_index(drop=True)


def main() -> int:
    df = load()
    print(f"matched point-days : {len(df)}")
    print(f"points             : {df.point_id.nunique()}")
    print(f"dates              : {df.date.min().date()} .. {df.date.max().date()}")
    print(f"with ERA5          : {df.era5_mm.notna().sum()}")

    rows = []
    for truth_name, truth_col in [("IMD", "imd_mm"), ("ERA5", "era5_mm")]:
        sub_all = df.dropna(subset=[truth_col])
        if sub_all.empty:
            print(f"  skipping {truth_name}: no data")
            continue
        for thr in THRESHOLDS:
            for lead in LEADS:
                fc_col = f"precipitation_previous_day{lead}"
                sub = sub_all.dropna(subset=[fc_col])
                a, b, c, d = table(sub[fc_col].to_numpy() >= thr,
                                   sub[truth_col].to_numpy() >= thr)
                rec = {"truth": truth_name, "threshold_mm": thr, "lead_days": lead}
                rec |= metrics(a, b, c, d)
                rec |= bootstrap_ci(sub, fc_col, truth_col, thr)
                rows.append(rec)
                print(f"  {truth_name:4} thr>={thr:<4} lead {lead}: "
                      f"POD={rec['POD']:.3f} FAR={rec['FAR']:.3f} "
                      f"HSS={rec['HSS']:.3f} BIAS={rec['BIAS']:.2f} "
                      f"n={int(rec['n'])}", flush=True)

    res = pd.DataFrame(rows)
    res.to_csv(RESULTS / "metrics.csv", index=False)

    # ---- the robustness result: how much does the truth source move FAR? ----
    piv = res.pivot_table(index=["threshold_mm", "lead_days"],
                          columns="truth", values="FAR")
    if {"IMD", "ERA5"} <= set(piv.columns):
        piv["FAR_gap_ERA5_minus_IMD"] = piv["ERA5"] - piv["IMD"]
        piv.to_csv(RESULTS / "far_truth_source_gap.csv")
        print("\n=== FAR by truth source (the robustness result) ===")
        print(piv.round(3).to_string())
    else:
        print("\n(ERA5 arm absent -- truth-source gap not computed)")

    print(f"\nwrote {RESULTS/'metrics.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
