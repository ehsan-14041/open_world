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
| Blocks processed | **1 of 11** |
| Qualifying Event #3 so far | **none** |

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
