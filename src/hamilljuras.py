"""Hamill & Juras (2006): how much of the pooled skill is geography?

Hamill, T. M. and J. Juras, 2006: Measuring forecast skill -- is it real
skill or is it the varying climatology? QJRMS 132, 2905-2923.
doi:10.1256/qj.06.25

Their point. A skill score is referenced to a climatological expectation. If
you pool locations whose climatologies differ, the reference becomes a
mixture no single location experiences, and the score rewards the forecast
for telling wet PLACES from dry PLACES -- a geographic signal that is free.
They show positive skill arising from forecasts that are pure random draws
from each location's own climatology, growing with the spread of base rates.

This study pools 139 locations whose wet-day base rates run from about 10% to
52%, so the critique lands squarely. But it does not land on everything:

  * FAR / PPV / NPV / POD / BIAS are RAW CONDITIONAL PROBABILITIES. Pooling
    them does not manufacture skill. It produces a frequency-weighted
    composite -- "what happens on an average forecast-day in this sample",
    not "what happens at an average location". That is a question of
    interpretation, and the two answers are computed here side by side.

  * HSS IS a skill score and is exposed. Its chance-expectation term is built
    from the marginals of whichever table it is handed, so a pooled table
    carries a mixture climatology.

Three quantities are produced for each (threshold, lead):

  pooled        sum the 139 contingency tables, then score. What the site
                and metrics.csv have reported so far.
  stratified    score each location against its own table, then average the
                scores. The standard remedy.
  null_pooled   the Hamill-Juras demonstration, on THIS data. At each point,
                replace the forecast with one that is statistically
                independent of the observation there but keeps the point's
                real forecast rate and real base rate. Every location then
                has exactly zero skill by construction. Pool those tables and
                score. Whatever comes out is pure base-rate artefact.

The null is computed in closed form rather than simulated: independence at a
point means the expected table is the outer product of its margins, so
a = n*f*o, b = n*f*(1-o), c = n*(1-f)*o, d = n*(1-f)*(1-o). That is exact and
has no Monte Carlo noise. A small simulation runs alongside it purely as a
check that the closed form is right.

Uncertainty is the same 8-degree spatial cluster bootstrap used everywhere
else, applied PAIRED: one block draw per iteration scores pooled and
stratified together, so the interval on the gap between them is paired.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from config import (ANALYSIS_END, ANALYSIS_START, BLOCK_DEG, INTERIM, LEADS,
                    RESULTS, THRESHOLDS)

N_BOOT = 4000
N_SIM = 400                 # only to verify the closed-form null
RNG = np.random.default_rng(20260919)


def hss(a, b, c, d):
    """Heidke skill score. Accepts scalars or equal-length arrays."""
    a, b, c, d = (np.asarray(x, dtype=float) for x in (a, b, c, d))
    den = (a + c) * (c + d) + (a + b) * (b + d)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0, 2 * (a * d - b * c) / np.where(den > 0, den, 1),
                        np.nan)


def ppv(a, b, c, d):
    a, b = np.asarray(a, float), np.asarray(b, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(a + b > 0, a / np.where(a + b > 0, a + b, 1), np.nan)


def npv(a, b, c, d):
    c, d = np.asarray(c, float), np.asarray(d, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(c + d > 0, d / np.where(c + d > 0, c + d, 1), np.nan)


SCORES = {"HSS": hss, "PPV": ppv, "NPV": npv}


def pooled(M, fn):
    """Score the summed table."""
    a, b, c, d = M.sum(axis=0)
    return float(fn(a, b, c, d))


def stratified(M, fn):
    """Score each row, then average the scores. nanmean: a point with no
    'rain' forecasts at all has an undefined PPV and must not poison the
    aggregate. Which points those are is reported alongside."""
    v = fn(M[:, 0], M[:, 1], M[:, 2], M[:, 3])
    return float(np.nanmean(v)), v


def null_table(M):
    """Expected per-point table if the forecast were independent of the
    observation at that point, holding the point's forecast rate and base
    rate at their measured values. Zero skill everywhere by construction."""
    n = M.sum(axis=1).astype(float)
    f = (M[:, 0] + M[:, 1]) / n          # forecast wet rate at this point
    o = (M[:, 0] + M[:, 2]) / n          # observed wet rate at this point
    return np.column_stack([n * f * o, n * f * (1 - o),
                            n * (1 - f) * o, n * (1 - f) * (1 - o)])


def simulate_null(M, n_sim=N_SIM):
    """Monte Carlo version of null_table, as a check on the closed form."""
    n = M.sum(axis=1).astype(int)
    f = (M[:, 0] + M[:, 1]) / n
    o = (M[:, 0] + M[:, 2]) / n
    out = np.empty(n_sim)
    for i in range(n_sim):
        T = np.zeros((len(n), 4))
        for j in range(len(n)):
            fc = RNG.random(n[j]) < f[j]
            ob = RNG.random(n[j]) < o[j]        # independent by construction
            T[j] = [np.sum(fc & ob), np.sum(fc & ~ob),
                    np.sum(~fc & ob), np.sum(~fc & ~ob)]
        out[i] = pooled(T, hss)
    return float(out.mean()), float(out.std())


def block_rows(point_ids):
    pts = pd.read_csv(INTERIM / "points.csv").set_index("point_id")
    p = pts.loc[list(point_ids)]
    lab = np.array([f"{int(la // BLOCK_DEG)}_{int(lo // BLOCK_DEG)}"
                    for la, lo in zip(p.lat, p.lon)])
    return [np.where(lab == b)[0] for b in np.unique(lab)]


def paired_ci(M, rows, n_boot=N_BOOT):
    """Pooled, stratified and their gap, on one shared block draw."""
    nb = len(rows)
    acc = {f"{k}_{w}": np.empty(n_boot)
           for k in SCORES for w in ("pooled", "strat", "gap")}
    for i in range(n_boot):
        sel = np.concatenate([rows[k] for k in RNG.integers(0, nb, size=nb)])
        S = M[sel]
        for k, fn in SCORES.items():
            p = pooled(S, fn)
            s, _ = stratified(S, fn)
            acc[f"{k}_pooled"][i] = p
            acc[f"{k}_strat"][i] = s
            acc[f"{k}_gap"][i] = p - s
    out = {}
    for k, v in acc.items():
        out[f"{k}_lo"] = float(np.nanpercentile(v, 2.5))
        out[f"{k}_hi"] = float(np.nanpercentile(v, 97.5))
    return out


def load():
    fc = pd.read_parquet(INTERIM / "forecast_daily.parquet")
    imd = pd.read_parquet(INTERIM / "imd_daily.parquet")
    for f in (fc, imd):
        f["date"] = pd.to_datetime(f["date"])
    df = fc.merge(imd, on=["point_id", "date"], how="inner")
    return df[(df.date >= pd.Timestamp(ANALYSIS_START))
              & (df.date <= pd.Timestamp(ANALYSIS_END))].reset_index(drop=True)


def counts(df, col, thr, codes, npts):
    f = df[col].to_numpy() >= thr
    o = df["imd_mm"].to_numpy() >= thr
    M = np.zeros((npts, 4), dtype=np.int64)
    np.add.at(M, (codes, 0), (f & o))
    np.add.at(M, (codes, 1), (f & ~o))
    np.add.at(M, (codes, 2), (~f & o))
    np.add.at(M, (codes, 3), (~f & ~o))
    return M


def main() -> int:
    df = load()
    rows_out = []
    for thr in THRESHOLDS:
        for lead in LEADS:
            col = f"precipitation_previous_day{lead}"
            sub = df.dropna(subset=[col, "imd_mm"])
            codes, uniq = pd.factorize(sub["point_id"], sort=True)
            M = counts(sub, col, thr, codes, len(uniq))
            rows = block_rows(uniq)

            base = (M[:, 0] + M[:, 2]) / M.sum(axis=1)
            rec = {"threshold_mm": thr, "lead_days": lead,
                   "n_points": len(uniq), "n_blocks": len(rows),
                   "base_rate_min": float(base.min()),
                   "base_rate_max": float(base.max()),
                   "base_rate_sd": float(base.std(ddof=1))}

            for k, fn in SCORES.items():
                p = pooled(M, fn)
                s, per = stratified(M, fn)
                q1, q3 = np.nanpercentile(per, [25, 75])
                rec |= {f"{k}_pooled": p, f"{k}_strat": s, f"{k}_gap": p - s,
                        f"{k}_median": float(np.nanmedian(per)),
                        f"{k}_q1": float(q1), f"{k}_q3": float(q3),
                        f"{k}_min": float(np.nanmin(per)),
                        f"{k}_max": float(np.nanmax(per)),
                        f"{k}_undefined_points": int(np.isnan(per).sum())}

            # the Hamill-Juras demonstration on this data
            N = null_table(M)
            rec["HSS_null_pooled"] = pooled(N, hss)
            rec["HSS_null_strat"] = float(np.nanmean(
                hss(N[:, 0], N[:, 1], N[:, 2], N[:, 3])))
            # share of the reported pooled skill that the null already gives
            rec["null_share_of_pooled"] = (rec["HSS_null_pooled"]
                                           / rec["HSS_pooled"])
            rec |= paired_ci(M, rows)
            rows_out.append(rec)

            print(f"  thr>={thr:<4} lead {lead}:  HSS pooled "
                  f"{rec['HSS_pooled']:.3f}  stratified {rec['HSS_strat']:.3f}"
                  f"  gap {rec['HSS_gap']:+.3f} "
                  f"[{rec['HSS_gap_lo']:+.3f},{rec['HSS_gap_hi']:+.3f}]"
                  f"  null {rec['HSS_null_pooled']:.3f}", flush=True)

    out = pd.DataFrame(rows_out)
    out.to_csv(RESULTS / "hamilljuras.csv", index=False)

    # ---- does the five-day boundary survive stratification? --------------
    # The page compares ECMWF's pooled HSS against the pooled HSS of the
    # day-1-held persistence ceiling. Both are pooled on the same sample, so
    # the base-rate inflation should largely cancel -- but "should" is not a
    # measurement, and the claim is load-bearing, so check it.
    print("\n=== five-day boundary under stratification ===", flush=True)
    imd = pd.read_parquet(INTERIM / "imd_daily.parquet")
    imd["date"] = pd.to_datetime(imd["date"])
    dfp = df.copy()
    for L in LEADS:
        lag = imd.rename(columns={"imd_mm": f"lag{L}_mm"}).copy()
        lag["date"] = lag["date"] + pd.Timedelta(days=L)
        dfp = dfp.merge(lag[["point_id", "date", f"lag{L}_mm"]],
                        on=["point_id", "date"], how="left")
    cross = []
    for thr in THRESHOLDS:
        ceil_p = ceil_s = None
        for lead in LEADS:
            col = f"precipitation_previous_day{lead}"
            sub = dfp.dropna(subset=[col, f"lag{lead}_mm", "lag1_mm", "imd_mm"])
            codes, uniq = pd.factorize(sub["point_id"], sort=True)
            n = len(uniq)
            Me = counts(sub, col, thr, codes, n)
            Mh = counts(sub, "lag1_mm", thr, codes, n)   # day-1-held ceiling
            if ceil_p is None:
                ceil_p, (ceil_s, _) = pooled(Mh, hss), stratified(Mh, hss)
            e_p, (e_s, _) = pooled(Me, hss), stratified(Me, hss)
            cross.append({"threshold_mm": thr, "lead_days": lead,
                          "ecmwf_pooled": e_p, "ecmwf_strat": e_s,
                          "ceiling_pooled": ceil_p, "ceiling_strat": ceil_s,
                          "above_pooled": e_p >= ceil_p,
                          "above_strat": e_s >= ceil_s})
            print(f"  thr>={thr:<4} lead {lead}: pooled {e_p:.3f} vs ceiling "
                  f"{ceil_p:.3f} -> {'above' if e_p >= ceil_p else 'BELOW'}   "
                  f"stratified {e_s:.3f} vs {ceil_s:.3f} -> "
                  f"{'above' if e_s >= ceil_s else 'BELOW'}", flush=True)
    pd.DataFrame(cross).to_csv(RESULTS / "hj_persistence_crossing.csv",
                               index=False)

    # ---- does the seasonal HSS inversion survive stratification? --------
    # The seasonal section's whole point is that HSS ranks the two seasons
    # opposite to FAR. Both seasonal HSS values are pooled across points, so
    # both carry the inflation; the question is whether the RANKING flips.
    print("\n=== seasonal HSS inversion under stratification ===", flush=True)
    MONSOON = [6, 7, 8, 9]
    df["season"] = np.where(df.date.dt.month.isin(MONSOON),
                            "monsoon (JJAS)", "non-monsoon")
    srows = []
    for thr in THRESHOLDS:
        for lead in LEADS:
            col = f"precipitation_previous_day{lead}"
            rec = {"threshold_mm": thr, "lead_days": lead}
            for season, ss in df.groupby("season"):
                sub = ss.dropna(subset=[col, "imd_mm"])
                codes, uniq = pd.factorize(sub["point_id"], sort=True)
                M = counts(sub, col, thr, codes, len(uniq))
                key = "mon" if season.startswith("monsoon") else "non"
                rec[f"{key}_pooled"] = pooled(M, hss)
                rec[f"{key}_strat"] = stratified(M, hss)[0]
                rec[f"{key}_ppv"] = pooled(M, ppv)
            rec["inversion_pooled"] = rec["non_pooled"] > rec["mon_pooled"]
            rec["inversion_strat"] = rec["non_strat"] > rec["mon_strat"]
            srows.append(rec)
            if lead == 1:
                print(f"  thr>={thr:<4} lead 1: pooled  non {rec['non_pooled']:.3f} "
                      f"vs monsoon {rec['mon_pooled']:.3f} -> inversion "
                      f"{rec['inversion_pooled']}", flush=True)
                print(f"  {'':11}  strat   non {rec['non_strat']:.3f} "
                      f"vs monsoon {rec['mon_strat']:.3f} -> inversion "
                      f"{rec['inversion_strat']}", flush=True)
    sdf = pd.DataFrame(srows)
    sdf.to_csv(RESULTS / "hj_seasonal.csv", index=False)
    print(f"  inversion holds pooled at {int(sdf.inversion_pooled.sum())}/"
          f"{len(sdf)} (threshold, lead) cells; stratified at "
          f"{int(sdf.inversion_strat.sum())}/{len(sdf)}")

    # verify the closed-form null against a simulation, once
    col = "precipitation_previous_day1"
    sub = df.dropna(subset=[col, "imd_mm"])
    codes, uniq = pd.factorize(sub["point_id"], sort=True)
    M = counts(sub, col, 1.0, codes, len(uniq))
    mu, sd = simulate_null(M)
    exact = pooled(null_table(M), hss)
    print(f"\nnull check (>=1mm, lead 1): closed form {exact:.4f}  "
          f"simulated {mu:.4f} +/- {sd:.4f}  "
          f"({abs(exact - mu) / sd:.2f} sd apart)")
    import json
    (RESULTS / "hj_null_check.json").write_text(json.dumps({
        "threshold_mm": 1.0, "lead_days": 1, "n_sim": N_SIM,
        "closed_form": exact, "simulated_mean": mu, "simulated_sd": sd,
        "sd_apart": abs(exact - mu) / sd,
        "note": ("The closed form is the exact expectation under "
                 "independence at every point; the simulation is only a "
                 "check that it was derived correctly.")},
        indent=1), encoding="utf-8")
    print(f"\nwrote {RESULTS/'hamilljuras.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
