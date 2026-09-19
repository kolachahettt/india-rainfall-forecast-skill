"""Shared configuration for the India rainfall forecast-skill verification."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IMD_GRD = DATA / "imd_grd"          # raw .grd downloads (one per day)
INTERIM = DATA / "interim"          # per-source daily tables
RESULTS = ROOT / "results"
WEB = ROOT / "web"                  # static site root
WEB_DATA = WEB / "data"             # precomputed JSON payload, no backend
for _d in (DATA, IMD_GRD, INTERIM, RESULTS, WEB, WEB_DATA):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- period
# Truth is cheap, so IMD is fetched from 1 Feb 2024.
START = dt.date(2024, 2, 1)
END = dt.date(2026, 8, 31)          # latest complete month

# Analysis starts later than the IMD fetch. Verified against the live API:
# the ecmwf_ifs025 previous-runs archive ramps in one lead per day --
#   2024-02-03 lead 1 ... 2024-02-10 lead 7
# so 2024-02-10 is the first day complete at all seven leads. IMD day D also
# needs forecast hours from 0300 UTC on D-1, which pushes the first usable
# verification day to 2024-02-11.
ANALYSIS_START = dt.date(2024, 2, 11)
ANALYSIS_END = END

# ---------------------------------------------------------------- IMD grid
# IMD 0.25 deg real-time gauge-based gridded rainfall.
# 135 lon x 129 lat, float32 little-endian, missing = -999.
IMD_URL = ("https://www.imdpune.gov.in/cmpg/Realtimedata/Rainfall/"
           "rain_ind0.25_{yy}_{mm}_{dd}.grd")
IMD_NLON, IMD_NLAT = 135, 129
IMD_LON0, IMD_LAT0, IMD_STEP = 66.5, 6.5, 0.25
IMD_BYTES = IMD_NLON * IMD_NLAT * 4          # 69660 -- the only valid size
IMD_MISSING = -999.0

# ---------------------------------------------------------------- sampling
# National sample: every Nth IMD land cell on a regular lattice.
# 6 * 0.25 deg = 1.5 deg spacing -> ~140 land points spanning all regions.
SAMPLE_STRIDE = 6

# ---------------------------------------------------------------- forecast
# Pinned model. NOT best_match: that is a per-location, per-time selector
# and would mean "the forecast" is not one nameable system across 31 months.
FORECAST_MODEL = "ecmwf_ifs025"
LEADS = [1, 2, 3, 4, 5, 6, 7]
PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# ---------------------------------------------------------------- day window
# IMD rainfall day D = 24h ending 0830 IST on D = 0300 UTC (D-1) -> 0300 UTC (D).
# Verified empirically; forward-labelled windows fail badly (see PROJECT_BRIEF.md).
IMD_DAY_START_UTC_HOUR = 3

# ---------------------------------------------------------------- metrics
THRESHOLDS = [1.0, 2.5]             # mm/day, "did it rain" definitions

# Cluster size for the uncertainty bootstrap, in degrees. Points are grouped
# into blocks of this size and whole blocks are resampled, because rainfall is
# spatially correlated and resampling individual points understates the
# variance. 8 degrees is where the measured interval width plateaus: widths
# grow 1.00x (points) -> 1.25x (3 deg) -> 1.68x (5 deg) -> 1.95x (8 deg)
# -> 1.87x (12 deg).
BLOCK_DEG = 8.0

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def daterange(start: dt.date = START, end: dt.date = END):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def imd_path(d: dt.date) -> Path:
    return IMD_GRD / f"rain_ind0.25_{d:%y_%m_%d}.grd"


def imd_url(d: dt.date) -> str:
    return IMD_URL.format(yy=f"{d:%y}", mm=f"{d:%m}", dd=f"{d:%d}")
