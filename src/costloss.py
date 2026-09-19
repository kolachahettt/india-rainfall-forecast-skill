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


# --------------------------------------------------------------------------
# Hamill & Juras applied to the value score.
#
# E_clim = min(alpha, s) uses the POOLED base rate s, which is the same defect
# stratification fixed in the skill score: it hands every location a
# climatological fallback that no location actually has. A cell where it rains
# on 6% of days and one where it rains on 54% are being credited against the
# same 24% reference.
#
# Two corrected aggregates, because "the average location" and "the whole
# country's bill" are different questions:
#
#   strat_mean     V computed at each cell against that cell's own s_i, then
#                  averaged over cells. The value to a typical location.
#   strat_expense  sum each expense term over cells first, each with its own
#                  s_i, and form the ratio once. The total expense actually
#                  saved by decision-makers spread over all 139 cells. This is
#                  the closer analogue of the pooled figure and the one to
#                  quote against it.
#
# A prediction worth recording before running it: V > 0 exactly when
# alpha lies in [c/(c+d), a/(a+b)] = [1 - NPV, PPV]. The break-even WINDOW is
# therefore a function of the two conditional probabilities alone, and those
# barely moved under stratification (0.009 and 0.001). So the window should be
# close to unchanged even if the magnitude of V is not.
# --------------------------------------------------------------------------
def value_per_cell(M: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """(n_cells, n_alpha) value, each cell against its OWN climatology."""
    a, b, c, d = (M[:, i].astype(float)[:, None] for i in range(4))
    n = a + b + c + d
    s = (a + c) / n
    al = np.asarray(alpha, float)[None, :]
    e_f = al * (a + b) / n + c / n
    e_cl = np.minimum(al, s)
    e_pf = al * s
    with np.errstate(divide="ignore", invalid="ignore"):
        v = (e_cl - e_f) / (e_cl - e_pf)
    return np.where(np.isfinite(v), v, np.nan)


def value_strat_mean(M, alpha):
    return np.nanmean(value_per_cell(M, alpha), axis=0)


def value_strat_expense(M, alpha):
    """Aggregate the EXPENSES across cells, each against its own s_i, then
    take the ratio once. Cells are equally weighted here because every cell
    contributes the same number of days."""
    a, b, c, d = (M[:, i].astype(float)[:, None] for i in range(4))
    n = a + b + c + d
    s = (a + c) / n
    al = np.asarray(alpha, float)[None, :]
    e_f = (al * (a + b) / n + c / n).sum(axis=0)
    e_cl = np.minimum(al, s).sum(axis=0)
    e_pf = (al * s).sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        v = (e_cl - e_f) / (e_cl - e_pf)
    return np.where(np.isfinite(v), v, np.nan)


def window(alphas, v):
    """The alpha range over which V > 0, or None."""
    pos = alphas[v > 0]
    return (float(pos.min()), float(pos.max())) if len(pos) else None


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
            v_strat = value_strat_expense(M, ALPHAS)
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
                j = int(np.argmin(np.abs(ALPHAS - a0)))
                rows.append(dict(threshold_mm=thr, lead_days=lead, alpha=a0,
                                 V=float(value(M, np.array([a0]))[0]),
                                 V_strat=float(v_strat[j]),
                                 V_lo=lo, V_hi=hi, base_rate=s))
            for al, vv, vst in zip(ALPHAS, v, v_strat):
                rows.append(dict(threshold_mm=thr, lead_days=lead, alpha=al,
                                 V=float(vv), V_strat=float(vst),
                                 V_lo=np.nan, V_hi=np.nan, base_rate=s))
        print(f"     (climatological rule is 'always act' when alpha < s, "
              f"'never act' when alpha > s)")

    out = pd.DataFrame(rows).drop_duplicates(
        subset=["threshold_mm", "lead_days", "alpha"], keep="first")
    out.to_csv(RESULTS / "costloss_value.csv", index=False)
    print(f"\nwrote {RESULTS/'costloss_value.csv'}")

    # ---- Hamill & Juras exposure of the value score ---------------------
    print("\n===== pooled vs stratified climatology in E_clim =====")
    srows, ALPHA_CI = [], (0.10, 0.20, 0.30, 0.50)
    for thr in THRESHOLDS:
        o = df["imd_mm"].to_numpy() >= thr
        print(f"\n  wet day >= {thr} mm")
        print(f"  {'lead':>4} {'window pooled':>16} {'window strat':>16} "
              f"{'V@.1 pool':>10} {'strat':>7} {'gap':>7} "
              f"{'V@.3 pool':>10} {'strat':>7} {'gap':>7} {'maxV p/s':>13}")
        for lead in LEADS:
            f = df[f"precipitation_previous_day{lead}"].to_numpy() >= thr
            M = np.zeros((len(uniq), 4), dtype=np.int64)
            np.add.at(M, (codes, 0), (f & o))
            np.add.at(M, (codes, 1), (f & ~o))
            np.add.at(M, (codes, 2), (~f & o))
            np.add.at(M, (codes, 3), (~f & ~o))
            vp = value(M, ALPHAS)
            vs = value_strat_expense(M, ALPHAS)
            vm = value_strat_mean(M, ALPHAS)
            wp, ws = window(ALPHAS, vp), window(ALPHAS, vs)
            rec = {"threshold_mm": thr, "lead_days": lead,
                   "win_pooled_lo": wp[0], "win_pooled_hi": wp[1],
                   "win_strat_lo": ws[0], "win_strat_hi": ws[1],
                   "maxV_pooled": float(np.nanmax(vp)),
                   "maxV_strat": float(np.nanmax(vs)),
                   "argmax_pooled": float(ALPHAS[int(np.nanargmax(vp))]),
                   "argmax_strat": float(ALPHAS[int(np.nanargmax(vs))])}
            # paired block bootstrap on the gap, one draw scoring both
            for a0 in ALPHA_CI:
                aa = np.array([a0])
                acc = np.empty(N_BOOT)
                for i in range(N_BOOT):
                    sel = np.concatenate(
                        [rbb[k] for k in RNG.integers(0, len(ub), size=len(ub))])
                    acc[i] = (value(M[sel], aa)[0]
                              - value_strat_expense(M[sel], aa)[0])
                j = int(np.argmin(np.abs(ALPHAS - a0)))
                rec |= {f"V{a0}_pooled": float(vp[j]),
                        f"V{a0}_strat": float(vs[j]),
                        f"V{a0}_mean": float(vm[j]),
                        f"V{a0}_gap": float(vp[j] - vs[j]),
                        f"V{a0}_gap_lo": float(np.nanpercentile(acc, 2.5)),
                        f"V{a0}_gap_hi": float(np.nanpercentile(acc, 97.5))}
            srows.append(rec)
            print(f"  {lead:>4} {wp[0]:>7.2f}-{wp[1]:<8.2f} "
                  f"{ws[0]:>7.2f}-{ws[1]:<8.2f} "
                  f"{rec['V0.1_pooled']:>10.3f} {rec['V0.1_strat']:>7.3f} "
                  f"{rec['V0.1_gap']:>+7.3f} "
                  f"{rec['V0.3_pooled']:>10.3f} {rec['V0.3_strat']:>7.3f} "
                  f"{rec['V0.3_gap']:>+7.3f} "
                  f"{rec['maxV_pooled']:>6.3f}/{rec['maxV_strat']:<6.3f}",
                  flush=True)
    sdf = pd.DataFrame(srows)
    sdf.to_csv(RESULTS / "costloss_stratified.csv", index=False)
    print(f"\nwrote {RESULTS/'costloss_stratified.csv'}")

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
