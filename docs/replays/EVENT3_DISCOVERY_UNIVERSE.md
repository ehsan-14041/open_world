# Event #3 discovery universe and search ordering

> **Written before any discovery day was acquired.** The universe and the processing order are
> pure functions of the calendar, publisher availability, and which days have already been
> spent. No historical knowledge of disruptions entered either.
>
> Implementation: [`event_sim/detect/discovery.py`](../../event_sim/detect/discovery.py).
> Instrument: [HAMPTON_ROADS_DETECTOR_FINAL_FREEZE.md](HAMPTON_ROADS_DETECTOR_FINAL_FREEZE.md),
> semantic hash `49ed3b935527f1fb…`.

## 1. Constraints defining the universe

| Constraint | Effect |
|---|---|
| Hampton Roads only | single region, frozen geometry |
| Geometry must be stable | 33 CFR 110.168 changes between 2020-04-01 and 2020-07-01, then is unchanged through **2026-01-01** (verified by diffing eCFR revisions). Universe starts **2020-07-01**. |
| National AIS availability | 2023 complete; **2024-01-01 → 2024-06-30 listed but every artifact returns 404**; 2024-07-01 → 2024-12-31 present; **no 2025 directory at all**. Universe ends **2024-12-31**. |
| No overlap with v1 development | 56 days excluded |
| No overlap with v2 blind validation | 2022-07-01 → 2022-12-27 excluded |
| No overlap with v3 blind validation | 2023-02-01 → 2023-07-30 excluded |
| No H1 development periods | none of the above were used for H1; H1 was developed against Yantian 2021 and Baltimore 2024 evidence, neither of which is Hampton Roads AIS |

The availability gap was discovered by probing the publisher, not assumed. It is a fact about
the archive and it materially shrinks the universe: the whole of 2024 H1 is unobtainable.

**Eligible days: 1047.**

## 2. Eligible contiguous spans

A span must hold at least 14 warmup days plus 45
discovery days to be processable.

| Span | Days |
|---|---|
| 2020-08-22 → 2020-11-14 | 85 |
| 2020-11-22 → 2021-02-14 | 85 |
| 2021-02-22 → 2021-05-14 | 82 |
| 2021-05-22 → 2021-08-14 | 85 |
| 2021-08-22 → 2021-11-14 | 85 |
| 2021-11-22 → 2022-02-14 | 85 |
| 2022-02-22 → 2022-05-14 | 82 |
| 2023-07-31 → 2023-12-31 | 154 |
| 2024-07-01 → 2024-12-31 | 184 |

The seven 2020–2022 spans are the gaps *between* the v1 development windows, which sampled one
week per quarter. Those weeks are spent; the ~85-day gaps between them are not, and
chronological ordering places them first. They are included because the rule includes them —
not because anything is expected there.

## 3. Block structure

| Parameter | Value |
|---|---|
| `BLOCK_DISCOVERY_DAYS` | 90 |
| `BLOCK_WARMUP_DAYS` | 14 (= the detector lookback) |
| `MIN_DISCOVERY_DAYS` | 45 |
| `MAX_DISCOVERY_BLOCKS` | **8** |

A span shorter than a full block yields one shorter block, provided it clears
`MIN_DISCOVERY_DAYS`. Block length varies only because span length varies; **every block is
processed by the identical frozen procedure**, and the detector is per-day, so its behaviour
does not depend on how many days follow.

### Boundary continuity

Detector v3 carries trailing state, so a block boundary must not reset the baseline and
manufacture a trigger. The rule:

> Every block's first discovery day is preceded by 14 **acquired** days.
> For the first block in a span these are dedicated warmup days, acquired but never treated as
> discovery days. For any later block in the same span they are the previous block's own tail,
> already acquired.

So the trailing window is fully populated at every discovery day, and no discovery day is ever
counted twice.

## 4. Search order — pre-registered

| Block | Warmup | Discovery | Days |
|---|---|---|---|
| **1** | 2020-08-22 → 2020-09-04 | **2020-09-05 → 2020-11-14** | 71 |
| **2** | 2020-11-22 → 2020-12-05 | **2020-12-06 → 2021-02-14** | 71 |
| **3** | 2021-02-22 → 2021-03-07 | **2021-03-08 → 2021-05-14** | 68 |
| **4** | 2021-05-22 → 2021-06-04 | **2021-06-05 → 2021-08-14** | 71 |
| **5** | 2021-08-22 → 2021-09-04 | **2021-09-05 → 2021-11-14** | 71 |
| **6** | 2021-11-22 → 2021-12-05 | **2021-12-06 → 2022-02-14** | 71 |
| **7** | 2022-02-22 → 2022-03-07 | **2022-03-08 → 2022-05-14** | 68 |
| **8** | 2023-07-31 → 2023-08-13 | **2023-08-14 → 2023-11-11** | 90 |

**Total discovery days: 581.**

Strictly chronological, earliest first. The order does not consider — and the module cannot
express — whether a hurricane, closure, strike or famous congestion episode falls in a period.
`discovery.py` contains no event names and no dates other than the availability and geometry
boundaries above.

## 5. Sequential processing

For each block, in order:

1. acquire the daily files (warmup + discovery),
2. verify SHA-256 of every national artifact,
3. reconstruct Hampton Roads observations,
4. run frozen Detector v3 — unchanged, no block-specific thresholds,
5. freeze trigger windows into the discovery ledger and **commit**,
6. classify the coverage regime,
7. only then research triggers against independent sources,
8. apply the frozen Event #3 eligibility contract.

