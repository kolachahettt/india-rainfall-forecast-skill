"""Persistence benchmark: does ECMWF beat "yesterday happens again"?

Murphy (1992) requires a skill score to be referenced against the most
accurate NAIVE method available, not merely against climatology. For daily
rainfall OCCURRENCE at short leads, persistence is usually that method:
monsoon wet spells last several days, so yesterday is a strong predictor of
today. Reporting ECMWF skill without this comparison is the first thing a
verification reviewer objects to.

Two forms are computed. They are NOT equally legitimate:

  lead-L persistence   obs(D - L) predicts day D at lead L.
                       Uses only information available when the lead-L
                       decision is actually taken. THIS IS THE FAIR
                       BENCHMARK and the one to quote.

  day-1-held           obs(D - 1) predicts day D at every lead.
                       For L > 1 this peeks at data the decision-maker does
                       not have. It is not a competitor; it is an UPPER
                       BOUND on what any persistence rule could achieve,
                       useful only to show how fast real persistence decays
                       relative to its own ceiling. At L = 1 the two forms
                       are identical by construction.

Comparison is on the matched sample: only point-days where both the ECMWF
lead-L forecast and the persistence predictor exist. ECMWF is re-scored on
that same restricted sample, so the two columns are strictly paired and the
difference is meaningful.

Uncertainty is a PAIRED cluster bootstrap over BLOCK_DEG spatial blocks: each
iteration draws one set of blocks and scores both systems on it, so the
interval on the difference accounts for the fact that they are evaluated on
the same rainfall.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from config import (ANALYSIS_END, ANALYSIS_START, BLOCK_DEG, INTERIM, LEADS,
                    RESULTS, THRESHOLDS)

N_BOOT = 4000
RNG = np.random.default_rng(20260919)


def scores(a, b, c, d) -> dict[str, float]:
    """PPV/NPV/BIAS/HSS/POD from a contingency table (scalars or arrays)."""
    a, b, c, d = (np.asarray(x, dtype=float) for x in (a, b, c, d))
    with np.errstate(divide="ignore", invalid="ignore"):
        ppv = a / (a + b)
        npv = d / (c + d)
        pod = a / (a + c)
        bias = (a + b) / (a + c)
        den = (a + c) * (c + d) + (a + b) * (b + d)
        hss = 2 * (a * d - b * c) / den
    return {"PPV": ppv, "NPV": npv, "POD": pod, "BIAS": bias, "HSS": hss}


KEYS = ["PPV", "NPV", "POD", "BIAS", "HSS"]


def per_point_counts(codes, npts, pred_wet, obs_wet) -> np.ndarray:
    """(npts, 4) array of hits / false alarms / misses / correct negatives."""
    out = np.zeros((npts, 4), dtype=np.int64)
    np.add.at(out, (codes, 0), (pred_wet & obs_wet))
    np.add.at(out, (codes, 1), (pred_wet & ~obs_wet))
    np.add.at(out, (codes, 2), (~pred_wet & obs_wet))
    np.add.at(out, (codes, 3), (~pred_wet & ~obs_wet))
    return out


def block_rows(point_ids) -> list[np.ndarray]:
    pts = pd.read_csv(INTERIM / "points.csv").set_index("point_id")
    p = pts.loc[list(point_ids)]
    lab = np.array([f"{int(la // BLOCK_DEG)}_{int(lo // BLOCK_DEG)}"
                    for la, lo in zip(p.lat, p.lon)])
    return [np.where(lab == b)[0] for b in np.unique(lab)]


def paired_ci(systems: dict[str, np.ndarray], rows: list[np.ndarray],
              ref: str, n_boot: int = N_BOOT) -> dict[str, float]:
    """Bootstrap every system, and every system's difference from `ref`.

    One block draw per iteration, shared by all systems: the interval on the
    difference is therefore paired and much tighter than differencing two
    independent intervals would suggest.
    """
    nb = len(rows)
    names = list(systems)
    acc = {(s, k): np.empty(n_boot) for s in names for k in KEYS}
    dif = {(s, k): np.empty(n_boot) for s in names if s != ref for k in KEYS}
    for i in range(n_boot):
        sel = np.concatenate([rows[k] for k in RNG.integers(0, nb, size=nb)])
        got = {}
        for s in names:
            a, b, c, d = systems[s][sel].sum(axis=0)
            got[s] = scores(a, b, c, d)
            for k in KEYS:
                acc[(s, k)][i] = got[s][k]
        for s in names:
            if s == ref:
                continue
            for k in KEYS:
                dif[(s, k)][i] = got[ref][k] - got[s][k]
    out = {}
    for (s, k), v in acc.items():
        out[f"{s}_{k}_lo"] = float(np.nanpercentile(v, 2.5))
        out[f"{s}_{k}_hi"] = float(np.nanpercentile(v, 97.5))
    for (s, k), v in dif.items():
        out[f"d_{s}_{k}_lo"] = float(np.nanpercentile(v, 2.5))
        out[f"d_{s}_{k}_hi"] = float(np.nanpercentile(v, 97.5))
        # share of draws in which ECMWF is ahead -- a one-sided read
        out[f"d_{s}_{k}_pwin"] = float(np.mean(v > 0))
    return out


def load() -> pd.DataFrame:
    """Forecast + IMD truth + IMD lagged 1..7 days, on the analysis window.

    The lags are built BEFORE the window is clipped, so lead-7 persistence on
    the first analysis day uses real observations from 2024-02-04 rather than
    dropping the day.
    """
    fc = pd.read_parquet(INTERIM / "forecast_daily.parquet")
    imd = pd.read_parquet(INTERIM / "imd_daily.parquet")
    for f in (fc, imd):
        f["date"] = pd.to_datetime(f["date"])
    df = fc.merge(imd, on=["point_id", "date"], how="inner")

    for L in LEADS:
        lag = imd.rename(columns={"imd_mm": f"lag{L}_mm"}).copy()
        lag["date"] = lag["date"] + pd.Timedelta(days=L)
        df = df.merge(lag[["point_id", "date", f"lag{L}_mm"]],
                      on=["point_id", "date"], how="left")

    lo, hi = pd.Timestamp(ANALYSIS_START), pd.Timestamp(ANALYSIS_END)
    return df[(df.date >= lo) & (df.date <= hi)].reset_index(drop=True)


def main() -> int:
    df = load()
    print(f"point-days {len(df):,}  points {df.point_id.nunique()}  "
          f"{df.date.min().date()}..{df.date.max().date()}")

    rows_out, diag = [], []
    for thr in THRESHOLDS:
        for L in LEADS:
            fc_col = f"precipitation_previous_day{L}"
            # matched sample: ECMWF, lead-L persistence and day-1-held
            # persistence must all be available on the same point-days
            sub = df.dropna(subset=[fc_col, f"lag{L}_mm", "lag1_mm",
                                    "imd_mm"])
            codes, uniq = pd.factorize(sub["point_id"], sort=False)
            obs = sub["imd_mm"].to_numpy() >= thr
            preds = {
                "ECMWF": sub[fc_col].to_numpy() >= thr,
                "persist_leadL": sub[f"lag{L}_mm"].to_numpy() >= thr,
                "persist_day1held": sub["lag1_mm"].to_numpy() >= thr,
            }
            systems = {s: per_point_counts(codes, len(uniq), p, obs)
                       for s, p in preds.items()}
            rows = block_rows(uniq)
            ci = paired_ci(systems, rows, ref="ECMWF")

            rec = {"threshold_mm": thr, "lead_days": L, "n": len(sub),
                   "n_points": len(uniq), "n_blocks": len(rows),
                   "obs_wet_rate": float(obs.mean())}
            for s, cnt in systems.items():
                a, b, c, d = cnt.sum(axis=0)
                sc = scores(a, b, c, d)
                for k in KEYS:
                    rec[f"{s}_{k}"] = float(sc[k])
                rec[f"{s}_a"], rec[f"{s}_b"] = int(a), int(b)
                rec[f"{s}_c"], rec[f"{s}_d"] = int(c), int(d)
            rec |= ci
            rows_out.append(rec)

            diag.append(
                f"  thr>={thr:<4} lead {L}:  "
                f"PPV  ECMWF {rec['ECMWF_PPV']:.3f}  "
                f"persist(L) {rec['persist_leadL_PPV']:.3f}  "
                f"diff {rec['ECMWF_PPV']-rec['persist_leadL_PPV']:+.3f} "
                f"[{rec['d_persist_leadL_PPV_lo']:+.3f},"
                f"{rec['d_persist_leadL_PPV_hi']:+.3f}]")
            print(diag[-1], flush=True)

    out = pd.DataFrame(rows_out)
    out.to_csv(RESULTS / "persistence_benchmark.csv", index=False)
    print(f"\nwrote {RESULTS/'persistence_benchmark.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
