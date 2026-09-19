# Rainfall forecast skill verification for India

**What this is:** a national, multi-year, lead-time-resolved verification of
rainfall forecasts over India, reproducible end-to-end from free public APIs.

**The question:** when the forecast says rain, how often does it rain?

**Headline metric: false alarm ratio.** A false alarm means a farmer skipped a
spray he should have made. That is the error with a direct cost attached, so it
leads the results rather than being one number among five.

---

## This is skill verification, NOT calibration

The project began as a calibration study — "when a forecast says 60% chance of
rain, does it rain 60% of the time?" **That question cannot be answered from
this data, and the project was renamed rather than fudged.**

Verified against the live API: the Open-Meteo Previous Runs archive contains
**no probability of precipitation at any lead time**. The variable
`precipitation_probability_previous_dayN` is *accepted by the API schema
without error* and returns **100% nulls** — at every location tested, every
date from Feb 2024 to Jun 2026, and under all of `best_match`, `gfs_seamless`,
`gfs_global`, `ecmwf_ifs025` and `icon_seamless`.

This is a trap worth naming: because the request succeeds, a pipeline ingests
a column of nulls and looks like it worked.

`precipitation_probability` exists at day 0 only (from ~May 2024), which is the
latest run — not a forecast at a fixed lead, and therefore useless for
lead-resolved calibration. The Ensemble API cannot backfill one either: its
window is rolling and in practice only the current run forward carries data.

Nothing in this repository should describe its output as calibration. The
metrics here measure **skill** — the correspondence between a deterministic
rain/no-rain forecast and observed rain.

---

## Constraint 1 — the day boundary: 0300–0300 UTC

**Rule: aggregate hourly forecast precipitation over 0300 UTC (D−1) → 0300 UTC
(D) and label it IMD day D.** Not IST calendar day. Not UTC calendar day.

IMD's rainfall day is the 24 h accumulation *ending* 0830 IST (= 0300 UTC), and
the 0.25° gridded product is built on that convention. The IMD `.grd` file
labelled D therefore already *is* day D — no shifting is applied on the truth
side. All the shifting happens on the forecast side, in `fetch_openmeteo.py`.

**Why it was tested rather than assumed.** The documented 24 h window is easy to
find; the *labelling direction* is the part that silently destroys a study, and
getting it backwards shifts everything by a day while still producing
plausible-looking numbers. So the window start was swept from −24 h to +12 h
relative to IST midnight of D, correlating ERA5-accumulated rainfall against the
IMD grid value for D (n = 49 days × 3 sites):

- correlation is **flat-topped from about −16 h to −3 h**
- it **declines monotonically for every positive offset**
- the tempting wrong choice, 0830 IST D → D+1 (offset +8.5 h), is worst
  everywhere:

| Site | Peak r | r at +8.5 h (forward window) |
|---|---|---|
| Kochi | 0.61 | 0.43 |
| Jodhpur | 0.73 | 0.38 |
| Guwahati | 0.52 | **0.03** |

The test cannot pin the exact hour — −15.5 h and −8 h sit within noise at
n = 49, and ERA5 has its own diurnal timing error — so the documented −15.5 h is
used. The empirical result confirms its direction and rules out the failure mode.

**Consequences.** Forecast hours are needed starting 0300 UTC the day *before*
the first verification day. And **Guwahati is the canary**: a wrong boundary
collapses its correlation from 0.52 to 0.03, so if any region's skill scores
look inexplicably terrible, check the boundary before blaming the model.

### Confirmed again at full scale

The sweep above used ERA5 as a stand-in at three sites (n=49). Once real
ECMWF forecasts were in hand, the day-level alignment was re-tested directly
by shifting the IMD labels against the lead-1 forecast across **94,452
point-days** at 102 points:

| Shift | corr | POD | FAR | HSS |
|---|---|---|---|---|
| −2 days | 0.307 | 0.768 | 0.468 | 0.483 |
| −1 day | 0.436 | 0.812 | 0.436 | 0.535 |
| **0 (as implemented)** | **0.588** | **0.861** | **0.402** | **0.591** |
| +1 day | 0.414 | 0.799 | 0.444 | 0.521 |
| +2 days | 0.304 | 0.754 | 0.474 | 0.471 |

