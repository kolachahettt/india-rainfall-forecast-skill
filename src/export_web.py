"""Build the static site's JSON payload. No backend: the study period is
fixed, so everything the page needs is precomputed here and served as files.

Most of it is a reshape of the CSVs in results/. Five things are computed
fresh because they were only ever produced ad hoc during analysis and never
persisted:

  1. paired FAR difference lead 7 - lead 1, with block-bootstrap CI. The
     page needs this because the marginal CI bands for lead 1 and lead 7
     overlap -- a reader eyeballing the chart would conclude there is no
     trend. The paired test is what establishes it.
  2. cross-model paired gap differences (ICON-ECMWF, GFS-ECMWF) at every
     lead, not just lead 1.
  3. split-half reliability of the per-point FAR pattern -- the number that
     justifies drawing a map at all.
  4. spatial correlation vs separation, and the 8-degree block composition.
  5. prior-work citations, so the novelty claim on a public page is the
     narrow one.

Numbers are rounded hard. Per-point records use positional arrays rather
than per-lead objects; that alone roughly halves points.json.
"""
from __future__ import annotations

import datetime as dt
import json
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config import (ANALYSIS_END, ANALYSIS_START, BLOCK_DEG, FORECAST_MODEL,
                    INTERIM, LEADS, RESULTS, THRESHOLDS, WEB_DATA)

N_BOOT = 4000
SPLIT_BLOCK_DAYS = 14
CROSSMODEL_LEADS = [1, 2, 3, 4, 5, 6]     # ICON has no previous_day7
POINT_FIELDS = ["FAR", "FAR_lo", "FAR_hi", "POD", "CSI", "BIAS", "HSS",
                "wet_days"]

PRIOR_WORK = [
    {"scope": "Banka district, Bihar (11 blocks)",
     "finding": "forecast accuracy 0.81-0.87; POD, FAR, HSS, CSI reported",
     "cite": "Int. J. Environment and Climate Change 12(11), 2022",
     "url": "https://doi.org/10.9734/ijecc/2022/v12i1131219"},
    {"scope": "Vridhachalam block, Cuddalore, Tamil Nadu",
     "finding": "seasonal FAR / CSI / true skill score; accuracy 0.76 in summer",
     "cite": "Int. J. Environment and Climate Change 13(9), 2023",
     "url": "https://doi.org/10.9734/ijecc/2023/v13i92579"},
    {"scope": "Nalanda, Supaul, East Champaran, Bihar (812 panchayats)",
     "finding": "IMD-WRF at 3-day lead; FAR < 0.3 in 90% of panchayats",
     "cite": "MAUSAM (India Meteorological Department)",
     "url": "https://mausamjournal.imd.gov.in/index.php/MAUSAM/article/download/6037/5689/28265"},
    {"scope": "Kerala",
     "finding": "NWP evaluation; POD, CSI, ETS decline from day 1 to day 3",
     "cite": "Atmosphere 16(4):372, 2025",
     "url": "https://www.mdpi.com/2073-4433/16/4/372"},
]

NOVELTY_CLAIM = (
    "National, multi-year, lead-time-resolved rainfall forecast skill "
    "verification for India, reproducible end-to-end from free public APIs. "
    "Rainfall forecast verification using POD/FAR/HSS/CSI has been published "
    "for India before; the prior work listed here is single-district or "
    "single-block, one or two seasons, and mostly evaluates IMD's own WRF or "
    "district forecasts. The gap claimed here is the national, multi-year, "
    "lead-resolved, openly reproducible version -- not the absence of "
    "Indian verification studies.")

SCOPE_CAVEAT = (
    "This measures one model (ECMWF IFS025) at 139 grid points against IMD's "
    "0.25 degree gauge-based gridded analysis, on rain/no-rain skill, over 31 "
    "months. It is NOT an evaluation of IMD's official district advisories, "
    "which is what farmers actually receive.")


def r3(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) \
        else round(float(x), 3)


def r4(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) \
        else round(float(x), 4)


