# Detector v3 blind sample — frozen before acquisition

> **Written and committed before any v3 blind day was downloaded**, and after the v3 protocol
> had frozen every parameter. These dates are fixed and are not revised after seeing results.

## 1. Definition

| Field | Value |
|---|---|
| Date range | **2023-02-01 → 2023-07-30** |
| Cadence | **contiguous daily**, no gaps |
| Days | **180** |
| Warmup consumed | 14 (the trailing lookback, for occupancy and all three coverage diagnostics) |
| Evaluable days | **166** |
| Measurement definition | 33 CFR **110.168**, eCFR effective **2022-01-01**, artifact SHA-256 `7baa46a782ede9dd7fd760a13e164a05246844158f4004c408f55032546dfce7` — identical to v1 and v2 |
| Expected transfer | ~55–65 GB |

Defined in code as `event_sim.detect.sampling.v3_blind_days()`, so the list is generated rather
than transcribed.

## 2. Selection rule — chronology and data quality only

1. **After every spent dataset.** The v1 development windows end 2022-05-21; the v2 blind
   period ends 2022-12-27.
2. **First month boundary leaving a buffer of more than twice the lookback.** 2023-02-01 sits
   **36 days** after the v2 period ends, against a 14-day lookback, so no v3 trailing window
   can reach into data whose validation role is finished.
3. **Inside the geometry validity era.** 110.168 is stable from 2020-07-01 through at least
   2024-01-01, verified by diffing eCFR revisions. The whole sample sits under one unchanged
   measurement definition.
4. **Same length as v2** (180 days), for comparability of the two validation exercises, and
   long enough to expose the coverage classifier to more than one regime.
5. **Two-plus quarters** (2023-Q1 tail, Q2, Q3 start) so seasonality is not sampled at a single
   phase.
6. **Cost.** ~55–65 GB, roughly two hours at the observed acquisition rate — the same order as
   the v2 sample, which was affordable.

**No event knowledge entered this choice.** No historical source was consulted about this
period before this document was written, and none will be until trigger windows are frozen.
Known disruptions, weather, strikes, congestion history and expected detector behaviour were
all excluded from the selection.

## 3. Non-overlap proof

| | |
|---|---|
| v1 development days | 56, within 2020-08-15 → 2022-05-21 |
| v2 blind days | 180, 2022-07-01 → 2022-12-27 |
| v3 blind days | 180, 2023-02-01 → 2023-07-30 |
| v3 ∩ v1 | **empty** |
| v3 ∩ v2 | **empty** |
| Buffer after v2 | **36 days** (> 2 × 14-day lookback) |
| Earliest day any v3 lookback can reach | 2023-01-18 — still 22 days after the v2 period ends |

Asserted by `sampling.v3_splits_are_disjoint()` and by tests, not left to inspection.

## 4. Acquisition record

For every day: date, source URL, byte size, SHA-256 of the national archive, national rows
scanned, regional rows retained, distinct vessels, and regional AIS message count — written to
`data/external/ais/metadata/`.

**Zero silent omissions.** Failed days are reported. If fewer than 90% of the 180 days acquire,
the protocol stop condition applies and no evaluation runs.

## 5. Single execution

Detector v3 runs **once** against this sample. No partial inspection followed by rule changes,
no coverage-threshold adjustment, no regime redefinition, no occupancy-parameter change. If it
fails, the sample is spent and any Detector v4 needs another fresh validation period — or, if
the failure is `MEASUREMENT_UNSTABLE` or `TOO_MANY_UNCERTAIN_DAYS`, the recommendation becomes
`STOP_HAMPTON_ROADS`.