The next block is acquired **only if** nothing qualifies. This is a sequential stopping design,
and it is also the acquisition budget: at roughly 300 MB per day, a full sweep of all
581 discovery days would exceed 200 GB, so stopping early is a practical necessity as well
as a scientific one.

## 6. First-qualified rule

The search ends at the **first chronologically encountered** candidate satisfying the frozen
contract. Not the largest, not the cleanest, not the one with the best-looking trajectory, and
explicitly not the one where a model might perform well — H1 remains unseen throughout.

## 7. Recovery — declared before any discovery

> Recovery is observed when the occupancy residual sits at or below **1.0**
> robust units for **7** consecutive days, all strictly after the trigger
> window ends.

Seven days is longer than the 4-day persistence rule, so a brief dip mid-event cannot be
mistaken for recovery. The reported recovery date is the day the run *completes* — the point at
which recovery has been demonstrated, not the point at which it began. Defined once, applied
identically to every candidate.

### Extension rule

If recovery is not observable before the acquired data ends, extend forward in fixed increments
of **14** days, up to **56** days total. Fixed
in advance so the extension cannot be chosen after seeing the trajectory.

## 8. Exhaustion

If no candidate qualifies after the full pre-registered budget, the result is:

```
NO_QUALIFYING_EVENT_IN_SEARCH_UNIVERSE
```

The universe is **not** expanded post-hoc. At that point Hampton Roads is finished for this
project and the correct move is to return to dataset and port selection — not to build a
Detector v4.

## 10. Amendment — budget raised to the universe exhaustion count

**Amended 2026-08-18, before any discovery detection was run.**

| | |
|---|---|
| Field | `MAX_DISCOVERY_BLOCKS` |
| Old value | **8** (preserved in code as `MAX_DISCOVERY_BLOCKS_ORIGINAL`) |
| New value | **11** |
| Discovery detection outcomes inspected at amendment time | **0** |
| Discovery result artifacts present at amendment time | **none** — no block result file, no ledger, no window document existed |
| Instrument semantic hash | `b79b6909f48d384c…` — **unchanged** |
| Search protocol hash | `11993ce1f548d1b4…` → `8ac1c174bb2839f8…` |
| Blocks unlocked | 3 |
| Additional discovery days | 220 |
| Additional acquisition including warmup | 262 days, ≈ 86 GB |

### Reason

The original cap of 8 was a round bound chosen **before the eligible universe had been
enumerated**. Once enumerated, the universe requires exactly **11** blocks, so the cap
mechanically truncated an already-frozen universe and left 3 blocks — 220 eligible unseen
discovery days — unreachable. That is an arbitrary right-censoring of the search: those days
satisfy every eligibility rule and were excluded only by a number chosen in ignorance of how
many blocks the rules would produce.

Because **no discovery detection result had been observed**, correcting the cap now removes
that censoring while preserving blind chronological selection. Nothing else changed: ordering,
block size, warmup and boundary rules, eligibility, recovery and extension rules, and Detector
v3 itself are all untouched.

The new value is not a preference for 11; it is the computed exhaustion count. Had the universe
required a different number, that number would have been used.

### Consequence for the terminal negative outcome

The stopping rule is no longer "search up to a budget". It is:

> Search the entire pre-registered eligible Hampton Roads universe chronologically, stopping
> early only when the first qualifying Event #3 is found.

So `NO_QUALIFYING_EVENT_IN_SEARCH_UNIVERSE` becomes a strictly stronger claim: it can only be
returned once the **whole frozen universe has actually been processed**, not merely once the
first eight blocks have been.

### Full block list after amendment

| Block | Discovery | Days | |
|---|---|---|---|
| 1 | 2020-09-05 → 2020-11-14 | 71 | |
| 2 | 2020-12-06 → 2021-02-14 | 71 | |
| 3 | 2021-03-08 → 2021-05-14 | 68 | |
| 4 | 2021-06-05 → 2021-08-14 | 71 | |
| 5 | 2021-09-05 → 2021-11-14 | 71 | |
| 6 | 2021-12-06 → 2022-02-14 | 71 | |
| 7 | 2022-03-08 → 2022-05-14 | 68 | |
| 8 | 2023-08-14 → 2023-11-11 | 90 | |
| 9 | 2023-11-12 → 2023-12-31 | 50 | unlocked by amendment |
| 10 | 2024-07-15 → 2024-10-12 | 90 | unlocked by amendment |
| 11 | 2024-10-13 → 2024-12-31 | 80 | unlocked by amendment |

**801 discovery days total.** Blocks 9 and 11 are span remainders, admitted by the unchanged
`MIN_DISCOVERY_DAYS` rule. Block 10 opens a new span, so it carries dedicated warmup
(2024-07-01 → 07-14); block 9's and block 11's warmup are the preceding blocks' own tails.

Blocks are still processed strictly in order. Block 10 and 11 are **not** inspected early.

## 9. Valid outcomes

Exactly one of `EVENT3_FROZEN_READY_FOR_HELDOUT`, `NO_QUALIFYING_EVENT_IN_SEARCH_UNIVERSE`,
`EVENT3_DRIVER_GAP`, `MEASUREMENT_INTEGRITY_FAILURE`. No softer success category exists.
