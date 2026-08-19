# Event #3 discovery ledger — append-only

> Every processed block is recorded here, with or without triggers. Entries are appended as
> each block is run and **committed before any historical source is consulted for that block**.
> Nothing is removed or revised once written.
>
> Instrument: Detector v3, instrument semantic hash
> `b79b6909f48d384c661818eb1e390e1cabc41704798014fb17a8789b1c5ef472` — unchanged throughout.
> Search protocol and ordering: [EVENT3_DISCOVERY_UNIVERSE.md](EVENT3_DISCOVERY_UNIVERSE.md).

## Search state

| | |
|---|---|
| Universe | 1,047 eligible days, 11 blocks, 801 discovery days |
| Ordering | strictly chronological, earliest first |
| Stopping rule | first chronologically encountered candidate passing the frozen contract |
| Blocks processed | **2 of 11** |
| Triggers frozen so far | **1** (block 2) |
| Qualifying Event #3 so far | **none yet — block 2 trigger not researched at time of writing** |

---

## Block 1 — 2020-09-05 → 2020-11-14

| | |
|---|---|
| Span | 2020-08-22 → 2020-11-14 |
| Warmup | 2020-08-22 → 2020-09-04 (acquired, never treated as discovery days) |
| Discovery days | 71 |
| Days acquired | **85 / 85** |
| Evaluable discovery days | 71 |
| Artifact set SHA-256 | `a7c723d1289b98cc24084fe848e7bb30…` (over the per-day national archive hashes) |

### Acquisition note

Six days — 2020-11-06, 11-07, 11-09, 11-10, 11-11, 11-12 — initially failed with `BadZipFile`:
truncated transfers, not missing artifacts. All six were confirmed present at source (HTTP 200,
223–258 MB) and were re-acquired cleanly at lower concurrency. The first pass stood at 79/85
(92.9%), above the 90% tolerance, so the block would have been *permitted* to proceed
incomplete. It was completed instead.

### Observations

| Series | median | mean | sd | min | max |
|---|---|---|---|---|---|
| `anchorage_occupancy` | 6.0 | 5.59 | 2.13 | 1 | 12 |
| standardised residual | 0.0 | — | 1.84 | −3.0 | **6.0** |

| | |
|---|---|
| Threshold | 3.0 |
| Max observed residual | **6.0** — reachable |
| Days at or above threshold | 5 (7.04%) |
| Persistent windows (≥ 4 consecutive days) | **0** |

### Coverage regimes

| Regime | Days | Share of evaluable |
|---|---|---|
| `stable` | 51 | 71.8% |
| `abrupt_measurement_shift` | 15 | **21.1%** |
| `gradual_shift` | 3 | 4.2% |
| `uncertain` | 2 | 2.8% |

**Recorded as measurement context, not as a gate.** The abrupt-shift rate of 21.1% is higher
than the 14.1% seen across the v3 validation period, and higher than the 15% ceiling that
Detector v3's *validation* criterion V4 used. That criterion was pre-registered as a test of
the detector on its blind sample, not as a per-block discovery gate, and no per-block
measurement gate was pre-registered. Inventing one now would be a post-hoc rule change, so it
is not applied.

The fact is logged because it matters for interpretation: the 2020 observation environment is
noticeably less settled than the 2022–2023 environment the classifier's thresholds were drawn
from. Block 1 produced no triggers, so nothing here is affected — but if a later block in this
era produces one, its measurement confidence must be read against this.

### Triggers

**None.** No run of 4 or more consecutive days at or above residual 3.0 occurred in the 71
discovery days.

### Consequence

No candidate. No historical research performed for this block — there is nothing to research.
Proceeding to block 2 under the sequential rule.

---

## Block 2 — 2020-12-06 → 2021-02-14

| | |
|---|---|
| Span | 2020-11-22 → 2021-02-14 |
| Warmup | 2020-11-22 → 2020-12-05 (acquired, never treated as discovery days) |
| Discovery days | 71 |
| Days acquired | **85 / 85** — zero failures |
| Evaluable discovery days | 71 |
| Artifact set SHA-256 | `0a2c0dd50298bd850c141e77559f1355…` |

### Observations

| Series | median | mean | sd | min | max |
|---|---|---|---|---|---|
| `anchorage_occupancy` | 8.0 | 7.24 | 2.54 | 1 | 14 |
| standardised residual | 0.5 | — | 1.80 | −4.0 | **6.0** |

Threshold reachable: max residual 6.0, 6 days at or above 3.0 (8.45%).

### Coverage regimes

| Regime | Days | Share |
|---|---|---|
| `stable` | 58 | 81.7% |
| `abrupt_measurement_shift` | 8 | 11.3% |
| `gradual_shift` | 4 | 5.6% |
| `uncertain` | 1 | 1.4% |

Notably steadier than block 1 (21.1% abrupt) and comparable to the v3 validation period.

### TRIGGER 1 — 2020-12-08 → 2020-12-11