A clean unimodal peak at zero with symmetric falloff, best on every metric
simultaneously. The 0300–0300 UTC labelling is correct.

---

## Constraint 2 — the HTTP 000 trap

**Rule: a connection failure is never recorded as missing data.**

The IMD server is slow and throttles hard. A first parallel download pass
reported 33% of dates "missing". Every one of them was throttling.

The distinction is clean and was verified directly:

| Signal | Meaning |
|---|---|
| **HTTP 404** | genuinely absent — confirmed with out-of-archive dates 2030-01-01 and 2010-01-01 |
| **connection error** (curl's `HTTP 000`) | throttling or reset — **always recovered on retry** |

Across 130 dates tested spanning Feb 2024 – Sep 2026, **every** date eventually
returned a valid grid and **not one** returned 404. Completeness is 100%; there
are no gaps in this period.

`fetch_imd.py` encodes this: 404 is recorded as `missing_404` and skipped, while
any connection error, timeout, non-200 or wrong-size response is retried with
backoff and — if it still fails after 10 attempts — logged as
`failed_transient`, which is explicitly *not* a data gap. Rerun the script and
it picks them up.

### Throughput, and why the fetch is not strictly serial

Verification recommended a serial fetch, because a 12-way parallel pass
produced ~35% connection resets. Measured properly during the build, that
recommendation was too conservative:

- the server's own time-to-first-byte is **17–31 s per file** — this is
  server-side generation, not network, and no client tuning reduces it
- a strictly serial fetch therefore needs **~20 h** for 943 days
- shortening the retry backoff (an early version escalated to 240 s, which with
  ~45% of days needing a retry tripled the ETA) helped, but not enough

So the fetch uses a **small pool, default 4 workers** (`--workers 1` is
strictly serial). This is far below the level that caused the reset storm, and
the resets that motivated "serial" in the first place are exactly what the
retry loop already absorbs. The invariant that actually matters — a connection
error is never a data gap — is untouched.

Socket timeout is 75 s: generous against a 31 s TTFB, but short enough that a
hung connection fails fast instead of burning two minutes.

---

## Constraint 3 — this is a grid, not IMD's district table

**IMD's district-wise rainfall tables are not retrievable for past dates.**

- The CRIS portal (`hydro.imd.gov.in/hydrometweb/`) is **dead — 404**.
- `imdgeospatial.imd.gov.in/Rainfall/` responds, but is **today-only**: its
  title is hardcoded to `24HOUR RAINFALL (mm) RECORDED AT 0830 IST OF`, with no
  date input and no dated endpoint in the page.

What *is* retrievable, by a plain dated GET, is IMD's gauge-based 0.25° gridded
daily rainfall:

```
https://www.imdpune.gov.in/cmpg/Realtimedata/Rainfall/rain_ind0.25_{yy}_{mm}_{dd}.grd
```

| Property | Value |
|---|---|
| Size | 69,660 bytes = 135 lon × 129 lat × float32 little-endian |
| Extent | 66.5–100.0°E, 6.5–38.5°N at 0.25° |
| Missing | −999 (12,451 cells); 4,964 valid land cells, constant across dates |
| Earliest | 2018-12-09 |

(The `rain.php` POST route returns HTTP 200 with 0 bytes and does not work.)

**State this honestly in the write-up.** These are grid cells, not IMD's
published district figures. Any district-level number derived here is an
*area-average approximation* of IMD's district rainfall, which IMD computes from
station data directly. Do not call the output "IMD district rainfall".

This project sidesteps the issue by verifying at **grid points**, not districts:
a regular 1.5° lattice (every 6th 0.25° cell) over IMD land cells, giving 139
points spanning 9.5–36.5°N and 69.5–96.5°E. A lattice rather than a hand-picked
set of cities — it covers every climate region without the selection bias of
choosing interesting places, and anyone can regenerate the identical list from a
single `.grd` file.

---

## Constraint 4 — ERA5's wet bias is one-directional, and it flatters FAR

**ERA5 is the robustness check, never the primary truth.**

Measured directly at three sites over monsoon 2024, on the same 0830 IST
rainfall day (n = 51 days/site):

| Threshold | IMD wet | ERA5 wet | ERA5-wet / IMD-dry | IMD-wet / ERA5-dry | Ratio |
|---|---|---|---|---|---|
| ≥1.0 mm | 62.7% | 82.4% | **36** | 6 | **1.31×** |
| ≥2.5 mm | 50.3% | 75.2% | **47** | 9 | **1.49×** |

At Kochi and Guwahati, ERA5 calls **100% of monsoon days wet** at ≥1 mm; IMD
says 74.5% and 68.6%.

**Why this matters for precisely this project.** FAR = FP/(TP+FP). A false alarm
is a day the forecast said rain and it did not rain. ERA5's error is
overwhelmingly one-directional — 36 ERA5-wet/IMD-dry against 6 the other way —
so it converts exactly those days into "it rained", turning false alarms into
hits. **Using ERA5 as truth systematically understates FAR**, making the
forecast look kinder to the farmer than it is. That is the one direction of
error a study about wasted sprays cannot tolerate.

This is consistent with the literature: ERA5 overestimates very light rain
(<1.5 mm/h), underestimates heavier rain, caps extremes near ~25 mm/h where
gauges exceed 110 mm/h, and produces more wet days than observations. Over India
it underestimates extremes over the Western Ghats and Northeast.

The analysis therefore runs the full contingency table under *both* truth
sources and reports the gap (`results/far_truth_source_gap.csv`) as a result in
its own right. The gap pre-empts the obvious reviewer question and quantifies
how much a reanalysis-truth study would have flattered the forecast.

One further trap: Open-Meteo's ERA5 snapped Kochi (9.93 N, 76.27 E) to the cell
at **10.0 N, 76.5 E** — roughly 30 km inland toward the Ghats. On an orographic
coast that displacement alone is material. Sample points here are taken *on* the
IMD grid so that forecast, ERA5 and truth refer to the same nominal location.

### Measured at national scale — the gap is enormous

Run over 117,602 point-days (127 of 139 points), the predicted direction was
confirmed and the magnitude is far larger than the three-site pilot suggested:

| Truth | FAR @ lead 1 | FAR @ lead 7 | BIAS @ lead 1 | HSS @ lead 1 |
|---|---|---|---|---|
| **IMD (correct)** | **0.407** | **0.463** | **1.58** | **0.591** |
| ERA5 (wrong) | 0.163 | 0.235 | 1.02 | 0.763 |

**ERA5 as truth makes the false alarm ratio look 2.5× better than it is**, and
it hides the over-forecasting almost completely — BIAS reads 1.02 (apparently
unbiased) against a true 1.58. The gap is −0.20 to −0.24 at every lead and both
thresholds.

**Why it is this bad: the comparison is close to circular.** ERA5 *is* the
ECMWF reanalysis, produced by the same modelling system as the `ecmwf_ifs025`
forecast being verified. Checking an ECMWF forecast against an ECMWF reanalysis
substantially checks the model against itself, so shared biases cancel and the
forecast scores its own homework. This is a stronger objection than ERA5's wet
bias alone, and it applies to *any* study verifying IFS-family forecasts
against ERA5 — not just this one.

Gauge-based IMD is independent of the forecast system. That independence, not
merely accuracy, is the reason it must be the truth source.

---

## Constraint 5 — the model is pinned

**`ecmwf_ifs025`, explicitly. Never `best_match`.**

`best_match` resolved to ICON at all three probe sites, but it is a
per-location, per-time model selector. Across a 31-month window it can switch
underneath the analysis, which would mean "the forecast" being verified is not
one nameable system — and the result would not be reproducible or attributable.

Pinning has a cost, recorded here so it is not rediscovered: **the
`ecmwf_ifs025` previous-runs archive does not reach 1 Feb 2024.** It ramps in
one lead per day:

| First date | Leads complete |
|---|---|
| 2024-02-03 | lead 1 |
| … | one lead per day |
| 2024-02-10 | all leads 1–7 |

Because IMD day D also needs forecast hours from 0300 UTC on D−1, the first
usable verification day is **2024-02-11**. The analysis period is therefore
**2024-02-11 → 2026-08-31**, not 2024-02-01. IMD truth is still fetched from
2024-02-01 (it is cheap, and a longer truth series costs nothing).

A second quirk: the previous-runs API **intermittently omits requested variables
from the response entirely** — absent, not null. One such case retried
successfully 3/3 times. `fetch_openmeteo.py` validates that every requested
variable is present and retries, rather than silently recording a gap.

---

## Operational constraint — Open-Meteo's hourly weight limit

The free tier limits request *weight*, not just request count, and a
400-day × 7-variable hourly request is heavy: the forecast fetch trips the
**hourly** limit at roughly 105 of the 139 points.

```
Hourly API request limit exceeded. Please try again in the next hour.
```

This is not a transient fault and must not be retried with backoff — doing so
burns the attempt budget and abandons points that would have succeeded.
`fetch_openmeteo.py` detects the rate-limit reason string, sleeps until the
hour rolls over, and resumes.

**The two APIs meter separately.** `previous-runs-api.open-meteo.com` and
`archive-api.open-meteo.com` hold independent quotas — verified directly with
the previous-runs API returning "Daily API request limit exceeded" while the
archive API answered normally in the same second. So the forecast and ERA5
fetches can run **concurrently**, and exhausting one does not block the other.
`run_openmeteo.sh` runs them in sequence, which leaves the archive quota idle
while the forecast waits out a daily cap; run the two independently to halve
the wall-clock.

**Never leave orphaned fetchers.** Repeated restarts during rate-limit
debugging left multiple shell loops and fetchers alive simultaneously, all
working the same point list and multiplying quota burn — which is what turned
an hourly cap into a daily one. `pgrep` does not exist in Git Bash on Windows,
so process checks based on it silently report nothing and look clean. Both
`fetch_openmeteo.py` and `run_openmeteo.sh` now hold single-instance locks.
Verify process death with PowerShell `Get-Process`, not `pgrep`.

Related, and the reason the first run lost an hour of work: **write each point
as soon as it lands.** The fetcher saves one parquet part per point under
`data/interim/{source}_parts/` and concatenates at the end, so an interruption
never costs completed work and a rerun resumes exactly where it stopped.

### Run exactly one fetcher — the quota is shared

The fetch is driven by a single Python process, `run_fetches.py`, and this is
deliberate. An earlier shell-loop orchestrator orphaned repeatedly:

- Git Bash spawns a wrapper `bash.exe` per script, and its `$$` is an MSYS pid
  that does **not** appear in the Windows process table — so a pid-based guard
  cannot see its own siblings
- a backgrounded shell survives session teardown with its `while` loop intact,
  so killing the Python children just made the loops respawn new ones
- eight orchestrators ended up fetching the same point list concurrently,
  which is what exhausted the **daily** quota

Two guards now exist. `run_fetches.py` takes an `O_CREAT|O_EXCL` lock — atomic,
because a check-then-write lock loses the race when several fetchers start in
the same second, which is exactly how the pile-up began. And the daily limit is
distinguished from the rolling hourly one: short re-probes are pointless
against a daily cap, so it backs off to hour-long blocks.

If throughput ever looks wrong, count the processes before anything else.

### The two APIs have separate quotas

`previous-runs-api.open-meteo.com` (forecast) and `archive-api.open-meteo.com`
(ERA5) meter **independently**. Verified directly: with previous-runs returning
`Daily API request limit exceeded`, the archive API served ERA5 requests
normally in the same second.

Practical consequence: the forecast and ERA5 fetches do **not** compete, so the
earlier "~2.5 days for both" estimate was pessimistic. ERA5 (one variable, and
far cheaper per point) completes in minutes; only the 7-variable forecast fetch
is genuinely quota-bound. They can safely be run at the same time.

---

## Novelty claim — state it exactly

The defensible claim is: **national, multi-year, lead-time-resolved,
reproducible from a free API.**

"Nobody has published rainfall forecast verification for India" is **not
accurate** and a reviewer will find the counterexamples in one search. Indian
verification using exactly POD / FAR / HSS / CSI already exists:

- **Banka district, Bihar** — 11 blocks, forecast accuracy 0.81–0.87
- **Vridhachalam, Tamil Nadu** — seasonal FAR / CSI / TSS
- **Nalanda, Supaul, East Champaran, Bihar** — IMD-WRF at 3-day lead, FAR < 0.3
  across 90% of 812 panchayats
- **Kerala** — NWP evaluation showing POD / CSI / ETS declining Day 1 → Day 3

All are single-district or single-block, one or two seasons, and mostly evaluate
IMD's own WRF or district forecasts. Cite them as prior work; claim the gap they
leave, not their absence.

---

## Pipeline

| Step | Script | Output |
|---|---|---|
| 1 | `fetch_imd.py` | `data/imd_grd/*.grd` — serial, retry, 404≠000 |
| 2 | `sample_points.py` | `data/interim/points.csv` — 139-point lattice |
| 3 | `fetch_openmeteo.py --source forecast` | `forecast_daily.parquet` — ECMWF IFS025, leads 1–7 |
| 4 | `fetch_openmeteo.py --source era5` | `era5_daily.parquet` — robustness truth |
| 5 | `extract_imd.py` | `imd_daily.parquet` — grid sampled at the 139 points |
| 6 | `analyze.py` | `results/metrics.csv`, `results/far_truth_source_gap.csv` |
| 7 | `persistence.py` | `results/persistence_benchmark.csv` — the naive benchmark; no new data, reads step 5 |
| 8 | `hamilljuras.py` | `results/hamilljuras.csv` + three checks — pooled vs stratified scoring |

All fetch steps are resumable: rerun and they skip what is already on disk.

## Metrics

With a = hits, b = false alarms, c = misses, d = correct negatives:

```
POD  = a / (a + c)                  hit rate
FAR  = b / (a + b)                  HEADLINE
CSI  = a / (a + b + c)
BIAS = (a + b) / (a + c)            > 1 means over-forecasting rain
HSS  = 2(ad - bc) / [(a+c)(c+d) + (a+b)(b+d)]
```

Wet-day thresholds: **≥1.0 mm** and **≥2.5 mm**.

Uncertainty is a **cluster bootstrap over 8° spatial blocks** (12 blocks over
the 139 points), 4000 replicates. Two different dependences are in play and
they are easy to state backwards:

- **Temporal, within a location.** Consecutive wet days at one point are
  correlated. The cluster bootstrap **handles this automatically** — a point's
  whole time series travels as one unit and is never broken up. No extra
  machinery is needed.
- **Spatial, between locations.** Rainfall is correlated across neighbouring
  points, and over India the monsoon's seasonal cycle keeps that correlation
  non-zero even at continental range. Measured on the IMD wet/dry series:
  mean r = 0.24 across all pairs, 0.50 for neighbours ~165 km apart, and still
  ~0.11 at 1800–4000 km. **This is the part that needs the block clustering.**
  Resampling individual points treats 139 correlated locations as 139
  independent clusters and understates the variance.

Block size was chosen empirically: interval width grows 1.00× (points) →
1.25× (3°) → 1.68× (5°) → **1.95× (8°)** → 1.87× (12°), so it plateaus at 8°.
Against the old point-level resampling the published FAR intervals are
2.05–2.28× wider, implying roughly **37 effective independent locations**
rather than 139.

An earlier version of this brief and of `analyze.py` had these two
dependences the wrong way round — it claimed the point bootstrap handled the
spatial part and that temporal correlation was unaddressed. Both statements
were inverted, and the intervals published before this correction were about
half their proper width.

## Known data gaps

**Forecast side: 7 of 933 days, 0.75%.** Dropped because the 0300–0300 UTC
window was not fully covered in the `ecmwf_ifs025` previous-runs archive:

- 2025-03-16 (isolated)
- 2026-04-18 → 2026-04-23 (six consecutive days)

These are **identical at all 139 points**, so they are an upstream archive
outage, not point-specific noise or a bug in the aggregation. IMD truth covers
all seven dates at all 139 points, so the loss is one-sided. Both fall outside
the monsoon, which limits the impact on the headline results, but the analysis
is an inner join and simply omits them — it does not interpolate.

**Truth side: none.** 943/943 IMD days downloaded, zero 404s, zero unresolved
transient failures.

## Headline result

Complete run: 139 points, **128,714 point-days**, 2024-02-11 → 2026-08-31,
`ecmwf_ifs025`, IMD gridded truth.

| Lead | POD | **FAR** (95% CI) | CSI | HSS | BIAS |
|---|---|---|---|---|---|
| 1 | 0.853 | **0.423** (0.385–0.477) | 0.525 | 0.566 | 1.48 |
| 4 | 0.814 | **0.444** (0.403–0.495) | 0.494 | 0.529 | 1.46 |
| 7 | 0.812 | **0.479** (0.435–0.537) | 0.465 | 0.487 | 1.56 |

*(wet day ≥1 mm; the ≥2.5 mm table runs ~3 points higher on FAR. Intervals are
the 8° block bootstrap — roughly twice the width of the point-level
resampling used before the correction.)*

**The finding is the frequency bias, and everything else follows from it.**
The model calls rain on 34.9% of days; rain falls on 23.6%. BIAS = **1.48** at
lead 1 and sits at 1.43–1.56 across the whole week, so it is a property of the
model rather than of how far ahead it is reaching — 14,560 more wet days than
happened. Two independent consequences:

1. **The two directions come apart.** PPV 0.577 against NPV 0.947 at lead 1.
   A model that over-calls a minority event is necessarily wrong more often
   when it says rain and right more often when it says dry.
2. **It loses to persistence in the rain direction at lead 1** (see below).

Both were measured separately; neither was assumed from the other.

*Earlier framing, superseded:* the page and this brief previously led with
"roughly two in five rain forecasts are false alarms." That is still true
(FAR 0.423 at lead 1) but it reports one direction of a two-directional
result and does not name the cause. The bias is the cause.

### The persistence benchmark — and the one result that goes against the model

Murphy (1992) requires the reference standard to be the most accurate *naive*
method available. For daily rainfall occurrence at short lead that is
persistence, not climatology. Computed from data already on disk
(`src/persistence.py`), on the matched sample, with a paired 8° block
bootstrap so both systems are scored on the same resampled blocks.

Lead-L persistence = the observation from L days before the target — only
information the decision-maker actually has at issue time.

| ≥1 mm, lead 1 | ECMWF | persistence | difference | paired 95% CI |
|---|---|---|---|---|
| **PPV** | 0.577 | **0.623** | **−0.046** | **(−0.074, −0.016)** |
| NPV | **0.947** | 0.883 | +0.064 | — |
| POD | **0.853** | 0.621 | +0.232 | — |
| HSS | **0.566** | 0.506 | +0.061 | (+0.030, +0.090) |
| BIAS | 1.48 | 1.00 | — | — |

**ECMWF loses the rain direction at lead 1.** The interval excludes zero and
ECMWF was ahead in 8 of 4,000 bootstrap draws. At ≥2.5 mm it is a statistical
tie with persistence nominally ahead (0.562 vs 0.546, CI −0.042 to +0.012).

This is *the same bias showing up a second way*. Persistence has BIAS = 1.00
by construction — it emits the observed wet-day distribution, shifted a day —
so it buys success ratio at the cost of detection (POD 0.621 vs 0.853). ECMWF
wins every other metric at lead 1, and wins PPV too from lead 2 onward, peaking
at +0.054 (≥1 mm) and +0.086 (≥2.5 mm) at lead 4–5.

**The five-day boundary.** Day-1-held persistence — repeating the most recent
observation at every lead, which for L > 1 uses information the
decision-maker does not have — is the *ceiling* on any persistence rule, not a
competitor. At ≥1 mm that ceiling is HSS 0.506. ECMWF is above it through lead
5 (0.516) and below it at leads 6 (0.502) and 7 (0.487): **beyond about five
days its overall skill is no better than knowing yesterday's weather.** At
≥2.5 mm it holds the line to lead 7 (0.461 against a ceiling of 0.460) — a
dead heat, not a win. Stated on the page as its own result.

**Read the lead-time trend from the paired test, not from the table above.**
The block-bootstrap intervals for lead 1 and lead 7 overlap, which does not
settle the comparison, because the two leads are scored on the same points and
days. Bootstrapping the *difference* under the same 8° block clustering gives
FAR(lead 7) − FAR(lead 1) = **+0.056, 95% CI (+0.046, +0.065)** — excludes
zero, so the upward trend is real. Comparisons between adjacent leads are
another matter: lead 3 vs lead 4 (0.440 vs 0.444) was never distinguishable
and still is not.

### Hamill & Juras — how much of the pooled skill is geography?

Hamill, T. M. and J. Juras, 2006: *Measuring forecast skill — is it real skill
or is it the varying climatology?* QJRMS **132**, 2905–2923.
doi:10.1256/qj.06.25

A skill score is referenced to a climatological expectation. Pooling locations
whose climatologies differ makes that reference a mixture no location
experiences, and the score then credits the forecast for telling wet *places*
from dry *places* — which is free. This study pools 139 cells whose wet-day
base rates run **5.9% to 53.6%** (sd 0.10), so the critique lands.

**The demonstration, on this data.** Replace the forecast at each cell with
one statistically independent of the observation there, holding that cell's
real forecast rate and real base rate. Every location then has *exactly zero*
skill. Pool those 139 tables: pooled HSS = **0.052**, which is **9%** of the
0.566 this study reported at lead 1. Computed in closed form (independence
makes the expected table the outer product of its margins), verified against a
400-draw simulation at 0.0519 ± 0.0026 — 0.08 sd apart.

**Pooled against stratified** (stratified = score each cell against its own
table, then average the scores; ≥1 mm):

| Metric | Lead 1 pooled | stratified | gap | paired 95% CI |
|---|---|---|---|---|
| **HSS** | 0.566 | **0.540** | **+0.027** | (+0.011, +0.048) |
| PPV | 0.577 | 0.568 | +0.009 | (−0.001, +0.021) |
| NPV | 0.947 | 0.946 | +0.001 | (−0.001, +0.003) |

The HSS gap widens to +0.033 by lead 7 and excludes zero at every lead and
both thresholds. **PPV and NPV barely move** — they are raw conditional
probabilities with no climatological reference to distort. Pooling makes them
a frequency-weighted composite, which changes the question they answer, not
whether the answer is valid. This vindicates the page's choice to lead with
the two directions rather than a skill score.

Per-cell HSS at lead 1 spans −0.002 to 0.758, median 0.562, IQR 0.155. No
cell had an undefined score for any of the three metrics.

**Two claims were re-checked against the corrected score, and one moved.**

* **The persistence ceiling moved by a day.** Stratification lowers the naive
  benchmark (0.506 → 0.463) more than it lowers ECMWF (0.566 → 0.540),
  because persistence tracks local wet-day frequency closely and so carries
  more of the free geographic signal. The ≥1 mm crossing therefore moves from
  lead 6 (pooled) to **lead 7 (stratified)**: ECMWF stays above the ceiling
  through lead 6. The page now reads this off the stratified score and states
  both. *The pooled comparison understated the model's advantage over
  persistence.*
* **The seasonal HSS inversion survives.** Both seasonal figures are pooled
  and both drop under stratification (non-monsoon 0.524 → 0.458, monsoon
  0.406 → 0.323 at lead 1), but the ranking does not flip: the inversion
  holds at **14 of 14** threshold-and-lead combinations under either
  reference.

**Not yet corrected:** the cost–loss value score uses `E_clim = min(α, s)`
with the *pooled* base rate `s`, so it carries the same exposure. Size
unquantified. Listed as a known gap rather than fixed.

Run by `src/hamilljuras.py` → `results/hamilljuras.csv`,
`hj_persistence_crossing.csv`, `hj_seasonal.csv`, `hj_null_check.json`.

### The ERA5 robustness result

Using ERA5 as truth instead of IMD **understates FAR by 0.21–0.26** — it
roughly halves it, from 0.423 to 0.164 at lead 1:

| Threshold | Lead | FAR (IMD) | FAR (ERA5) | Gap |
|---|---|---|---|---|
| ≥1 mm | 1 | 0.423 | 0.164 | **−0.259** |
| ≥1 mm | 7 | 0.479 | 0.240 | **−0.239** |
| ≥2.5 mm | 1 | 0.454 | 0.218 | **−0.235** |
| ≥2.5 mm | 7 | 0.518 | 0.312 | **−0.206** |

BIAS tells the same story: ~1.00–1.10 against ERA5 versus 1.43–1.56 against
IMD. Against ERA5 the forecast looks nearly unbiased and skilful
(HSS 0.755 at lead 1); against gauge-based truth it over-forecasts rain by half
and is far less skilful (HSS 0.566).

### Mechanism: tested, and mostly not self-verification

An earlier version of this brief claimed the gap was driven by
**self-verification** — ERA5 being ECMWF's own IFS reanalysis, so an IFS
forecast scored against it shares systematic error rather than being
independently tested. That claim was reasoning, not measurement, and the
measurement only partly supports it.

Test: verify two non-IFS models (DWD **ICON**, NCEP **GFS**) against both
truths on a matched sample — same 47 points, same days, same leads,
successive inner merges so all three models see identical rows
(n = 43,287 point-days). If shared lineage matters, non-IFS gaps should be
smaller.

FAR gap (ERA5 − IMD), wet day ≥1 mm:

| Lead | ECMWF (IFS) | ICON (DWD) | GFS (NCEP) |
|---|---|---|---|
| 1 | −0.2431 | −0.2157 | −0.2112 |
| 3 | −0.2351 | −0.2076 | −0.2109 |
| 6 | −0.2213 | −0.1988 | −0.2053 |

Paired block bootstrap on the difference, lead 1, ≥1 mm:

- ICON − ECMWF = **+0.0274**, 95% CI (+0.0174, +0.0401)
- GFS − ECMWF = **+0.0319**, 95% CI (+0.0222, +0.0458)

Both exclude zero, at every lead and both thresholds. **So
self-verification is real and statistically significant — but it accounts
for only 7–16% of the gap** (11–13% at lead 1). The other ~85% is present
for models that share nothing with ERA5, i.e. it is ERA5's wet bias, which
flatters every forecast about equally.

**The practical conclusion is unchanged and in fact broader:** do not use a
reanalysis as primary truth for rainfall skill over India — not only when
scoring the reanalysis centre's own model. Expect FAR to come out roughly
half its gauge-verified value whoever produced the forecast. But do not
attribute that to shared lineage; the lineage effect is the small part.

One thing not to overclaim: at lead 1 the three models' FAR-vs-ERA5 values
are almost identical (0.1703 / 0.1704 / 0.1711, spread 0.0007) while their
FAR-vs-IMD values differ by 0.031 — suggesting ERA5 truth erases model
discrimination. That compression does **not** persist: by lead 6 the
ERA5 spread is 0.054 against an IMD spread of 0.062. It is a lead-1
observation only.

## Known limitations

- **Both dependences are now handled, but the block count is small.** Temporal
  correlation within a point is absorbed by the cluster bootstrap (whole series
  move together); spatial correlation between points is absorbed by the 8°
  block clustering. The residual weakness is that 8° over India yields only 12
  blocks, and they are very uneven (sizes 24, 23, 21, 18, 14, 14, 10, 5, 4, 3,
  2, 1). Resampling 12 unequal units makes the interval endpoints themselves
  noisy, and a single-point block contributes almost nothing when drawn. The
  intervals are honest about spatial dependence but should not be read to three
  decimal places.
- **Grid points, not districts** — see Constraint 3.
- **Point-to-grid representativeness**: a 0.25° IMD cell is an interpolated
  gauge product, not a point gauge, and the ECMWF cell is a model average. Both
  smooth convective extremes.
- **One model.** Results describe ECMWF IFS025, not "weather forecasts" in
  general, and not the IMD forecasts farmers actually receive through official
  advisories.
