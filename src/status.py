"""Progress of every stage. Safe to run at any time, including mid-fetch."""
from __future__ import annotations

import json

import pandas as pd

from config import (ANALYSIS_END, ANALYSIS_START, END, IMD_BYTES, IMD_GRD,
                    INTERIM, RESULTS, START, daterange)


def bar(done: int, total: int, width: int = 34) -> str:
    if not total:
        return "?"
    n = int(width * done / total)
    return f"[{'#' * n}{'.' * (width - n)}] {done}/{total} ({100*done/total:.0f}%)"


def main() -> int:
    print("=" * 62)
    print("  forecast-trust -- pipeline status")
    print("=" * 62)

    total_days = sum(1 for _ in daterange())
    have = sum(1 for p in IMD_GRD.glob("*.grd") if p.stat().st_size == IMD_BYTES)
    print(f"\n1. IMD grids ({START} .. {END})")
    print(f"   {bar(have, total_days)}")

    log = INTERIM / "imd_fetch_log.jsonl"
    if log.exists():
        recs = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
        n404 = sum(1 for r in recs if r["status"] == "missing_404")
        nfail = sum(1 for r in recs if r["status"] == "failed_transient")
        print(f"   genuinely absent (404): {n404}    "
              f"unresolved transient: {nfail}")
        if nfail:
            print("   -> rerun fetch_imd.py; transient failures are not gaps")

    npts = len(pd.read_csv(INTERIM / "points.csv"))
    for k, src in enumerate(("forecast", "era5"), start=2):
        parts = INTERIM / f"{src}_parts"
        n = len(list(parts.glob("*.parquet"))) if parts.exists() else 0
        print(f"\n{k}. Open-Meteo {src} ({ANALYSIS_START} .. {ANALYSIS_END})")
        print(f"   {bar(n, npts)}")
        if 0 < n < npts:
            d = pd.read_csv(INTERIM / "points.csv")
            done = {p.stem for p in parts.glob("*.parquet")}
            sub = d[d.point_id.isin(done)]
            print(f"   lat covered so far: {sub.lat.min()}-{sub.lat.max()} "
                  f"of {d.lat.min()}-{d.lat.max()}  "
                  f"(partial results are NOT nationally representative)")

    print("\n4. Derived tables")
    for name in ("imd_daily.parquet", "forecast_daily.parquet",
                 "era5_daily.parquet"):
        p = INTERIM / name
        if p.exists():
            df = pd.read_parquet(p)
            print(f"   {name:26} rows={len(df):>8,}  points={df.point_id.nunique()}")
        else:
            print(f"   {name:26} -")

    print("\n5. Results")
    for name in ("metrics.csv", "far_truth_source_gap.csv", "RESULTS.md"):
        p = RESULTS / name
        print(f"   {name:26} {'present' if p.exists() else '-'}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
