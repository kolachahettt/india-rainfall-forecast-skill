"""Test the self-verification hypothesis.

Claim under test: the large ERA5-minus-IMD gap in false alarm ratio is not
(only) ERA5's wet bias, but partly an artefact of scoring an ECMWF forecast
against ECMWF's own reanalysis. ERA5 is produced with the IFS model and
`ecmwf_ifs025` is the operational IFS forecast, so the two share model
lineage and convective parameterisation, hence share systematic error.

Discriminating prediction: if self-verification contributes, the gap should
be SMALLER for forecasts from other centres (DWD ICON, NCEP GFS) because
those do not share ERA5's lineage. If the gap is the same size for every
model, ERA5's wet bias explains it on its own and the self-verification
claim must be dropped.

Comparison is matched: the same points, days, leads and thresholds for all
three models. ICON carries no previous_day7 in the archive, so leads 1-6.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from config import (ANALYSIS_END, ANALYSIS_START, BLOCK_DEG, INTERIM, RESULTS,
                    THRESHOLDS)

LEADS = [1, 2, 3, 4, 5, 6]
N_BOOT = 4000
MODELS = {"ECMWF (IFS - same lineage as ERA5)": "forecast",
          "ICON (DWD)": "icon",
          "GFS (NCEP)": "gfs"}


def load_parts(source: str) -> pd.DataFrame:
    d = INTERIM / f"{source}_parts"
    files = sorted(d.glob("*.parquet")) if d.exists() else []
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    return df


def far(M: np.ndarray) -> float:
    a, b = M.sum(axis=0)[0], M.sum(axis=0)[1]
    return b / (a + b) if (a + b) else np.nan


def counts(fc_wet, ob_wet, codes, npts) -> np.ndarray:
    M = np.zeros((npts, 4), dtype=np.int64)
    np.add.at(M, (codes, 0), (fc_wet & ob_wet))
    np.add.at(M, (codes, 1), (fc_wet & ~ob_wet))
    np.add.at(M, (codes, 2), (~fc_wet & ob_wet))
    np.add.at(M, (codes, 3), (~fc_wet & ~ob_wet))
    return M


def block_index(point_ids):
    pts = pd.read_csv(INTERIM / "points.csv").set_index("point_id")
    p = pts.loc[list(point_ids)]
    lab = np.array([f"{int(la // BLOCK_DEG)}_{int(lo // BLOCK_DEG)}"
                    for la, lo in zip(p.lat, p.lon)])
    ub = np.unique(lab)
    return [np.where(lab == b)[0] for b in ub], len(ub)


def boot_stat(fn, rows_by_block, nb, n_boot=N_BOOT, seed=99):
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, nb, size=nb)
        sel = np.concatenate([rows_by_block[k] for k in pick])
        out[i] = fn(sel)
    return out


def main() -> int:
    imd = pd.read_parquet(INTERIM / "imd_daily.parquet")
    imd["date"] = pd.to_datetime(imd["date"])
    era = load_parts("era5").rename(columns={"precipitation": "era5_mm"})
    if era.empty:
        sys.exit("need era5 data")

    loaded = {}
    for label, src in MODELS.items():
        d = load_parts(src)
        if d.empty:
            print(f"SKIP {label}: no {src} data on disk")
            continue
        loaded[label] = d
    if len(loaded) < 2:
        sys.exit("need at least two models to compare")

    # matched sample: points present for EVERY loaded model
    common = set.intersection(*[set(d.point_id.unique()) for d in loaded.values()])
    common = sorted(common)
    print(f"matched sample: {len(common)} points common to "
          f"{len(loaded)} models\n")

    rows = []
    for thr in THRESHOLDS:
        for lead in LEADS:
            col = f"precipitation_previous_day{lead}"
            # ONE frame shared by every model: successive inner merges force
            # an identical (point, date) sample, without which the paired
            # model-vs-model bootstrap below would not actually be paired.
            # (Row counts per point differ by model -- ECMWF/ICON 926 days,
            # GFS 931 -- because the archives have different outage days.)
            base = imd.merge(era[["point_id", "date", "era5_mm"]],
                             on=["point_id", "date"], how="inner")
            base = base[base.point_id.isin(common)]
            for label, d in loaded.items():
                base = base.merge(
                    d[["point_id", "date", col]].rename(columns={col: label}),
                    on=["point_id", "date"], how="inner")
            base = base[(base.date >= pd.Timestamp(ANALYSIS_START))
                        & (base.date <= pd.Timestamp(ANALYSIS_END))]
            codes, uniq = pd.factorize(base.point_id, sort=True)
            rbb, nb = block_index(uniq)
            obs_i = base.imd_mm.to_numpy() >= thr
            obs_e = base.era5_mm.to_numpy() >= thr

            per_model = {}
            for label in loaded:
                f = base[label].to_numpy() >= thr
                Mi = counts(f, obs_i, codes, len(uniq))
                Me = counts(f, obs_e, codes, len(uniq))
                gap = lambda sel, Mi=Mi, Me=Me: far(Me[sel]) - far(Mi[sel])
                s = boot_stat(gap, rbb, nb)
                lo, hi = np.percentile(s, [2.5, 97.5])
                per_model[label] = dict(
                    far_imd=far(Mi), far_era5=far(Me),
                    gap=far(Me) - far(Mi), gap_lo=lo, gap_hi=hi,
                    n=int(len(base)), Mi=Mi, Me=Me, rbb=rbb, nb=nb)
                rows.append({"threshold_mm": thr, "lead_days": lead,
                             "model": label, "far_imd": far(Mi),
                             "far_era5": far(Me), "gap": far(Me) - far(Mi),
                             "gap_lo": lo, "gap_hi": hi, "n": len(base)})

            if lead == 1:
                print(f"===== wet day >= {thr} mm, lead 1 "
                      f"(n={per_model[list(per_model)[0]]['n']:,} point-days/model) =====")
                print(f"{'model':>36} {'FAR vs IMD':>11} {'FAR vs ERA5':>12} "
                      f"{'gap':>8} {'gap 95% CI':>20}")
                for label, v in per_model.items():
                    print(f"{label:>36} {v['far_imd']:>11.4f} {v['far_era5']:>12.4f} "
                          f"{v['gap']:>+8.4f} ({v['gap_lo']:+.4f},{v['gap_hi']:+.4f})")
                # paired test: does a non-IFS model's gap differ from ECMWF's?
                base = [k for k in per_model if k.startswith("ECMWF")]
                if base:
                    b = per_model[base[0]]
                    for label, v in per_model.items():
                        if label == base[0]:
                            continue
                        diff = lambda sel, v=v, b=b: ((far(v["Me"][sel]) - far(v["Mi"][sel]))
                                                      - (far(b["Me"][sel]) - far(b["Mi"][sel])))
                        s = boot_stat(diff, b["rbb"], b["nb"], seed=123)
                        lo, hi = np.percentile(s, [2.5, 97.5])
                        obs = v["gap"] - b["gap"]
                        # Gaps are negative, so a POSITIVE difference means
                        # this model's gap is smaller in MAGNITUDE than
                        # ECMWF's -- which is what supports self-verification.
                        share = abs(obs) / abs(b["gap"]) * 100
                        if lo > 0:
                            verdict = (f"gap is SMALLER in magnitude than "
                                       f"ECMWF's by {abs(obs):.4f} "
                                       f"({share:.0f}% of ECMWF's gap) "
                                       f"-> supports self-verification")
                        elif hi < 0:
                            verdict = ("gap is LARGER in magnitude than "
                                       "ECMWF's -> contradicts "
                                       "self-verification")
                        else:
                            verdict = ("no significant difference from ECMWF "
                                       "-> wet bias alone")
                        print(f"\n  {label} gap minus ECMWF gap: {obs:+.4f} "
                              f"95% CI ({lo:+.4f},{hi:+.4f})\n    -> {verdict}")
                print()

    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "crossmodel_far_gap.csv", index=False)
    print(f"wrote {RESULTS/'crossmodel_far_gap.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
