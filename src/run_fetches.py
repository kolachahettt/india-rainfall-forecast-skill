"""Drive the forecast and ERA5 fetches to completion in ONE process.

This replaces an earlier shell orchestrator. That design kept orphaning:
Git Bash spawns a wrapper bash.exe per script, its `$$` is an MSYS pid that
does not match the Windows pid table, and a background shell survives session
teardown with its `while` loop intact. Killing the Python children just made
the surviving loops respawn new ones -- eight orchestrators ended up racing
the same point list and blew the daily API quota.

One process, one lock, one thing to look for in the process table.

Both fetches are resumable (one parquet part per point), so this can be
stopped and restarted at any time without losing work.
"""
from __future__ import annotations

import sys
import time
import traceback

import pandas as pd

from config import INTERIM
from fetch_openmeteo import build, fetch_point, single_instance

PAUSE_BETWEEN_ROUNDS = 30


def points() -> pd.DataFrame:
    return pd.read_csv(INTERIM / "points.csv")


def remaining(source: str, pts: pd.DataFrame) -> list:
    parts = INTERIM / f"{source}_parts"
    parts.mkdir(parents=True, exist_ok=True)
    return [p for p in pts.itertuples()
            if not (parts / f"{p.point_id}.parquet").exists()]


def run_source(source: str, pts: pd.DataFrame) -> bool:
    url, want, extra = build(source)
    parts = INTERIM / f"{source}_parts"
    todo = remaining(source, pts)
    print(f"\n=== {source}: {len(pts) - len(todo)}/{len(pts)} done, "
          f"{len(todo)} to fetch ===", flush=True)

    consecutive_failures = 0
    while todo:
        t0 = time.time()
        for i, p in enumerate(todo, 1):
            try:
                df = fetch_point(p.lat, p.lon, url, want, extra)
            except Exception as exc:
                consecutive_failures += 1
                print(f"  {p.point_id} FAILED ({consecutive_failures} in a row): "
                      f"{str(exc)[:120]}", flush=True)
                if consecutive_failures >= 10:
                    print(f"  {source}: 10 consecutive failures, pausing "
                          f"{PAUSE_BETWEEN_ROUNDS}s", flush=True)
                    time.sleep(PAUSE_BETWEEN_ROUNDS)
                    consecutive_failures = 0
                continue
            consecutive_failures = 0
            out = df.reset_index().rename(columns={"imd_day": "date"})
            out.insert(0, "point_id", p.point_id)
            out.to_parquet(parts / f"{p.point_id}.parquet", index=False)
            done = len(pts) - len(remaining(source, pts))
            if i % 5 == 0 or i == len(todo):
                el = time.time() - t0
                print(f"  [{done}/{len(pts)}] {p.point_id} rows={len(out)} "
                      f"{el/i:.0f}s/pt", flush=True)

        todo = remaining(source, pts)
        if todo:
            print(f"  {source}: {len(todo)} still missing, retrying after "
                  f"{PAUSE_BETWEEN_ROUNDS}s", flush=True)
            time.sleep(PAUSE_BETWEEN_ROUNDS)

    # combine parts into the single table the analysis reads
    files = sorted(parts.glob("*.parquet"))
    allp = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    out_path = INTERIM / f"{source}_daily.parquet"
    allp.to_parquet(out_path, index=False)
    print(f"  wrote {out_path.name}: rows={len(allp):,} "
          f"points={allp.point_id.nunique()}", flush=True)
    return True


def main() -> int:
    with single_instance("driver"):
        pts = points()
        for source in ("forecast", "era5"):
            try:
                run_source(source, pts)
            except KeyboardInterrupt:
                print("interrupted -- progress is on disk, rerun to resume")
                return 130
            except Exception:
                traceback.print_exc()
                return 1
        print("\nALL FETCHES COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
