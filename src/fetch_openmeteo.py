"""Fetch Open-Meteo hourly precipitation and aggregate to IMD rainfall days.

Two sources, same aggregation:

  --source forecast : previous-runs archive, pinned to ecmwf_ifs025,
                      leads 1-7 (precipitation_previous_dayN)
  --source era5     : ERA5 reanalysis from the archive API, used only as the
                      robustness-check truth

Aggregation window is the IMD rainfall day: 0300 UTC (D-1) -> 0300 UTC (D),
labelled day D. Every hour is mapped with (ts - 3h).date() + 1 day, and a day
is kept only if all 24 hours are present and non-null.

Two failure modes learned the hard way, both handled here:

1. The previous-runs API intermittently omits requested variables from the
   response entirely -- absent, not null. One such case retried successfully
   3/3 times. Responses are validated for variable presence and retried,
   never silently recorded as a gap.

2. The free tier enforces an HOURLY request-weight limit, and a 400-day x
   7-variable hourly request is heavy: it trips at roughly 105 points. That
   is not an error to retry-with-backoff -- the script sleeps until the hour
   rolls over and resumes.

Each point is written to its own parquet part as soon as it lands, so an
interruption never loses completed work. Rerun to resume.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import os
import subprocess
import sys
import time

import pandas as pd
import requests

from config import (ANALYSIS_END, ANALYSIS_START, ARCHIVE_URL, FORECAST_MODEL,
                    IMD_DAY_START_UTC_HOUR, INTERIM, LEADS,
                    PREVIOUS_RUNS_URL, USER_AGENT)

CHUNK_DAYS = 400
MAX_ATTEMPTS = 5
BACKOFF = [3, 10, 30, 60, 120]
PAUSE = 0.4
RATE_LIMIT_MARKERS = ("limit exceeded", "minutely", "hourly", "daily api")


def _pid_alive(pid: int) -> bool:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | "
             f"Measure-Object | Select-Object -ExpandProperty Count"],
            capture_output=True, text=True, timeout=30).stdout.strip()
        return out.isdigit() and int(out) > 0
    except Exception:
        return False           # cannot tell -> assume stale, do not deadlock


@contextlib.contextmanager
def single_instance(source: str):
    """Refuse to start if another fetch for this source is already running.

    Orphaned fetchers survived a session teardown once: killing them only made
    the surviving shell loops respawn new ones, and eight orchestrators ended
    up racing against the same point list, blowing the daily quota. One holder
    per source, always.

    Acquisition is O_CREAT|O_EXCL so it is atomic -- a check-then-write lock
    loses the race when several fetchers start in the same second, which is
    exactly how the pile-up happened.
    """
    lock = INTERIM / f".{source}_fetch.lock"
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                pid = int(lock.read_text().strip())
            except (ValueError, OSError):
                pid = -1
            if pid > 0 and _pid_alive(pid):
                sys.exit(f"another {source} fetch is already running "
                         f"(pid {pid}); refusing to start a second one")
            print(f"clearing stale lock from pid {pid}", flush=True)
            lock.unlink(missing_ok=True)
            continue           # retry the atomic create once
        with os.fdopen(fd, "w") as fh:
            fh.write(str(os.getpid()))
        break
    else:
        sys.exit(f"could not acquire {source} lock")
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def lead_vars(leads=None) -> list[str]:
    return [f"precipitation_previous_day{n}" for n in (leads or LEADS)]


# Non-IFS comparison models, for the self-verification test: if the ERA5 FAR
# gap is an artefact of ECMWF forecasts being scored against ECMWF's own
# reanalysis, it should shrink for models from other centres.
# ICON carries no previous_day7 in the archive (verified null at every date
# tested), so the cross-model comparison runs on leads 1-6.
COMPARISON_MODELS = {"icon": "icon_seamless", "gfs": "gfs_seamless"}
COMPARISON_LEADS = [1, 2, 3, 4, 5, 6]


def build(source: str):
    if source == "forecast":
        return PREVIOUS_RUNS_URL, lead_vars(), {"models": FORECAST_MODEL}
    if source in COMPARISON_MODELS:
        return (PREVIOUS_RUNS_URL, lead_vars(COMPARISON_LEADS),
                {"models": COMPARISON_MODELS[source]})
    return ARCHIVE_URL, ["precipitation"], {"models": "era5"}


# The "hourly" limit is a ROLLING window, not a clock-hour reset: waiting
# until the top of the next hour is not enough if the quota was spent in the
# preceding minutes. Wait in progressively longer blocks and re-probe.
_RATE_WAITS = [300, 600, 900, 1200, 1800]
# The DAILY limit will not clear until the quota day rolls over, so short
# re-probes are pointless. Back off to hour-long blocks.
_DAILY_WAITS = [1800, 3600, 3600, 3600]


def wait_out_rate_limit(n: int, reason: str = "") -> None:
    daily = "daily" in reason.lower()
    waits = _DAILY_WAITS if daily else _RATE_WAITS
    wait = waits[min(n, len(waits) - 1)]
    resume = dt.datetime.now() + dt.timedelta(seconds=wait)
    print(f"    rate limit ({'daily' if daily else 'rolling'}) -- waiting "
          f"{wait//60} min, retry at {resume:%H:%M:%S}", flush=True)
    time.sleep(wait)


def request_chunk(url, params, want) -> dict[str, list]:
    """Return {var: hourly list}. Retries transient faults; waits out rate limits."""
    attempt = 0
    rate_waits = 0
    reason = "unknown"
    while True:
        try:
            r = requests.get(url, params=params, timeout=180,
                             headers={"User-Agent": USER_AGENT})
            js = r.json()
            if js.get("error"):
                reason = str(js.get("reason", ""))[:160]
                if any(m in reason.lower() for m in RATE_LIMIT_MARKERS):
                    # Not a transient fault. Waiting is the only fix, and
                    # burning attempts on it would abandon good points.
                    wait_out_rate_limit(rate_waits, reason)
                    rate_waits += 1
                    continue
            else:
                h = js.get("hourly") or {}
                missing = [v for v in (["time"] + want) if v not in h]
                if missing:
                    reason = f"absent vars: {missing}"
                elif not h["time"]:
                    reason = "empty time axis"
                else:
                    return h
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"[:160]

        attempt += 1
        if attempt >= MAX_ATTEMPTS:
            raise RuntimeError(f"giving up after {MAX_ATTEMPTS}: {reason}")
        # Log it: a silent retry loop looks identical to a hung process.
        print(f"    transient fault (attempt {attempt}/{MAX_ATTEMPTS}), "
              f"sleeping {BACKOFF[attempt-1]}s: {reason}", flush=True)
        time.sleep(BACKOFF[attempt - 1])


def to_imd_days(hourly: dict[str, list], want: list[str]) -> pd.DataFrame:
    """Sum hourly values into IMD rainfall days (0300-0300 UTC, labelled D)."""
    df = pd.DataFrame({v: hourly[v] for v in want})
    df["ts"] = pd.to_datetime(hourly["time"])
    # 03:00 UTC on D-1 .. 02:00 UTC on D  ->  day D
    df["imd_day"] = (df["ts"] - pd.Timedelta(hours=IMD_DAY_START_UTC_HOUR)
                     ).dt.floor("D") + pd.Timedelta(days=1)
    g = df.groupby("imd_day")
    out = g[want].sum(min_count=1)
    # keep only days with all 24 hours present and every variable non-null
    complete = (g.size() == 24) & (g[want].count() == 24).all(axis=1)
    return out[complete.reindex(out.index, fill_value=False)]


def fetch_point(lat, lon, url, want, extra,
                start_date=None, end_date=None) -> pd.DataFrame:
    first = pd.Timestamp(start_date or ANALYSIS_START)
    last = pd.Timestamp(end_date or ANALYSIS_END)
    # one extra day at the front: day D needs hours from 0300 UTC on D-1
    frames = []
    cur = first - pd.Timedelta(days=1)
    while cur <= last:
        stop = min(cur + pd.Timedelta(days=CHUNK_DAYS - 1), last)
        params = {"latitude": lat, "longitude": lon,
                  "hourly": ",".join(want),
                  "start_date": cur.strftime("%Y-%m-%d"),
                  "end_date": stop.strftime("%Y-%m-%d"),
                  "timezone": "UTC", **extra}
        frames.append(to_imd_days(request_chunk(url, params, want), want))
        cur = stop + pd.Timedelta(days=1)
        time.sleep(PAUSE)
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df.loc[(df.index >= first) & (df.index <= last)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True,
                    choices=["forecast", "era5", *COMPARISON_MODELS])
    ap.add_argument("--stride", type=int, default=1,
                    help="fetch every Nth point (quota saver for the "
                         "cross-model comparison; 1 = all points)")
    args = ap.parse_args()
    with single_instance(args.source):
        return _run(args)


def _run(args) -> int:
    url, want, extra = build(args.source)
    parts = INTERIM / f"{args.source}_parts"
    parts.mkdir(parents=True, exist_ok=True)
    pts = pd.read_csv(INTERIM / "points.csv")
    stride = max(1, getattr(args, "stride", 1))
    if stride > 1:
        # Deterministic every-Nth subsample. points.csv is ordered south to
        # north, so this stays spread across all climate regions.
        pts = pts.iloc[::stride].reset_index(drop=True)

    todo = [p for p in pts.itertuples()
            if not (parts / f"{p.point_id}.parquet").exists()]
    print(f"{args.source}: {len(pts)} points in scope (stride={stride}), "
          f"{len(pts) - len(todo)} already on disk, "
          f"{len(todo)} to fetch ({ANALYSIS_START} .. {ANALYSIS_END})",
          flush=True)

    failures = []
    t0 = time.time()
    for i, p in enumerate(todo, 1):
        try:
            df = fetch_point(p.lat, p.lon, url, want, extra)
        except Exception as exc:
            failures.append((p.point_id, str(exc)[:150]))
            print(f"  [{i}/{len(todo)}] {p.point_id} FAILED {exc}", flush=True)
            continue
        df = df.reset_index().rename(columns={"imd_day": "date"})
        df.insert(0, "point_id", p.point_id)
        # write immediately: an interruption must never lose finished work
        df.to_parquet(parts / f"{p.point_id}.parquet", index=False)
        if i % 10 == 0 or i == len(todo):
            el = time.time() - t0
            print(f"  [{i}/{len(todo)}] {p.point_id} rows={len(df)} "
                  f"{el/i:.1f}s/pt eta={(len(todo)-i)*el/i/60:.1f}min",
                  flush=True)

    files = sorted(parts.glob("*.parquet"))
    if files:
        allp = pd.concat([pd.read_parquet(f) for f in files],
                         ignore_index=True)
        out = INTERIM / f"{args.source}_daily.parquet"
        allp.to_parquet(out, index=False)
        print(f"wrote {out}  rows={len(allp)} "
              f"points={allp.point_id.nunique()}", flush=True)

    if failures:
        print(f"FAILED {len(failures)} points -- rerun to retry:", flush=True)
        for pid, msg in failures[:10]:
            print(f"   {pid}: {msg}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