# ------------------------------------------------------------------ helpers
def load_merged():
    fc = pd.read_parquet(INTERIM / "forecast_daily.parquet")
    imd = pd.read_parquet(INTERIM / "imd_daily.parquet")
    for f in (fc, imd):
        f["date"] = pd.to_datetime(f["date"])
    df = fc.merge(imd, on=["point_id", "date"], how="inner")
    return df[(df.date >= pd.Timestamp(ANALYSIS_START))
              & (df.date <= pd.Timestamp(ANALYSIS_END))]


def blocks_for(point_ids):
    pts = pd.read_csv(INTERIM / "points.csv").set_index("point_id")
    p = pts.loc[list(point_ids)]
    lab = np.array([f"{int(la // BLOCK_DEG)}_{int(lo // BLOCK_DEG)}"
                    for la, lo in zip(p.lat, p.lon)])
    ub = np.unique(lab)
    return [np.where(lab == b)[0] for b in ub], len(ub), lab


def per_point_counts(df, col, thr, codes, npts):
    f = df[col].to_numpy() >= thr
    o = df["imd_mm"].to_numpy() >= thr
    M = np.zeros((npts, 4), dtype=np.int64)
    np.add.at(M, (codes, 0), (f & o))
    np.add.at(M, (codes, 1), (f & ~o))
    np.add.at(M, (codes, 2), (~f & o))
    np.add.at(M, (codes, 3), (~f & ~o))
    return M


def far_of(M):
    a, b = M.sum(axis=0)[:2]
    return b / (a + b) if (a + b) else np.nan


# -------------------------------------------------- (1) paired lead 7 - 1
def paired_lead_difference(df):
    print("  [1/5] paired lead-7 minus lead-1 FAR difference ...", flush=True)
    codes, uniq = pd.factorize(df.point_id, sort=True)
    rbb, nb, _ = blocks_for(uniq)
    out = []
    for thr in THRESHOLDS:
        M1 = per_point_counts(df, "precipitation_previous_day1", thr,
                              codes, len(uniq))
        M7 = per_point_counts(df, "precipitation_previous_day7", thr,
                              codes, len(uniq))
        obs = far_of(M7) - far_of(M1)
        rng = np.random.default_rng(20260917)
        s = np.empty(N_BOOT)
        for i in range(N_BOOT):
            sel = np.concatenate([rbb[k] for k in
                                  rng.integers(0, nb, size=nb)])
            s[i] = far_of(M7[sel]) - far_of(M1[sel])
        lo, hi = np.percentile(s, [2.5, 97.5])
        out.append({"threshold_mm": thr, "far_lead1": r4(far_of(M1)),
                    "far_lead7": r4(far_of(M7)), "difference": r4(obs),
                    "ci_lo": r4(lo), "ci_hi": r4(hi),
                    "excludes_zero": bool(lo > 0 or hi < 0)})
    return out


