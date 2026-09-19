"""Monsoon (JJAS) versus non-monsoon skill, all metrics, all leads.

Same contingency machinery and same 8-degree spatial block bootstrap as the
pooled analysis -- only the day set changes. Splitting matters because the
all-season numbers are a weighted blend of two very different regimes: the
monsoon supplies most of the wet days, so it dominates the pooled figure,
while the dry season is mostly correct-negatives and can flatter skill
scores that reward them.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from config import (ANALYSIS_END, ANALYSIS_START, BLOCK_DEG, INTERIM, LEADS,
                    RESULTS, THRESHOLDS)

N_BOOT = 4000
RNG = np.random.default_rng(20260917)
MONSOON = [6, 7, 8, 9]


def metrics(a, b, c, d):
    a, b, c, d = float(a), float(b), float(c), float(d)
    pod = a / (a + c) if (a + c) else np.nan
    far = b / (a + b) if (a + b) else np.nan
    csi = a / (a + b + c) if (a + b + c) else np.nan
    bias = (a + b) / (a + c) if (a + c) else np.nan
    den = (a + c) * (c + d) + (a + b) * (b + d)
    hss = (2 * (a * d - b * c) / den) if den else np.nan
    return dict(POD=pod, FAR=far, CSI=csi, BIAS=bias, HSS=hss)


def main() -> int:
    fc = pd.read_parquet(INTERIM / "forecast_daily.parquet")
    imd = pd.read_parquet(INTERIM / "imd_daily.parquet")
    for f in (fc, imd):
        f["date"] = pd.to_datetime(f["date"])
    df = fc.merge(imd, on=["point_id", "date"], how="inner")
    df = df[(df.date >= pd.Timestamp(ANALYSIS_START))
            & (df.date <= pd.Timestamp(ANALYSIS_END))]
    pts = pd.read_csv(INTERIM / "points.csv").set_index("point_id")
    df["season"] = np.where(df.date.dt.month.isin(MONSOON),
                            "monsoon (JJAS)", "non-monsoon (ONDJFMAM)")

    rows = []
    for season, sub in df.groupby("season"):
        codes, uniq = pd.factorize(sub.point_id, sort=True)
        p = pts.loc[uniq]
        lab = np.array([f"{int(la // BLOCK_DEG)}_{int(lo // BLOCK_DEG)}"
                        for la, lo in zip(p.lat, p.lon)])
        ub = np.unique(lab)
        rbb = [np.where(lab == b)[0] for b in ub]
        o_all = sub["imd_mm"].to_numpy()
        for thr in THRESHOLDS:
            o = o_all >= thr
            for lead in LEADS:
                f = sub[f"precipitation_previous_day{lead}"].to_numpy() >= thr
                M = np.zeros((len(uniq), 4), dtype=np.int64)
                np.add.at(M, (codes, 0), (f & o))
                np.add.at(M, (codes, 1), (f & ~o))
                np.add.at(M, (codes, 2), (~f & o))
                np.add.at(M, (codes, 3), (~f & ~o))
                pt = metrics(*M.sum(axis=0))
                acc = {k: np.empty(N_BOOT) for k in pt}
                for i in range(N_BOOT):
                    sel = np.concatenate(
                        [rbb[k] for k in RNG.integers(0, len(ub), size=len(ub))])
                    m = metrics(*M[sel].sum(axis=0))
                    for k in pt:
                        acc[k][i] = m[k]
                rec = dict(season=season, threshold_mm=thr, lead_days=lead,
                           n=int(len(sub)),
                           base_rate=float(o.mean()), **pt)
                for k in pt:
                    rec[f"{k}_lo"] = float(np.nanpercentile(acc[k], 2.5))
                    rec[f"{k}_hi"] = float(np.nanpercentile(acc[k], 97.5))
                rows.append(rec)

    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "seasonal_metrics.csv", index=False)

    for thr in THRESHOLDS:
        print(f"\n===== wet day >= {thr} mm =====")
        for season in sorted(out.season.unique()):
            s = out[(out.season == season)
                    & (out.threshold_mm == thr)].sort_values("lead_days")
            print(f"\n  {season}   n={int(s.n.iloc[0]):,} point-days, "
                  f"wet-day base rate {s.base_rate.iloc[0]*100:.1f}%")
            print(f"  {'lead':>4} {'POD':>6} {'FAR':>6} {'FAR 95% CI':>17} "
                  f"{'CSI':>6} {'HSS':>6} {'BIAS':>6}")
            for r in s.itertuples():
                print(f"  {r.lead_days:>4} {r.POD:>6.3f} {r.FAR:>6.3f} "
                      f"({r.FAR_lo:.3f}-{r.FAR_hi:.3f}) {r.CSI:>6.3f} "
                      f"{r.HSS:>6.3f} {r.BIAS:>6.2f}")
    print(f"\nwrote {RESULTS/'seasonal_metrics.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
