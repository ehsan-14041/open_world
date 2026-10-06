# Detector v2 blind trigger windows — frozen before historical research

> **Frozen.** These windows are the raw output of the frozen detector on the blind sample.
> They are recorded here **before any historical source was consulted**. No window may be
> removed later because its cause turns out to be inconvenient, and none may be added.
>
> The run they came from **failed** its pre-registered validity gate — outcome
> `DETECTOR_V2_COVERAGE_CONFOUNDED`, see
> [HAMPTON_ROADS_DETECTOR_V2_RESULTS.md](HAMPTON_ROADS_DETECTOR_V2_RESULTS.md). These windows
> therefore **cannot nominate Event #3**. They are recorded as evidence about the detector,
> not about the port.

## Detection parameters in force

```
LOOKBACK_DAYS = 14   RESIDUAL_THRESHOLD = 3.0   PERSISTENCE_DAYS = 4
SCALE_FLOOR = 1.0    MIN_LOOKBACK_PRESENT = 10  COVERAGE_GUARD_RESIDUAL = 3.0
```

Blind sample 2022-07-01 → 2022-12-27, 180 days acquired of 180, 170 evaluable after warmup,
zero missing.

## Window 1

| Field | Value |
|---|---|
| Start | **2022-10-24** |
| Peak | **2022-10-27** |
| End | **2022-10-27** |
| Duration | 4 days |
| Peak residual | **7.0** |
| Mean residual | 4.75 |
| Peak occupancy | 17 |
| Trailing baseline at peak | 10.0 |
| Triggering metric | `anchorage_occupancy` |
| Coverage-flagged days | 1 of 4 |
| Coverage-confounded | **No** |

Day by day, with the three days either side for context:

| Date | Occupancy | Baseline | Residual | Coverage residual | Flag |
|---|---|---|---|---|---|
| 2022-10-21 | 7 | 11.5 | −3.00 | 0.00 | |
| 2022-10-22 | 9 | 10.5 | −1.00 | 1.00 | |
| 2022-10-23 | 10 | 10.0 | 0.00 | −3.00 | |
| **2022-10-24** | **13** | 10.0 | **3.00** | −1.40 | |
| **2022-10-25** | **14** | 10.0 | **4.00** | 1.33 | |
| **2022-10-26** | **15** | 10.0 | **5.00** | 2.60 | |
| **2022-10-27** | **17** | 10.0 | **7.00** | 3.00 | flagged |
| 2022-10-28 | 14 | 10.0 | 2.67 | 1.67 | |
| 2022-10-29 | 15 | 10.0 | 3.33 | 0.29 | |
| 2022-10-30 | 9 | 10.0 | −0.50 | 0.86 | |

Shape: monotonic accumulation against a flat baseline, then decay. Elevation persists two
days past the formal window (10-28, 10-29 at residual 2.67 and 3.33) before returning to
baseline on 10-30 — the run broke only because 10-28 fell fractionally under threshold.

## Window 2

| Field | Value |
|---|---|
| Start | **2022-12-11** |
| Peak | **2022-12-11** |
| End | **2022-12-14** |
| Duration | 4 days |
| Peak residual | **4.0** |
| Mean residual | 3.25 |
| Peak occupancy | 13 |
| Trailing baseline at peak | 9.0 |
| Triggering metric | `anchorage_occupancy` |
| Coverage-flagged days | **3 of 4** |
| Coverage-confounded | **Yes** |

| Date | Occupancy | Baseline | Residual | Coverage residual | Flag |
|---|---|---|---|---|---|
| 2022-12-08 | 13 | 8.0 | 5.00 | 2.27 | |
| 2022-12-09 | 12 | 8.5 | 2.33 | 0.67 | |
| 2022-12-10 | 10 | 9.0 | 1.00 | 0.88 | |
| **2022-12-11** | **13** | 9.0 | **4.00** | 1.71 | |
| **2022-12-12** | **12** | 9.0 | **3.00** | 3.20 | flagged |
| **2022-12-13** | **14** | 9.5 | **3.00** | 3.00 | flagged |
| **2022-12-14** | **16** | 10.0 | **3.00** | 4.50 | flagged |
| 2022-12-15 | 15 | 10.0 | 2.50 | 2.13 | |
| 2022-12-16 | 13 | 11.0 | 1.00 | 0.80 | |
| 2022-12-17 | 16 | 12.0 | 2.00 | 1.90 | |

Shape: occupancy rises together with regional vessel presence. The coverage residual reaches
4.5 — larger than the occupancy residual itself on the same day. On the pre-registered rule
this is a `measurement_anomaly` signature, not a port-specific one.

## Coverage-flagged days across the whole blind sample

20 of 170 evaluable days (11.8%):

```
2022-07-20, 2022-07-28, 2022-07-29, 2022-08-18, 2022-08-19, 2022-08-20, 2022-08-21,
2022-08-25, 2022-08-27, 2022-09-18, 2022-09-20, 2022-09-21, 2022-09-22, 2022-10-27,
2022-11-30, 2022-12-01, 2022-12-03, 2022-12-12, 2022-12-13, 2022-12-14
```

## Status

Historical research had **not** begun when this file was written. Classifications are
appended below only after this document was committed.

---

## Appended after freeze — classifications

Added after the above was committed as `9657261`. The detection facts above are unchanged.

Independent source: **NOAA NCEI daily summaries, station USW00013737** (Norfolk International
Airport), 2022-10-18 → 2022-12-20. Non-AIS and machine-readable.

| Window | Classification | Basis |
|---|---|---|
| 2022-10-24..27 | **`unknown`** | No exogenous driver independently supported. Max gust 12.5 m/s, below the period p90 of 14.3; no precipitation. No Coast Guard port condition, channel closure, terminal shutdown, labour action or berth outage found. |
| 2022-12-11..14 | **`measurement_artifact`** | 3 of 4 days coverage-flagged; on 12-14 the coverage residual (4.50) exceeds the occupancy residual (3.00). Regional vessel presence rose with occupancy. |

Neither window is weather-driven, and the converse check holds: the three windiest days in the
context period — 2022-11-12 (18.3 m/s), 2022-11-11 (17.0), 2022-10-23 (16.5) — produced no
trigger.

Recorded as a hypothesis and **not** a finding: 2022-10-23, immediately before window 1, was
the third windiest day in the period, and occupancy then rose monotonically over four days.
One day, one station, no documented restriction, noticed after the fact, in a run that failed
validation. It is not a driver.

**No window qualifies as an Event #3 candidate.**