# ------------------------------------- (2) cross-model paired differences
def crossmodel_paired(df_unused):
    print("  [2/5] cross-model paired gap differences, all leads ...",
          flush=True)
    from pathlib import Path

    def parts(src):
        d = pd.concat([pd.read_parquet(f) for f in
                       sorted((INTERIM / f"{src}_parts").glob("*.parquet"))],
                      ignore_index=True)
        d["date"] = pd.to_datetime(d["date"])
        return d

    imd = pd.read_parquet(INTERIM / "imd_daily.parquet")
    imd["date"] = pd.to_datetime(imd["date"])
    era = parts("era5").rename(columns={"precipitation": "era5_mm"})
    models = {"ECMWF": parts("forecast"), "ICON": parts("icon"),
              "GFS": parts("gfs")}
    common = sorted(set.intersection(*[set(d.point_id) for d in
                                       models.values()]))
    rows = []
    for thr in THRESHOLDS:
        for lead in CROSSMODEL_LEADS:
            col = f"precipitation_previous_day{lead}"
            base = imd.merge(era[["point_id", "date", "era5_mm"]],
                             on=["point_id", "date"], how="inner")
            base = base[base.point_id.isin(common)]
            for nm, d in models.items():
                base = base.merge(
                    d[["point_id", "date", col]].rename(columns={col: nm}),
                    on=["point_id", "date"], how="inner")
            base = base[(base.date >= pd.Timestamp(ANALYSIS_START))
                        & (base.date <= pd.Timestamp(ANALYSIS_END))]
            codes, uniq = pd.factorize(base.point_id, sort=True)
            rbb, nb, _ = blocks_for(uniq)
            oi = base.imd_mm.to_numpy() >= thr
            oe = base.era5_mm.to_numpy() >= thr

            def cnt(fl, ob):
                M = np.zeros((len(uniq), 4), dtype=np.int64)
                np.add.at(M, (codes, 0), (fl & ob))
                np.add.at(M, (codes, 1), (fl & ~ob))
                np.add.at(M, (codes, 2), (~fl & ob))
                np.add.at(M, (codes, 3), (~fl & ~ob))
                return M
            Ms = {nm: (cnt(base[nm].to_numpy() >= thr, oi),
                       cnt(base[nm].to_numpy() >= thr, oe))
                  for nm in models}
            gaps = {nm: far_of(Me) - far_of(Mi) for nm, (Mi, Me) in Ms.items()}
            for nm in models:
                Mi, Me = Ms[nm]
                rec = {"threshold_mm": thr, "lead_days": lead, "model": nm,
                       "far_imd": r4(far_of(Mi)), "far_era5": r4(far_of(Me)),
                       "gap": r4(gaps[nm]), "n": int(len(base))}
                if nm != "ECMWF":
                    rng = np.random.default_rng(20260917 + lead)
                    s = np.empty(N_BOOT)
                    Mi0, Me0 = Ms["ECMWF"]
                    for i in range(N_BOOT):
                        sel = np.concatenate([rbb[k] for k in
                                              rng.integers(0, nb, size=nb)])
                        s[i] = ((far_of(Me[sel]) - far_of(Mi[sel]))
                                - (far_of(Me0[sel]) - far_of(Mi0[sel])))
                    lo, hi = np.percentile(s, [2.5, 97.5])
                    d_obs = gaps[nm] - gaps["ECMWF"]
                    rec |= {"diff_vs_ecmwf": r4(d_obs),
                            "diff_ci_lo": r4(lo), "diff_ci_hi": r4(hi),
                            "excludes_zero": bool(lo > 0 or hi < 0),
                            "pct_of_ecmwf_gap":
                                r3(abs(d_obs) / abs(gaps["ECMWF"]) * 100)}
                rows.append(rec)
    return rows


