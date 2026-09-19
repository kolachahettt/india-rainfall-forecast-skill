# forecast-trust

Does rainfall forecasting work in India? A national, multi-year,
lead-time-resolved skill verification, reproducible from free public APIs.

**When the forecast says rain, how often does it rain?** Contingency-table
verification of `ecmwf_ifs025` at leads 1–7 days against IMD 0.25° gauge-based
gridded observations, Feb 2024 – Aug 2026, at 139 grid points across India.

**The headline is the false alarm ratio** — a false alarm means a farmer
skipped a spray he should have made.

> This measures forecast **skill**, not calibration. No probability of
> precipitation is archived at any lead time, so the "is 60% really 60%?"
> question cannot be answered from this data. See
> [PROJECT_BRIEF.md](PROJECT_BRIEF.md).

## Read this first

**[PROJECT_BRIEF.md](PROJECT_BRIEF.md)** records every constraint established
during verification, and why each one matters:

1. the 0300–0300 UTC day boundary, and the empirical test behind it
2. the HTTP 000 trap — why a connection error is never a data gap
3. grid cells vs IMD's district tables
4. ERA5's one-directional wet bias, and why it flatters FAR
5. why the model is pinned rather than `best_match`

## Run it

```bash
cd src
python fetch_imd.py                        # hours: serial by necessity, resumable
python sample_points.py                    # 139-point national lattice
python fetch_openmeteo.py --source forecast
python fetch_openmeteo.py --source era5
python extract_imd.py
python analyze.py
python report.py
```

Or drive both Open-Meteo fetches to completion in one go:

```bash
python src/run_fetches.py
```

This is a **single process** holding a single lock. Do not background several
copies: an earlier shell-loop version orphaned across sessions and eight of
them ended up racing the same point list, which exhausted the daily API quota.
Starting a second copy now exits immediately with `another driver fetch is
already running`.

Check progress at any time, including mid-fetch:

```bash
python src/status.py
```

Every fetch step is resumable — rerun and it skips what is already on disk.
`fetch_imd.py` exits non-zero if any date still needs retrying; just run it
again. The Open-Meteo fetch writes one parquet part per point, so an
interruption never loses completed work.

**Budget the time.** IMD takes ~3 h at 4 workers. The Open-Meteo side is
limited by the free tier's fractional call accounting (14 days × 14 variables
= 1.0 call): the full 139-point forecast + ERA5 fetch costs roughly 24,000
calls against a 10,000/day ceiling, so expect **~2.5 days** of unattended
grinding. `analyze.py` runs on whatever is present and will skip the ERA5 arm
if it is not there yet — but partial point sets are **not** nationally
representative, because the lattice fills from south to north.

## Output

| File | Contents |
|---|---|
| `results/RESULTS.md` | tables and figures |
| `results/metrics.csv` | POD, FAR, CSI, HSS, BIAS per truth × threshold × lead, with bootstrap CIs |
| `results/far_truth_source_gap.csv` | how much using ERA5 as truth moves FAR |

## Requirements

Python 3.11+ with `numpy pandas pyarrow requests matplotlib`.

Data: Open-Meteo (CC BY 4.0) and IMD Pune. Cite both.
