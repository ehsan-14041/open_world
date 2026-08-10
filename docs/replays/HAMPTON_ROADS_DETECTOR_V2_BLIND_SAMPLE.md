# Detector v2 blind sample — frozen before acquisition

> **Written before any blind day was downloaded**, and after
> [HAMPTON_ROADS_DETECTOR_V2_PROTOCOL.md](HAMPTON_ROADS_DETECTOR_V2_PROTOCOL.md) had frozen
> every detector parameter. These dates are fixed. They are not revised after seeing results.

## 1. Definition

| Field | Value |
|---|---|
| Date range | **2022-07-01 → 2022-12-27** |
| Cadence | **contiguous daily**, no gaps |
| Days | **180** |
| Warmup consumed | 14 (the trailing lookback) |
| Evaluable days | **166** |
| Measurement definition version | 33 CFR **110.168**, eCFR effective **2022-01-01**, artifact SHA-256 `7baa46a782ede9dd7fd760a13e164a05246844158f4004c408f55032546dfce7` — identical to the development set |
| Expected transfer | ~**55 GB** (180 national dailies at ~305 MB) |
| Expected retained | ~350 MB of regional extracts |

Defined in code as `event_sim.detect.sampling.blind_days()`, so the date list is generated
rather than transcribed.

## 2. Why contiguous, and why the development set could never have served

Detector v2 estimates its baseline from the 14 days immediately preceding each day. The
development set is eight *disjoint* 7-day blocks — it cannot supply a 14-day trailing window
anywhere, so the detector cannot be run on it at all, let alone validated.

This is a clean structural reason the split is honest rather than nominal: the development
days informed the *parameters* (drift rate, deviation scale, natural run length), but the
detector's actual behaviour has never been observed on them.

## 3. Why this period — selection rule

Selection used temporal and data-quality criteria only.

1. **Strictly after the development set.** Development ends 2022-05-21. The blind sample
   starts at the next clean quarter boundary, 2022-07-01.
2. **A 41-day buffer** separates them. This is deliberate: the 14-day trailing lookback at
   the first blind day must not be able to reach back into development days, and 41 days
   leaves that impossible with room to spare.
3. **Inside the geometry validity era.** 110.168 is stable from 2020-07-01 through at least
   2024-01-01, so the whole sample sits under one unchanged measurement definition.
4. **Length from warmup arithmetic.** 14 days are consumed before the first defined residual.
   180 days leaves 166 evaluable — enough to resolve a trigger rate to roughly 0.6%, and
   enough for the ≤10% trigger-share criterion (C2) to be a real constraint rather than noise.
5. **Two full quarters** (2022-Q3, 2022-Q4) so any quarterly seasonality is represented rather
   than sampled at one phase.
6. **Cost proportionality.** ~55 GB and roughly 110 minutes at the observed acquisition rate.
   A full year would have been ~110 GB for better trigger-rate resolution; 180 days was judged
   sufficient for the pre-registered criteria. That trade is recorded here rather than left
   implicit.

**No event knowledge entered this choice.** The period was not selected because anything is
believed to have happened in it, and no historical source was consulted before this document
was written.

## 4. Non-overlap proof

| | |
|---|---|
| Development days | 56, spanning 2020-08-15 → 2022-05-21 |
| Blind days | 180, spanning 2022-07-01 → 2022-12-27 |
| Set intersection | **empty** |
| Gap between development end and blind start | **41 days** |
| Earliest day any blind lookback can reach | 2022-06-17 — still 27 days after the last development day |

Asserted by `sampling.splits_are_disjoint()` and by a test, not left to inspection.

## 5. Acquisition record requirements

For every day: filename, date, byte size, SHA-256 of the national archive, national rows
scanned, and regional rows retained — written to `data/external/ais/metadata/`.

Failed days are **not** silently skipped. If acquisition completes fewer than 90% of the 180
protocol days, the stop condition in the protocol applies and no evaluation runs.