| Field | Value |
|---|---|
| Start | **2020-12-08** |
| Peak | **2020-12-11** |
| End | **2020-12-11** |
| Duration | 4 days (the minimum persistence) |
| Occupancy trajectory | **6 → 6 → 7 → 8** |
| Residual trajectory | **3.0 → 3.0 → 3.5 → 4.0** |
| Mean residual | 3.375 |
| Trailing baseline | 3.0 → 4.0 |
| **Coverage regime** | **`stable`** (4 of 4 days) |
| **Candidate class** | **`candidate_port_anomaly`** |
| Measurement confidence | **high** — no coverage-flagged day inside the window |
| Recovery observed | **yes**, run completed **2021-01-20** |

Day by day, with context either side:

| Date | Occ | Base | Resid | Vessels | v-res | msg/vessel | m-res | Cells | s-res | Regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2020-12-05 | 3 | 3.0 | 0.00 | 31 | −0.33 | 313 | 2.19 | 130 | −0.50 | stable |
| 2020-12-06 | 5 | 3.0 | 2.00 | 38 | 2.40 | 305 | 1.34 | 165 | 3.81 | stable |
| 2020-12-07 | 5 | 3.0 | 2.00 | 31 | −0.50 | 347 | 3.57 | 151 | 1.65 | stable |
| **2020-12-08** | **6** | 3.0 | **3.00** | 38 | 1.83 | 356 | 3.61 | 165 | 2.86 | stable |
| **2020-12-09** | **6** | 3.0 | **3.00** | 37 | 1.00 | 338 | 2.46 | 156 | 2.00 | stable |
| **2020-12-10** | **7** | 3.5 | **3.50** | 39 | 1.83 | 349 | 2.75 | 157 | 1.50 | stable |
| **2020-12-11** | **8** | 4.0 | **4.00** | 40 | 1.57 | 336 | 1.32 | 160 | 1.26 | stable |
| 2020-12-12 | 5 | 4.5 | 0.33 | 39 | 1.17 | 361 | 1.49 | 179 | 2.62 | stable |
| 2020-12-13 | 3 | 5.0 | −2.00 | 40 | 1.40 | 298 | −0.41 | 135 | −1.25 | stable |

### Reading, before any external source was consulted

The shape is a clean monotonic accumulation on a flat baseline of 3, peaking at 8, then an
immediate drop to 5 and 3. The coverage diagnostics stay quiet throughout: vessel-count
residual never exceeds 1.83, and while report density reaches 3.61 on the first day it stays
below the 4.0 abrupt threshold and falls steadily across the window. This is the first window
in the entire project to classify as `candidate_port_anomaly` rather than
`candidate_with_context` or `measurement_artifact`.

Two cautions recorded now, so they cannot be softened later:

- **The absolute magnitude is small.** Occupancy moves from a baseline of 3 to a peak of 8 —
  five vessels. The residual is large only because the trailing MAD is at its 1.0 floor.
- **The duration is exactly the 4-day minimum**, and occupancy falls back to 5 the very next
  day. Recovery nonetheless took until 2021-01-20 to complete a 7-day in-band run, because the
  series makes further excursions to residual 3 and 6 in between.

### Status at freeze time

Historical research had **not** begun when this entry was written. Whether any exogenous driver
exists is unknown, and the trigger is not yet a candidate for anything.

---

### Appended after freeze — classification

Added after the above was committed as `17a5b47`. The detection facts are unchanged.

**Independent, non-AIS source:** NOAA NCEI daily summaries, station USW00013737 (Norfolk
International Airport), 2020-11-15 → 2021-01-05.

| | Window 2020-12-08..11 | Context period |
|---|---|---|
| Max gust | **14.3 m/s** | p90 17.4, max 23.7 |
| Precipitation | 0.3 mm across all four days | up to 24.6 mm/day |
| Snow | 0.0 mm | — |

**Not weather-driven**, and the converse check holds: the windiest days in the context period —
2020-12-24 (23.7 m/s), 12-14 (21.9), 11-30 (20.1), 12-05 (17.9) — produced **no trigger**. The
wettest days (12-16 at 24.6 mm, 12-14 at 23.1 mm) likewise produced none.

Searches of Coast Guard, Port of Virginia, Army Corps and maritime trade press found no channel
closure, port condition, terminal shutdown, berth or crane outage, infrastructure failure or
labour action in the window.

**Classification: `unknown`.**

### Event #3 eligibility

| # | Requirement | Status |
|---|---|---|
| 1 | Occupancy anomaly independently detected | **met** |
| 2 | Measurement regime interpretable across the window | **met** — 4 of 4 days `stable` |
| 3 | Baseline → accumulation → peak → recovery | **met** — flat baseline of 3, monotonic rise to 8, recovery completing 2021-01-20 |
| 4 | Exogenous driver independently documented | **NOT MET** |
| 5 | Driver representable by the simulator | n/a |
| 6 | Frozen eligibility contract passes unchanged | n/a |

This is the strongest window the project has produced — the first with a clean measurement
regime *and* an observed recovery — and it still fails, on requirement 4. Occupancy rising is an
outcome, not a driver; the contract does not accept it as one, and the contract is not being
relaxed to accommodate a shape that looks right.

**Not an Event #3 candidate.** The search continues to block 3 under the sequential rule.