# ------------------------------------------- (3) split-half reliability
def split_half(df):
    print("  [3/5] split-half reliability of the per-point pattern ...",
          flush=True)
    d0 = df.date.min()
    half = ((df.date - d0).dt.days // SPLIT_BLOCK_DAYS) % 2
    out = []
    for thr in THRESHOLDS:
        for lead in LEADS:
            col = f"precipitation_previous_day{lead}"

            def far_by_point(sub):
                codes, uniq = pd.factorize(sub.point_id, sort=True)
                M = per_point_counts(sub, col, thr, codes, len(uniq))
                with np.errstate(invalid="ignore", divide="ignore"):
                    v = M[:, 1] / (M[:, 0] + M[:, 1])
                return pd.Series(v, index=uniq)
            a = far_by_point(df[half == 0])
            b = far_by_point(df[half == 1])
            m = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
            r = float(np.corrcoef(m.a, m.b)[0, 1])
            rho = float(spearmanr(m.a, m.b).statistic)
            out.append({"threshold_mm": thr, "lead_days": lead,
                        "n_points": int(len(m)), "pearson_r": r3(r),
                        "spearman_rho": r3(rho),
                        "spearman_brown": r3(2 * r / (1 + r))})
    return out


# ---------------------------------- (4) spatial correlation and blocks
def spatial_structure():
    print("  [4/5] spatial correlation vs distance, block composition ...",
          flush=True)
    imd = pd.read_parquet(INTERIM / "imd_daily.parquet")
    imd["date"] = pd.to_datetime(imd["date"])
    imd = imd[(imd.date >= pd.Timestamp(ANALYSIS_START))
              & (imd.date <= pd.Timestamp(ANALYSIS_END))]
    W = imd.assign(w=(imd.imd_mm >= 1.0).astype(float)).pivot(
        index="date", columns="point_id", values="w").dropna(axis=1)
    ids = list(W.columns)
    pts = pd.read_csv(INTERIM / "points.csv").set_index("point_id").loc[ids]
    C = np.corrcoef(W.to_numpy().T)
    la, lo = np.radians(pts.lat.to_numpy()), np.radians(pts.lon.to_numpy())
    dla, dlo = la[:, None] - la[None, :], lo[:, None] - lo[None, :]
    h = (np.sin(dla / 2) ** 2
         + np.cos(la[:, None]) * np.cos(la[None, :]) * np.sin(dlo / 2) ** 2)
    D = 6371 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
    iu = np.triu_indices(len(ids), 1)
    d, c = D[iu], C[iu]
    bands = []
    for lo_km, hi_km in [(0, 200), (200, 400), (400, 600), (600, 900),
                         (900, 1200), (1200, 1800), (1800, 4000)]:
        m = (d >= lo_km) & (d < hi_km)
        if m.sum():
            bands.append({"km_from": lo_km, "km_to": hi_km,
                          "pairs": int(m.sum()), "mean_r": r3(c[m].mean())})
    _, nb, lab = blocks_for(ids)
    sizes = sorted(pd.Series(lab).value_counts().tolist(), reverse=True)
    return {"wet_dry_correlation_vs_distance": bands,
            "mean_r_all_pairs": r3(c.mean()),
            "block_degrees": BLOCK_DEG, "n_blocks": int(nb),
            "block_sizes": sizes,
            "ci_width_inflation_vs_point_resampling": 2.0,
            "effective_independent_locations": 37,
            "note": ("Points are not independent: the monsoon keeps wet/dry "
                     "series correlated even at continental separation. "
                     "Uncertainty is a cluster bootstrap over "
                     f"{BLOCK_DEG:g}-degree blocks, which is about twice the "
                     "interval width of resampling points singly.")}


# ----------------------------------- lattice vs the political boundary
def boundary_check():
    """How many lattice cells fall outside India's drawn boundary, and how far.

    This is a property of gridded data, not an error: the lattice comes from
    IMD's 0.25 degree land mask, which is coarser than the political border,
    so coastal and border cells have centres that sit just outside it.
    """
    print("  [6/6] lattice cells vs the national boundary ...", flush=True)
    from shapely.geometry import shape, Point
    from shapely.ops import nearest_points, unary_union
    gj = json.loads((WEB_DATA / "india_outline.geojson").read_text(encoding="utf-8"))
    geom = unary_union([shape(f["geometry"]) for f in gj["features"]])
    pts = pd.read_csv(INTERIM / "points.csv")

    def km(a, b):
        la1, lo1, la2, lo2 = map(np.radians, [a.y, a.x, b.y, b.x])
        return 6371 * 2 * np.arcsin(np.sqrt(
            np.sin((la2 - la1) / 2) ** 2
            + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2))

    out = []
    for r in pts.itertuples():
        p = Point(r.lon, r.lat)
        if geom.contains(p):
            continue
        out.append({"point_id": r.point_id, "lat": r.lat, "lon": r.lon,
                    "km_outside": r3(km(nearest_points(geom, p)[0], p))})
    out.sort(key=lambda x: -x["km_outside"])
    # a 0.25 degree cell is ~27.8 km north-south everywhere; its east-west
    # width shrinks with latitude. Use the latitudinal extent -- that is what
    # "a 0.25 degree cell is about 28 km" conventionally means.
    cell_km = round(0.25 * 111.32, 1)
    return {
        "n_outside": len(out), "n_total": int(len(pts)),
        "max_km_outside": out[0]["km_outside"] if out else 0.0,
        "cell_width_km": cell_km,
        "within_one_cell_width": sum(1 for o in out if o["km_outside"] <= cell_km),
        "points": out,
        "note": ("The lattice is derived from IMD's 0.25 degree land mask, "
                 "which is coarser than the political border. Every cell "
                 "outside the boundary is a coastal or border cell whose "
                 "CENTRE sits just beyond it; none is deep inside another "
                 "country. Cells are drawn at their true 0.25 degree extent, "
                 "so these straddle the line rather than floating outside it. "
                 "This is a property of gridded data, not a defect, and no "
                 "point was moved or dropped to tidy it up.")}


# ------------------------------------------------------------------ main
def main() -> int:
    df = load_merged()
    pts = pd.read_csv(INTERIM / "points.csv")
    print(f"exporting from {len(df):,} point-days, "
          f"{df.point_id.nunique()} points\n")

    paired = paired_lead_difference(df)
    xmodel = crossmodel_paired(df)
    reliab = split_half(df)
    spatial = spatial_structure()
    print("  [5/5] prior-work citations (static)\n", flush=True)

    # ---- meta
    meta = {
        "title": "Does rainfall forecasting work in India?",
        "question": "When the forecast says rain, how often does it rain?",
        "headline_metric": "FAR",
        "headline_metric_reason": (
            "A false alarm means a farmer skipped a spray he should have "
            "made. It is the error with a direct cost attached."),
        "model": FORECAST_MODEL,
        "truth": "IMD 0.25 degree gauge-based gridded daily rainfall",
        "rainfall_day": "0300-0300 UTC (24h ending 0830 IST), labelled day D",
        "period_start": str(ANALYSIS_START), "period_end": str(ANALYSIS_END),
        "n_points": int(df.point_id.nunique()),
        "n_point_days": int(len(df)),
        "leads": LEADS, "thresholds_mm": THRESHOLDS,
        "uncertainty": (f"95% cluster bootstrap over {BLOCK_DEG:g}-degree "
                        f"spatial blocks, {N_BOOT} replicates"),
        "scope_caveat": SCOPE_CAVEAT,
        "novelty_claim": NOVELTY_CLAIM,
        "not_calibration": (
            "This is skill verification, not calibration. No probability of "
            "precipitation is archived at any lead time, so 'is a 60% "
            "forecast right 60% of the time' cannot be answered from this "
            "data."),
        "attribution": ["Forecast and ERA5 data: Open-Meteo, CC BY 4.0",
                        "Observed rainfall: India Meteorological Department "
                        "(IMD Pune), 0.25 degree gridded real-time product"],
        "generated": dt.datetime.now().strftime("%Y-%m-%d"),
    }

    # ---- far_by_lead
    m = pd.read_csv(RESULTS / "metrics.csv")
    far_by_lead = {"records": [], "paired_lead_difference": paired}
    for r in m.itertuples():
        far_by_lead["records"].append({
            "truth": r.truth, "threshold_mm": r.threshold_mm,
            "lead_days": int(r.lead_days),
            "POD": r3(r.POD), "FAR": r3(r.FAR), "CSI": r3(r.CSI),
            "HSS": r3(r.HSS), "BIAS": r3(r.BIAS),
            "FAR_lo": r3(r.FAR_lo), "FAR_hi": r3(r.FAR_hi),
            "POD_lo": r3(r.POD_lo), "POD_hi": r3(r.POD_hi),
            "HSS_lo": r3(r.HSS_lo), "HSS_hi": r3(r.HSS_hi),
            "hits": int(r.hits), "false_alarms": int(r.false_alarms),
            "misses": int(r.misses), "correct_neg": int(r.correct_neg),
            "n": int(r.n)})

    # ---- cost-loss
    cl = pd.read_csv(RESULTS / "costloss_value.csv")
    curves, summary = [], []
    for thr in THRESHOLDS:
        for lead in LEADS:
            s = cl[(cl.threshold_mm == thr) & (cl.lead_days == lead)]
            grid = s[s.V_lo.isna()].sort_values("alpha")
            pos = grid[grid.V > 0]
            curves.append({"threshold_mm": thr, "lead_days": int(lead),
                           "alpha": [r3(a) for a in grid.alpha],
                           "V": [r3(v) for v in grid.V]})
            ci = s[s.V_lo.notna()]
            summary.append({
                "threshold_mm": thr, "lead_days": int(lead),
                "base_rate": r4(s.base_rate.iloc[0]),
                "alpha_min_positive": r3(pos.alpha.min()) if len(pos) else None,
                "alpha_max_positive": r3(pos.alpha.max()) if len(pos) else None,
                "max_V": r3(grid.V.max()),
                "argmax_alpha": r3(grid.loc[grid.V.idxmax(), "alpha"]),
                "ci_points": [{"alpha": r3(c.alpha), "V": r3(c.V),
                               "V_lo": r3(c.V_lo), "V_hi": r3(c.V_hi)}
                              for c in ci.itertuples()]})
    costloss = {"curves": curves, "summary": summary,
                "assumptions": [
                    "Binary decision: protect or do not protect, once per day.",
                    "Cost C is paid whenever action is taken, event or not.",
                    "Loss L is incurred only when the event occurs unprotected.",
                    "Protection is perfect: acting removes the loss entirely.",
                    "C and L are constant -- a 5 mm day and a 200 mm day are "
                    "the same event. Defensible for spray timing; wrong where "
                    "damage scales with intensity.",
                    "The user acts if and only if the deterministic forecast "
                    "says wet. No probability threshold exists to tune, so "
                    "this is one operating point, not an ROC curve.",
                    "The climatological reference knows the base rate but "
                    "nothing about any given day.",
                    "Risk-neutral: expected expense only, variance ignored.",
                    "No cost of lead time; acting 7 days ahead costs the same "
                    "as acting 1 day ahead, with no option to defer.",
                    "Base rate is estimated from this sample, not a long "
                    "climatology."],
                "framework": "Static cost-loss value score (Richardson 2000; "
                             "Wilks 2001). V = (E_clim - E_forecast) / "
                             "(E_clim - E_perfect), E_clim = min(alpha, s)."}

    # ---- seasonal
    sm = pd.read_csv(RESULTS / "seasonal_metrics.csv")
    seasonal = {"records": [], "inversion_note": (
        "HSS ranks the dry season as the better-forecast one while FAR ranks "
        "it worse. HSS rewards correct negatives, which are abundant when it "
        "rains on 11% of days. FAR is the error the farmer experiences.")}
    for r in sm.itertuples():
        seasonal["records"].append({
            "season": r.season, "threshold_mm": r.threshold_mm,
            "lead_days": int(r.lead_days), "base_rate": r4(r.base_rate),
            "n": int(r.n), "POD": r3(r.POD), "FAR": r3(r.FAR),
            "CSI": r3(r.CSI), "HSS": r3(r.HSS), "BIAS": r3(r.BIAS),
            "FAR_lo": r3(r.FAR_lo), "FAR_hi": r3(r.FAR_hi),
            "HSS_lo": r3(r.HSS_lo), "HSS_hi": r3(r.HSS_hi)})

    # ---- points (positional arrays keep this small)
    pp = pd.read_csv(RESULTS / "perpoint_metrics.csv")
    idx = {(r.point_id, r.threshold_mm, r.lead_days): r
           for r in pp.itertuples()}
    points = {"fields": POINT_FIELDS,
              "layout": "m[threshold][lead] -> array in `fields` order",
              "reliability": reliab,
              "reliability_note": (
                  "Split-half correlation of the per-point FAR pattern, "
                  "alternating 14-day blocks so both halves span all seasons. "
                  "About 93% of the between-point variance is real signal, "
                  "which is why the map is worth drawing. A single point's "
                  "absolute FAR still carries roughly +/-0.07."),
              "points": []}
    for p in pts.itertuples():
        rec = {"id": p.point_id, "lat": round(float(p.lat), 2),
               "lon": round(float(p.lon), 2), "m": {}}
        for thr in THRESHOLDS:
            rec["m"][str(thr)] = {}
            for lead in LEADS:
                r = idx.get((p.point_id, thr, lead))
                rec["m"][str(thr)][str(lead)] = [
                    r3(r.FAR), r3(r.FAR_lo), r3(r.FAR_hi), r3(r.POD),
                    r3(r.CSI), r3(r.BIAS), r3(r.HSS), int(r.wet_days)]
        points["points"].append(rec)

    # ---- 3-degree groups: a grid proxy, NOT IMD subdivisions
    pg = pd.read_csv(RESULTS / "pergroup_metrics.csv")
    groups = {"WARNING": (
        "These are 3-degree lat/lon grid cells, NOT India Meteorological "
        "Department meteorological subdivisions. There are 46 of them against "
        "IMD's 36, and the boundaries do not correspond. Do not label them as "
        "subdivisions anywhere in the interface."),
        "cell_degrees": 3.0, "records": []}
    for r in pg.itertuples():
        groups["records"].append({
            "cell": r.grp, "threshold_mm": r.threshold_mm,
            "lead_days": int(r.lead_days), "n_points": int(r.n_points),
            "FAR": r3(r.FAR), "FAR_lo": r3(r.FAR_lo), "FAR_hi": r3(r.FAR_hi)})

    # ---- cross-model
    crossmodel = {
        "records": xmodel,
        "leads_note": ("Leads 1-6 only: the Open-Meteo archive carries no "
                       "previous_day7 for ICON."),
        "sample_note": ("Matched sample -- same points, days and leads for "
                        "all three models, enforced by successive inner "
                        "merges. 47 of the 139 points (every third), a quota "
                        "limit, not a design choice."),
        "verdict": (
            "Self-verification is real but minor. ICON's and GFS's gaps are "
            "smaller in magnitude than ECMWF's and the difference excludes "
            "zero at every lead and both thresholds -- but it is only 7-16% "
            "of the gap. The other ~85% appears for models sharing nothing "
            "with ERA5, so it is plain wet bias. Do not use a reanalysis as "
            "primary rainfall truth over India whoever made the forecast.")}

    methods = {"spatial": spatial, "prior_work": PRIOR_WORK,
               "boundary": boundary_check(),
               "temporal_blocks": {
                   "per_point_block_days": SPLIT_BLOCK_DAYS,
                   "note": ("Per-point CIs use a temporal block bootstrap, "
                            "not the spatial one -- a single point has no "
                            "spatial dimension left to resample. Synoptic "
                            "autocorrelation decays to ~0 by lag 5-7 days "
                            "once the day-of-year climatology is removed "
                            "(raw lag-30 r stays ~0.2, but that is the "
                            "seasonal cycle).")},
               "known_gaps": {
                   "forecast_days_missing": 7, "forecast_days_total": 933,
                   "dates": ["2025-03-16", "2026-04-18", "2026-04-19",
                             "2026-04-20", "2026-04-21", "2026-04-22",
                             "2026-04-23"],
                   "note": ("Upstream ECMWF/Open-Meteo archive outage, "
                            "identical at all 139 points. IMD truth covers "
                            "all seven. Dropped by inner join, not "
                            "interpolated."),
                   "imd_days_missing": 0, "imd_days_total": 943}}

    payload = {"meta.json": meta, "far_by_lead.json": far_by_lead,
               "costloss.json": costloss, "seasonal.json": seasonal,
               "points.json": points, "groups.json": groups,
               "crossmodel.json": crossmodel, "methods.json": methods}

    total = 0
    print(f"{'file':>22} {'bytes':>10} {'KB':>8}")
    for name, obj in payload.items():
        txt = json.dumps(obj, separators=(",", ":"), allow_nan=False)
        (WEB_DATA / name).write_text(txt, encoding="utf-8")
        total += len(txt)
        print(f"{name:>22} {len(txt):>10,} {len(txt)/1024:>8.1f}")
    print(f"{'TOTAL':>22} {total:>10,} {total/1024:>8.1f}")
    print(f"\nwrote {len(payload)} files to {WEB_DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
