# Detector v3 blind trigger windows — frozen before historical research

> **Frozen.** Raw output of the frozen detector on the v3 blind sample, recorded **before any
> historical source was consulted**. No window may later be removed because its cause is
> inconvenient, and none may be added.
>
> Run outcome: **`DETECTOR_V3_VALID`** — all six pre-registered criteria passed. Unlike the v2
> run, these windows come from a detector that passed its own validity gate.

## Parameters in force

```
LOOKBACK_DAYS = 14   RESIDUAL_THRESHOLD = 3.0   PERSISTENCE_DAYS = 4   SCALE_FLOOR = 1.0
V_SHIFT = 3.5   M_ABRUPT = 4.0   S_ABRUPT = 4.5   M_STABLE = 2.0   S_STABLE = 2.5
WINDOW_REGIME_MIN_DAYS = 2
```

Blind sample 2023-02-01 → 2023-07-30. 180 of 180 days acquired, 170 evaluable, zero missing.

## Window 1 — the only trigger

| Field | Value |
|---|---|
| Start | **2023-06-01** |
| Peak | **2023-06-02** |
| End | **2023-06-05** |
| Duration | 5 days |
| Peak occupancy residual | **7.00** |
| Mean residual | 4.07 |
| Occupancy trajectory | **19 → 22 → 21 → 21 → 21** |
| Trailing baseline | 14.5 → 16.0 |
| Triggering metric | `anchorage_occupancy` |
| **Coverage regime** | **`gradual_shift`** |
| **Candidate class** | **`candidate_with_context`** |
| Regime day counts | stable 2, gradual_shift 2, abrupt_measurement_shift 1 |
| Measurement confidence | **moderate** — see below |

### Day-by-day, with four days either side

| Date | Occ | Base | Resid | Vessels | v-res | msg/vessel | m-res | Cells | s-res | Regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2023-05-28 | 16 | 14.0 | 2.00 | 53 | −2.00 | 401 | 4.90 | 158 | −4.13 | abrupt |
| 2023-05-29 | 17 | 14.0 | 3.00 | 62 | 2.20 | 332 | −1.12 | 191 | 0.40 | stable |
| 2023-05-30 | 16 | 14.0 | 1.33 | 59 | 0.83 | 340 | −0.50 | 185 | −0.53 | stable |
| 2023-05-31 | 15 | 14.0 | 0.50 | 57 | 0.17 | 356 | 1.08 | 183 | −0.67 | stable |
| **2023-06-01** | **19** | 14.5 | **3.00** | 59 | 1.00 | 354 | 0.43 | 188 | 0.10 | stable |
| **2023-06-02** | **22** | 15.0 | **7.00** | 65 | 4.00 | 356 | 0.67 | 193 | 1.25 | gradual_shift |
| **2023-06-03** | **21** | 15.5 | **3.67** | 68 | 5.50 | 353 | 0.42 | 196 | 2.00 | gradual_shift |
| **2023-06-04** | **21** | 16.0 | **3.33** | 66 | 3.20 | 367 | 0.99 | 192 | 1.00 | stable |
| **2023-06-05** | **21** | 16.0 | **3.33** | 67 | 2.67 | 356 | 0.09 | 224 | **10.29** | abrupt |
| 2023-06-06 | 20 | 16.0 | 1.60 | 64 | 1.43 | 375 | 1.52 | 191 | 0.67 | stable |
| 2023-06-07 | 23 | 16.5 | 2.17 | 75 | 3.75 | 344 | −0.94 | 246 | **18.83** | abrupt |
| 2023-06-08 | 26 | 18.0 | 3.20 | 74 | 3.12 | 366 | 0.82 | 257 | **16.50** | abrupt |
| 2023-06-09 | 23 | 19.5 | 1.17 | 69 | 1.50 | 359 | 0.25 | 211 | 3.90 | stable |

### What the coverage model says about this window

Read the three diagnostics together, which is the entire point of having three:

- **Vessel count rose** with occupancy — 59 → 68 over the window, residuals up to 5.50.
- **Report density stayed flat** — `m-res` never exceeds 0.99 inside the window. Each vessel
  was reported at the same rate throughout.
- **Spatial footprint stayed flat until the last day**, then jumped: 10.29 on 06-05, and
  18.83 / 16.50 on 06-07 / 06-08.

Days 1–4 are therefore the classifier's `gradual_shift` signature: *more ships, reported the
same way*. That is traffic, not instrumentation — and it is also not, by itself, a
port-specific anomaly. Occupancy rose while regional presence rose alongside it.

From 06-05 onward a genuine observation-regime change begins: the footprint expands from ~190
to ~250 cells while vessel count and report density move far less. Whatever changed in the
observing system, it changed *after* the window's peak, not before it.

**Measurement confidence: moderate.** The window is not measurement-confounded — its first
four days sit in a steady observation environment — but it is not a clean
`candidate_port_anomaly` either, because the occupancy rise co-occurs with a regional traffic
rise the detector cannot attribute to the port.

## Note on V4

The measurement-stability criterion passed at **14.12%** abrupt days against a **15%** limit.
That is a pass, and it is a narrow one. Recorded here rather than in a footnote because it
bears directly on how much weight this window can carry.

## Status

Historical research had **not** begun when this file was written. Any classification appears
below only after this document was committed.
