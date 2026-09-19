"""Cost-loss value of the rainfall forecast, by lead time.

Standard static cost-loss decision model (Richardson 2000; Wilks 2001).

A decision-maker can pay C to protect against an event that, unprotected,
costs L. The cost-loss ratio is alpha = C/L. With contingency counts
a=hits, b=false alarms, c=misses, d=correct negatives, N total, and
climatological event frequency s = (a+c)/N, expenses per unit L are:

    act on the forecast   E_f    = alpha*(a+b)/N + c/N
    climatology           E_clim = min(alpha, s)      (always act, or never)
    perfect foresight     E_perf = alpha*s

and the value score is

    V = (E_clim - E_f) / (E_clim - E_perf)

V = 1 is perfect foresight, V = 0 is no better than the cheaper
climatological rule, V < 0 means acting on the forecast is worse than
ignoring it. The question "does the forecast beat climatology" is exactly
V > 0, and the answer depends on alpha as well as on lead time.

ASSUMPTIONS, stated plainly -- these are the model's, not measurements:

  1. The decision is binary: protect or do not protect, once per day.
  2. C is paid whenever action is taken, whether or not the event occurs.
  3. L is incurred only when the event occurs and no action was taken.
  4. Protection is perfect: acting removes the loss entirely.
  5. C and L are constant -- they do not scale with rainfall amount, so a
     5 mm day and a 200 mm day are the same "event". For spray decisions
     this is defensible; for flood damage it is not.
  6. The user acts if and only if the deterministic forecast says wet.
     No probability threshold is available to tune (the archive has no
     probability of precipitation), so this is a single operating point,
     not an ROC curve. A probabilistic forecast would dominate this.
  7. The climatological reference knows s but nothing about any given day.
  8. Risk-neutral: the decision-maker minimises expected expense and is
     indifferent to variance.
  9. No cost of lead time itself -- acting on 7 days' notice costs the same
     as acting on 1 day's notice, and there is no option to defer.
 10. s is estimated from this sample, not from a long climatology.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from config import (ANALYSIS_END, ANALYSIS_START, BLOCK_DEG, INTERIM, LEADS,
                    RESULTS, THRESHOLDS)

ALPHAS = np.round(np.arange(0.02, 0.99, 0.02), 4)
N_BOOT = 2000
RNG = np.random.default_rng(20260917)


def value(M: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    a, b, c, d = M.sum(axis=0)
    n = a + b + c + d
    s = (a + c) / n
    e_f = alpha * (a + b) / n + c / n
    e_cl = np.minimum(alpha, s)
    e_pf = alpha * s
    with np.errstate(divide="ignore", invalid="ignore"):
        v = (e_cl - e_f) / (e_cl - e_pf)
    return np.where(np.isfinite(v), v, np.nan)


def main() -> int:
    fc = pd.read_parquet(INTERIM / "forecast_daily.parquet")
    imd = pd.read_parquet(INTERIM / "imd_daily.parquet")
    for f in (fc, imd):
        f["date"] = pd.to_datetime(f["date"])
    df = fc.merge(imd, on=["point_id", "date"], how="inner")
    df = df[(df.date >= pd.Timestamp(ANALYSIS_START))
            & (df.date <= pd.Timestamp(ANALYSIS_END))]
    pts = pd.read_csv(INTERIM / "points.csv").set_index("point_id")
    codes, uniq = pd.factorize(df.point_id, sort=True)
    p = pts.loc[uniq]
    lab = np.array([f"{int(la // BLOCK_DEG)}_{int(lo // BLOCK_DEG)}"
                    for la, lo in zip(p.lat, p.lon)])
    ub = np.unique(lab)
    rbb = [np.where(lab == x)[0] for x in ub]

    rows = []
    for thr in THRESHOLDS:
        o = df["imd_mm"].to_numpy() >= thr
        print(f"\n===== wet day >= {thr} mm =====")
        print(f"{'lead':>4} {'base rate s':>12} {'alpha range where V>0':>24} "
              f"{'max V':>7} {'at alpha':>9} {'V(a=0.1)':>9} {'V(a=0.3)':>9}")
        for lead in LEADS:
            f = df[f"precipitation_previous_day{lead}"].to_numpy() >= thr
            M = np.zeros((len(uniq), 4), dtype=np.int64)
            np.add.at(M, (codes, 0), (f & o))
            np.add.at(M, (codes, 1), (f & ~o))
            np.add.at(M, (codes, 2), (~f & o))
            np.add.at(M, (codes, 3), (~f & ~o))
            a, b, c, d = M.sum(axis=0)
            n = a + b + c + d
            s = (a + c) / n
            v = value(M, ALPHAS)
            pos = ALPHAS[v > 0]
            rng_txt = (f"{pos.min():.2f} - {pos.max():.2f}" if len(pos)
                       else "none (never beats clim)")
            imax = int(np.nanargmax(v))
            # block-bootstrap CI for V at two illustrative alphas
            cis = {}
            for a0 in (0.10, 0.30):
                acc = np.empty(N_BOOT)
                for i in range(N_BOOT):
                    sel = np.concatenate(
                        [rbb[k] for k in RNG.integers(0, len(ub), size=len(ub))])
                    acc[i] = value(M[sel], np.array([a0]))[0]
                cis[a0] = (float(np.nanpercentile(acc, 2.5)),
                           float(np.nanpercentile(acc, 97.5)))
            print(f"{lead:>4} {s:>12.4f} {rng_txt:>24} {np.nanmax(v):>7.3f} "
                  f"{ALPHAS[imax]:>9.2f} {value(M,np.array([0.1]))[0]:>9.3f} "
                  f"{value(M,np.array([0.3]))[0]:>9.3f}")
            for a0, (lo, hi) in cis.items():
                rows.append(dict(threshold_mm=thr, lead_days=lead, alpha=a0,
                                 V=float(value(M, np.array([a0]))[0]),
                                 V_lo=lo, V_hi=hi, base_rate=s))
            for al, vv in zip(ALPHAS, v):
                rows.append(dict(threshold_mm=thr, lead_days=lead, alpha=al,
                                 V=float(vv), V_lo=np.nan, V_hi=np.nan,
                                 base_rate=s))
        print(f"     (climatological rule is 'always act' when alpha < s, "
              f"'never act' when alpha > s)")

    out = pd.DataFrame(rows).drop_duplicates(
        subset=["threshold_mm", "lead_days", "alpha"], keep="first")
    out.to_csv(RESULTS / "costloss_value.csv", index=False)
    print(f"\nwrote {RESULTS/'costloss_value.csv'}")

    print("\n=== V at alpha = 0.10 and 0.30, with 8-deg block bootstrap CI ===")
    ci = pd.read_csv(RESULTS / "costloss_value.csv")
    ci = ci[ci.V_lo.notna()]
    for thr in THRESHOLDS:
        for a0 in (0.10, 0.30):
            s = ci[(ci.threshold_mm == thr) & (ci.alpha == a0)
                   ].sort_values("lead_days")
            txt = "  ".join(f"L{int(r.lead_days)}:{r.V:.3f}"
                            f"({r.V_lo:.3f},{r.V_hi:.3f})"
                            for r in s.itertuples())
            print(f"  >= {thr} mm, alpha={a0}: {txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
