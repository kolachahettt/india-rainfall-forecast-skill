"""Download IMD 0.25 deg gridded daily rainfall, one .grd per day.

The IMD server is slow and throttles hard. Verification established:

  * a genuinely absent date returns a clean HTTP 404
  * throttling/reset shows up as a connection error (curl's "HTTP 000")
    and ALWAYS recovers on retry

So a connection error is NEVER recorded as missing data. Only a 404 is.
That distinction is the point of this script and must not be relaxed.

Concurrency note. Verification recommended a serial fetch, because a 12-way
parallel pass produced ~35% connection resets. Measured properly, though, the
server takes 17-31s of server-side time per file, so a strictly serial fetch
needs ~20 hours for 943 days -- and the resets that motivated "serial" are
exactly what the retry loop already handles. This uses a small pool
(default 4) instead: enough to cut the wall-clock to a few hours, far below
the level that caused the reset storm, with every reset still retried rather
than mistaken for absence. Tune with --workers; --workers 1 is strictly serial.

Resumable -- rerun and it skips days already on disk at the right size.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from config import (IMD_BYTES, INTERIM, USER_AGENT, daterange, imd_path,
                    imd_url)

LOG = INTERIM / "imd_fetch_log.jsonl"

MAX_ATTEMPTS = 10
BACKOFF = [2, 3, 5, 8, 12, 20, 30, 45, 60, 90]
TIMEOUT = 75              # server TTFB is 17-31s; a hung socket should fail fast
PAUSE = 0.3               # per-worker gap between requests

_log_lock = threading.Lock()
_local = threading.local()


def session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = _local.s = requests.Session()
    return s


def have(d: dt.date) -> bool:
    p = imd_path(d)
    return p.exists() and p.stat().st_size == IMD_BYTES


def log(rec: dict) -> None:
    with _log_lock, LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def fetch_one(d: dt.date) -> str:
    """Return 'ok', 'missing_404', or 'failed_transient'."""
    url = imd_url(d)
    reason = "unknown"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = session().get(url, timeout=TIMEOUT,
                              headers={"User-Agent": USER_AGENT})
        except requests.exceptions.RequestException as exc:
            # The "HTTP 000" case: connection reset / timeout.
            # NOT missing data. Back off and retry.
            reason = type(exc).__name__
        else:
            if r.status_code == 404:
                # Genuine absence: out-of-archive dates 404 cleanly.
                log({"date": d.isoformat(), "status": "missing_404",
                     "attempt": attempt})
                return "missing_404"
            if r.status_code == 200 and len(r.content) == IMD_BYTES:
                imd_path(d).write_bytes(r.content)
                log({"date": d.isoformat(), "status": "ok",
                     "attempt": attempt, "bytes": len(r.content)})
                return "ok"
            reason = f"http_{r.status_code}_bytes_{len(r.content)}"

        if attempt < MAX_ATTEMPTS:
            time.sleep(BACKOFF[attempt - 1])

    log({"date": d.isoformat(), "status": "failed_transient",
         "attempts": MAX_ATTEMPTS, "last": reason})
    return "failed_transient"


def worker(d: dt.date) -> str:
    out = fetch_one(d)
    time.sleep(PAUSE)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4,
                    help="1 = strictly serial")
    args = ap.parse_args()

    days = list(daterange())
    todo = [d for d in days if not have(d)]
    print(f"IMD fetch: {len(days)} days in period, {len(todo)} still needed, "
          f"{args.workers} worker(s)", flush=True)
    if not todo:
        print("nothing to do", flush=True)
        return 0

    counts = {"ok": 0, "missing_404": 0, "failed_transient": 0}
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(worker, d): d for d in todo}
        for fut in as_completed(futs):
            counts[fut.result()] += 1
            done += 1
            if done % 20 == 0 or done == len(todo):
                el = time.time() - t0
                rate = el / done
                print(f"  [{done}/{len(todo)}] "
                      f"ok={counts['ok']} 404={counts['missing_404']} "
                      f"fail={counts['failed_transient']} "
                      f"{rate:.1f}s/day eta={(len(todo)-done)*rate/3600:.1f}h",
                      flush=True)

    print(f"DONE {counts}", flush=True)
    # Transient failures are recoverable: just rerun this script.
    return 1 if counts["failed_transient"] else 0


if __name__ == "__main__":
    sys.exit(main())
