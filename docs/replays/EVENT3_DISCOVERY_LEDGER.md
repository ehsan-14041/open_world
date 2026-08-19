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
| Blocks processed | **6 of 11** |
| Triggers frozen so far | **4** (blocks 2, 3, 4, 6) |
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

---

## Block 3 — 2021-03-08 → 2021-05-14

| | |
|---|---|
| Span | 2021-02-22 → 2021-05-14 |
| Warmup | 2021-02-22 → 2021-03-07 |
| Discovery days | 68 |
| Days acquired | **82 / 82** — zero failures |
| Evaluable discovery days | 68 |
| Artifact set SHA-256 | `696d7b78c1651b66035652b5bc701e49…` |

### Observations

| Series | median | mean | sd | min | max |
|---|---|---|---|---|---|
| `anchorage_occupancy` | 10.0 | 9.87 | 3.72 | 1 | 18 |
| standardised residual | 0.63 | — | 2.30 | −6.0 | **5.0** |

Threshold reachable: max residual 5.0, 10 days at or above 3.0 (14.71%).

### Coverage regimes

| Regime | Days | Share |
|---|---|---|
| `stable` | 50 | 73.5% |
| `gradual_shift` | 8 | 11.8% |
| `abrupt_measurement_shift` | 6 | 8.8% |
| `uncertain` | 4 | 5.9% |

### TRIGGER 2 — 2021-03-09 → 2021-03-12

| Field | Value |
|---|---|
| Start | **2021-03-09** |
| Peak | **2021-03-10** |
| End | **2021-03-12** |
| Duration | 4 days (the minimum persistence) |
| Occupancy trajectory | **7 → 9 → 8 → 9** |
| Residual trajectory | **3.0 → 5.0 → 4.0 → 3.33** |
| Mean residual | 3.833 |
| Trailing baseline | flat at 4.0 throughout |
| **Coverage regime** | **`stable`** (3 stable, 1 uncertain) |
| **Candidate class** | **`candidate_port_anomaly`** |
| Measurement confidence | **moderate** — one `uncertain` day at the peak |
| Recovery observed | **yes**, run completed **2021-04-09** |

| Date | Occ | Base | Resid | Vessels | v-res | msg/vessel | m-res | Cells | s-res | Regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2021-03-07 | 6 | 4.0 | 2.00 | 34 | −0.50 | 165 | −9.55 | 120 | −2.75 | abrupt |
| 2021-03-08 | 5 | 4.0 | 0.67 | 39 | 3.00 | 295 | −2.28 | 140 | −0.11 | stable |
| **2021-03-09** | **7** | 4.0 | **3.00** | 35 | 0.00 | 387 | 1.76 | 154 | 1.56 | stable |
| **2021-03-10** | **9** | 4.0 | **5.00** | 43 | 5.33 | 326 | −0.90 | 173 | 3.67 | uncertain |
| **2021-03-11** | **8** | 4.0 | **4.00** | 39 | 2.33 | 325 | −0.76 | 158 | 1.89 | stable |
| **2021-03-12** | **9** | 4.0 | **3.33** | 40 | 2.25 | 356 | 1.17 | 152 | 1.14 | stable |
| 2021-03-13 | 8 | 4.0 | 2.00 | 47 | 5.75 | 322 | −0.84 | 177 | 3.55 | uncertain |
| 2021-03-14 | 7 | 4.5 | 1.00 | 49 | 4.50 | 335 | −0.06 | 190 | 4.24 | uncertain |
| 2021-03-15 | 9 | 5.5 | 1.40 | 49 | 4.17 | 368 | 1.72 | 223 | 5.54 | abrupt |

### Reading, before any external source was consulted

Occupancy roughly doubles off a baseline that stays flat at 4.0 for the whole window, peaking
at 9 on the second day. Report density is quiet throughout the window (|m-res| ≤ 1.76), which
is what separates this from a sensor artifact.

The caution here is on the other side from block 2's. On the peak day the vessel-count residual
reaches 5.33 with footprint at 3.67, so that day classifies `uncertain` rather than `stable` —
the count moved and the classifier declined to attribute it. And immediately after the window,
vessel count and footprint climb further (5.75 / 3.55, then 4.50 / 4.24, then an abrupt day),
so the days following the peak sit in a visibly less settled observation environment than the
days before it.

Two windows in two consecutive blocks now share a signature: about four days, occupancy roughly
doubling off a low flat baseline, peak residual 4–5 driven substantially by the MAD floor of
1.0. That is worth noting as a pattern rather than treating each as a singular event.

### Status at freeze time

Historical research had **not** begun when this entry was written.

---

### Appended after freeze - classification

Added after the above was committed as `921beed`.

**Independent, non-AIS source:** NOAA NCEI daily summaries, station USW00013737,
2021-12-15 to 2022-02-10.

| | Window 2022-01-06..10 | Context period |
|---|---|---|
| Max gust | **16.5 m/s** | p90 17.9, max 24.1 |
| Precipitation | 8.1 mm total | - |
| Snow | **0.0 mm** on all five days | up to 9 mm/day later in the month |

**Not weather-driven.** The windiest days - 2022-01-03 (24.1 m/s), 01-16 (21.9), 01-17 (21.5),
01-28 (20.1) - produced **no trigger**.

#### A documented disruption exists in this block, and it is not this window

Trade-press reporting establishes a real Hampton Roads disruption in January 2022: **two
late-January snowstorms** halted operations for roughly 96 hours, leaving about 11 vessels
anchored outside the harbour, growing to 14 within a week.

The snow dates match the independent weather record exactly - the snowiest days in the period
are **2022-01-22 (9 mm), 01-21 (8 mm), 01-29 (8 mm), 01-28 (2 mm)**.

**That is 11-19 days after this trigger window ended.** The frozen trigger runs 01-06 to 01-10.
Under the causal-timing rule, an effect that clearly precedes its supposed cause is rejected, and
no anticipation mechanism is documented or plausible here. The late-January snowstorms do not
explain the early-January window.

**Classification: `unknown`.** Requirement 4 not met. **Not an Event #3 candidate.**

---

## INSTRUMENT FINDING - the frozen detector missed the documented event

This is the most consequential result of the discovery phase, and it is recorded here rather
than in a footnote because it reframes every prior block.

The late-January disruption **is plainly visible** in the reconstructed series:

| Date | Occupancy | Baseline | Residual | Regime |
|---|---|---|---|---|
| 2022-01-20 | 17 | 19.0 | -2.00 | stable |
| 2022-01-21 | 17 | 19.0 | -2.00 | stable |
| 2022-01-22 | 17 | 19.0 | -2.00 | stable |
| **2022-01-23** | **25** | 18.5 | **4.33** | stable |
| **2022-01-24** | **23** | 18.5 | **3.00** | stable |
| **2022-01-25** | **25** | 18.5 | **4.33** | stable |
| 2022-01-26 | 22 | 19.0 | **1.50** | stable |
| 2022-01-27 | 24 | 19.0 | 2.50 | stable |
| 2022-01-28 | 24 | 19.0 | 2.50 | stable |
| 2022-01-29 | 25 | 19.5 | 2.20 | stable |
| 2022-01-30 | 26 | **21.0** | 1.43 | stable |
| 2022-01-31 | 26 | **22.5** | 1.40 | stable |
| 2022-02-01 | 27 | **23.5** | 1.75 | abrupt |

Occupancy climbs from 17 to a sustained 22-27 and stays there for ten days. **The detector
produced no trigger.** Two mechanisms combined:

1. **The run broke one day short.** Residuals reached 3.0+ on 01-23, 01-24 and 01-25, then 01-26
   fell to 1.50. Three consecutive days against a persistence requirement of four.
2. **The trailing baseline absorbed the event.** As the elevation persisted, the 14-day trailing
   median climbed with it: 18.5, 19.0, 19.5, 21.0, 22.5, 23.5. By 01-30, occupancy of 26 - nine
   above the pre-event level - scored a residual of only 1.43.

### What this means, stated plainly

The frozen instrument detects **short, sharp** excursions and is structurally **blind to
sustained** ones. A 14-day trailing median has a 7-day breakdown point; an event that outlasts
that becomes its own baseline. This was noted as a design property when the lookback was chosen -
"an elevated stretch of up to 7 days cannot corrupt its own baseline" - but its converse was
never tested, because no validation period contained a sustained documented event.

This inverts the reading of blocks 2, 3, 4 and 6. The natural interpretation until now was *the
instrument keeps finding real anomalies that no source explains*. The better-supported
interpretation is now:

> The instrument finds a **class** of anomaly - brief, sharp, 4-5 days - that tends not to have
> documented drivers, while being blind to the class that does: slow-building sustained
> congestion.

Four unexplained short triggers and one missed documented sustained event is a coherent picture,
and it is not a flattering one for the search as designed.

### What is NOT being done about it

- **The detector is not changed.** Detector development is finished and the instrument is frozen
  for the whole of discovery. Adjusting persistence, lookback or baseline estimator now - after
  seeing which event it missed - is precisely the post-hoc move the protocol forbids. The
  instrument semantic hash `b79b6909f48d384c...` stands.
- **Late January 2022 does not become Event #3.** It was **not detected**. Promoting it now would
  be exactly the forbidden inversion: *historical event, then inspect AIS around event*. The
  protocol requires detection to precede research, and it did not detect this.
- **The search continues unchanged** to block 7 under the same rules.

Any future detector generation addressing sustained events would need its own development and
validation split, and this finding is the honest evidence for why one might be warranted.

---

### Appended after freeze — classification

Added after the above was committed as `abc20a7`.

**Independent, non-AIS source:** NOAA NCEI daily summaries, station USW00013737,
2021-05-15 → 2021-07-15.

| | Window 2021-06-06..09 | Context period |
|---|---|---|
| Max gust | **12.1 m/s** | p90 13.9, max 19.7 |
| Precipitation | 0.8 mm across all four days | — |

**Not weather-driven.** The windiest days — 2021-07-08 (19.7 m/s), 06-22 (16.5), 07-01 (16.1) —
produced **no trigger**.

No Coast Guard port condition, channel closure, terminal shutdown, berth outage, infrastructure
failure or labour action was found for Hampton Roads in this window.

#### The narrative that exists, and why it is rejected

Trade-press searching does surface a general 2021 context: an unprecedented import surge, vessel
bunching, and the Yantian COVID closure in late May–June 2021 rippling through global schedules.
It would be easy to attach this window to that story. It is rejected on three independent
grounds, any one of which is sufficient:

1. **It is not an exogenous local driver.** A global import surge is arrival-side pressure, not
   a documented local capacity event. The protocol names "more vessels appeared" as explicitly
   *insufficient*, and no Hampton Roads capacity event is documented.
2. **The measurement contradicts it.** This is the decisive point. Across the window the
   regional vessel count barely moves — 50 to 55, with its residual *falling* from 3.40 to 0.29
   — while anchorage occupancy jumps by seven. An arrival surge should raise regional presence.
   It did not. Whatever filled the anchorage, more ships arriving in the region is not it.
3. **It would breach independence from H1 development.** Yantian 2021 is one of the two
   historical events this project used to develop and diagnose H1. An Event #3 whose driver is
   the downstream wake of Yantian is not held out from H1 development, and the eligibility
   contract requires that independence. This disqualifies the narrative even if the first two
   objections were somehow answered.

**Classification: `unknown`.**

### Event #3 eligibility

| # | Requirement | Status |
|---|---|---|
| 1 | Occupancy anomaly independently detected | **met** |
| 2 | Measurement regime interpretable | **met** — 4 of 4 days `stable`, high confidence |
| 3 | Baseline → accumulation → peak → recovery | **met** — flat baseline 9, peak 16, clean recovery by 2021-06-17 |
| 4 | Exogenous driver independently documented | **NOT MET** |
| 5–6 | Representability, contract | n/a |

The best-shaped window in the project, on the cleanest measurement regime, with the clearest
recovery — and it still fails on requirement 4. Three windows have now been rejected for the
same reason. That consistency is itself informative: the instrument keeps finding real
anchorage excursions that no independent source explains.

**Not an Event #3 candidate.** Search continues to block 5.

---

### Appended after freeze — classification

Added after the above was committed as `50efa6e`.

**Independent, non-AIS source:** NOAA NCEI daily summaries, station USW00013737,
2021-02-15 → 2021-04-15.

| | Window 2021-03-09..12 | Context period |
|---|---|---|
| Max gust | **14.3 m/s** | p90 16.1, max 22.8 |
| Precipitation | **0.0 mm** on all four days | — |

**Not weather-driven.** The windiest days in the period — 2021-02-22 (22.8 m/s), 03-19 (21.5),
04-01 / 03-28 / 03-26 (18.3) — produced **no trigger**.

No Coast Guard, Port of Virginia, Army Corps or trade-press record of a channel closure, port
condition, terminal shutdown, berth outage or labour action in the window.

**Corroborating context, found while searching and worth recording because it cuts against a
disruption reading:** the Port of Virginia publicly reported record volumes through this period
with *no congestion* and no adverse service impact, following more than \$800M of capacity
investment completed between July 2019 and November 2020. That is not proof of absence, but it
is independent evidence pointing the same way as the null result.

**Classification: `unknown`.**

### Event #3 eligibility

| # | Requirement | Status |
|---|---|---|
| 1 | Occupancy anomaly independently detected | **met** |
| 2 | Measurement regime interpretable | **partial** — peak day `uncertain`; environment unsettles immediately after |
| 3 | Baseline → accumulation → peak → recovery | **met** — flat baseline of 4, peak 9, recovery completing 2021-04-09 |
| 4 | Exogenous driver independently documented | **NOT MET** |
| 5–6 | Representability, contract | n/a |

**Not an Event #3 candidate.** Search continues to block 4.

---

## Block 4 — 2021-06-05 → 2021-08-14

| | |
|---|---|
| Span | 2021-05-22 → 2021-08-14 |
| Warmup | 2021-05-22 → 2021-06-04 |
| Discovery days | 71 |
| Days acquired | **85 / 85** — zero failures |
| Evaluable discovery days | 71 |
| Artifact set SHA-256 | `1b2ef8c2fb5a8d258fdbf21a19e1ec23…` |

### Observations

| Series | median | mean | sd | min | max |
|---|---|---|---|---|---|
| `anchorage_occupancy` | 8.0 | 7.58 | 2.65 | 3 | 16 |
| standardised residual | 0.0 | — | 2.03 | −3.0 | **7.0** |

Threshold reachable: max residual 7.0, 10 days at or above 3.0 (14.08%).

### Coverage regimes

| Regime | Days | Share |
|---|---|---|
| `stable` | 54 | 76.1% |
| `abrupt_measurement_shift` | 13 | 18.3% |
| `gradual_shift` | 2 | 2.8% |
| `uncertain` | 2 | 2.8% |

### TRIGGER 3 — 2021-06-06 → 2021-06-09

| Field | Value |
|---|---|
| Start | **2021-06-06** |
| Peak | **2021-06-08** |
| End | **2021-06-09** |
| Duration | 4 days |
| Occupancy trajectory | **14 → 14 → 16 → 16** |
| Residual trajectory | **5.0 → 5.0 → 7.0 → 4.33** |
| Mean residual | **5.333** |
| Trailing baseline | flat at 9.0, rising to 9.5 |
| **Coverage regime** | **`stable`** (4 of 4 days) |
| **Candidate class** | **`candidate_port_anomaly`** |
| Measurement confidence | **high** — no coverage-flagged day inside the window |
| Recovery observed | **yes**, run completed **2021-06-17** |

| Date | Occ | Base | Resid | Vessels | v-res | msg/vessel | m-res | Cells | s-res | Regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2021-06-04 | 9 | 9.0 | 0.00 | 49 | 1.50 | 337 | −1.17 | 172 | 1.00 | stable |
| 2021-06-05 | 10 | 9.0 | 1.00 | 54 | 3.00 | 328 | −1.51 | 183 | 2.83 | stable |
| **2021-06-06** | **14** | 9.0 | **5.00** | 55 | 3.40 | 352 | −0.23 | 186 | 3.08 | stable |
| **2021-06-07** | **14** | 9.0 | **5.00** | 53 | 2.40 | 382 | 1.27 | 176 | 0.73 | stable |
| **2021-06-08** | **16** | 9.0 | **7.00** | 54 | 2.00 | 389 | 1.60 | 165 | −0.73 | stable |
| **2021-06-09** | **16** | 9.5 | **4.33** | 50 | 0.29 | 394 | 1.58 | 169 | −0.21 | stable |
| 2021-06-10 | 13 | 10.0 | 1.50 | 51 | 0.80 | 389 | 1.34 | 200 | 5.36 | abrupt |
| 2021-06-11 | 9 | 10.0 | −0.50 | 51 | 0.60 | 388 | 1.32 | 152 | −2.64 | stable |
| 2021-06-12 | 8 | 10.0 | −1.00 | 50 | −0.25 | 360 | 0.06 | 155 | −2.21 | stable |

### Reading, before any external source was consulted

**This is the strongest window the project has produced.** It improves on the block 2 and 3
triggers on every axis that was weak there:

- **Magnitude.** Occupancy runs 14–16 against a baseline flat at 9 — seven vessels above
  baseline, on a base high enough that the MAD floor is not doing the work. Peak residual 7.0.
- **Measurement confidence is high.** All four days `stable`. The vessel count barely moves
  (50–55, residual falling 3.40 → 0.29 across the window) while occupancy jumps by 7. Report
  density stays quiet (|m-res| ≤ 1.60) and footprint likewise. So the anchorage filled up
  *without* more ships appearing in the region and *without* any change in how they were
  reported — which is exactly the signature the coverage model exists to isolate.
- **Recovery is fast and clean**, completing 2021-06-17: occupancy falls 13, 9, 8 and stays
  down.

The one caution: on 2021-06-13/14 the coverage diagnostics collapse (vessel residual −8.75,
density −9.47), an abrupt measurement shift **after** the window and during the recovery tail.
It does not touch the accumulation or the peak, but it means part of the recovery limb sits in
a degraded observation environment.

### Status at freeze time

Historical research had **not** begun when this entry was written.

---

### Appended after freeze - classification

Added after the above was committed as `921beed`.

**Independent, non-AIS source:** NOAA NCEI daily summaries, station USW00013737,
2021-12-15 to 2022-02-10.

| | Window 2022-01-06..10 | Context period |
|---|---|---|
| Max gust | **16.5 m/s** | p90 17.9, max 24.1 |
| Precipitation | 8.1 mm total | - |
| Snow | **0.0 mm** on all five days | up to 9 mm/day later in the month |

**Not weather-driven.** The windiest days - 2022-01-03 (24.1 m/s), 01-16 (21.9), 01-17 (21.5),
01-28 (20.1) - produced **no trigger**.

#### A documented disruption exists in this block, and it is not this window

Trade-press reporting establishes a real Hampton Roads disruption in January 2022: **two
late-January snowstorms** halted operations for roughly 96 hours, leaving about 11 vessels
anchored outside the harbour, growing to 14 within a week.

The snow dates match the independent weather record exactly - the snowiest days in the period
are **2022-01-22 (9 mm), 01-21 (8 mm), 01-29 (8 mm), 01-28 (2 mm)**.

**That is 11-19 days after this trigger window ended.** The frozen trigger runs 01-06 to 01-10.
Under the causal-timing rule, an effect that clearly precedes its supposed cause is rejected, and
no anticipation mechanism is documented or plausible here. The late-January snowstorms do not
explain the early-January window.

**Classification: `unknown`.** Requirement 4 not met. **Not an Event #3 candidate.**

---

## INSTRUMENT FINDING - the frozen detector missed the documented event

This is the most consequential result of the discovery phase, and it is recorded here rather
than in a footnote because it reframes every prior block.

The late-January disruption **is plainly visible** in the reconstructed series:

| Date | Occupancy | Baseline | Residual | Regime |
|---|---|---|---|---|
| 2022-01-20 | 17 | 19.0 | -2.00 | stable |
| 2022-01-21 | 17 | 19.0 | -2.00 | stable |
| 2022-01-22 | 17 | 19.0 | -2.00 | stable |
| **2022-01-23** | **25** | 18.5 | **4.33** | stable |
| **2022-01-24** | **23** | 18.5 | **3.00** | stable |
| **2022-01-25** | **25** | 18.5 | **4.33** | stable |
| 2022-01-26 | 22 | 19.0 | **1.50** | stable |
| 2022-01-27 | 24 | 19.0 | 2.50 | stable |
| 2022-01-28 | 24 | 19.0 | 2.50 | stable |
| 2022-01-29 | 25 | 19.5 | 2.20 | stable |
| 2022-01-30 | 26 | **21.0** | 1.43 | stable |
| 2022-01-31 | 26 | **22.5** | 1.40 | stable |
| 2022-02-01 | 27 | **23.5** | 1.75 | abrupt |

Occupancy climbs from 17 to a sustained 22-27 and stays there for ten days. **The detector
produced no trigger.** Two mechanisms combined:

1. **The run broke one day short.** Residuals reached 3.0+ on 01-23, 01-24 and 01-25, then 01-26
   fell to 1.50. Three consecutive days against a persistence requirement of four.
2. **The trailing baseline absorbed the event.** As the elevation persisted, the 14-day trailing
   median climbed with it: 18.5, 19.0, 19.5, 21.0, 22.5, 23.5. By 01-30, occupancy of 26 - nine
   above the pre-event level - scored a residual of only 1.43.

### What this means, stated plainly

The frozen instrument detects **short, sharp** excursions and is structurally **blind to
sustained** ones. A 14-day trailing median has a 7-day breakdown point; an event that outlasts
that becomes its own baseline. This was noted as a design property when the lookback was chosen -
"an elevated stretch of up to 7 days cannot corrupt its own baseline" - but its converse was
never tested, because no validation period contained a sustained documented event.

This inverts the reading of blocks 2, 3, 4 and 6. The natural interpretation until now was *the
instrument keeps finding real anomalies that no source explains*. The better-supported
interpretation is now:

> The instrument finds a **class** of anomaly - brief, sharp, 4-5 days - that tends not to have
> documented drivers, while being blind to the class that does: slow-building sustained
> congestion.

Four unexplained short triggers and one missed documented sustained event is a coherent picture,
and it is not a flattering one for the search as designed.

### What is NOT being done about it

- **The detector is not changed.** Detector development is finished and the instrument is frozen
  for the whole of discovery. Adjusting persistence, lookback or baseline estimator now - after
  seeing which event it missed - is precisely the post-hoc move the protocol forbids. The
  instrument semantic hash `b79b6909f48d384c...` stands.
- **Late January 2022 does not become Event #3.** It was **not detected**. Promoting it now would
  be exactly the forbidden inversion: *historical event, then inspect AIS around event*. The
  protocol requires detection to precede research, and it did not detect this.
- **The search continues unchanged** to block 7 under the same rules.

Any future detector generation addressing sustained events would need its own development and
validation split, and this finding is the honest evidence for why one might be warranted.

---

### Appended after freeze — classification

Added after the above was committed as `abc20a7`.

**Independent, non-AIS source:** NOAA NCEI daily summaries, station USW00013737,
2021-05-15 → 2021-07-15.

| | Window 2021-06-06..09 | Context period |
|---|---|---|
| Max gust | **12.1 m/s** | p90 13.9, max 19.7 |
| Precipitation | 0.8 mm across all four days | — |

**Not weather-driven.** The windiest days — 2021-07-08 (19.7 m/s), 06-22 (16.5), 07-01 (16.1) —
produced **no trigger**.

No Coast Guard port condition, channel closure, terminal shutdown, berth outage, infrastructure
failure or labour action was found for Hampton Roads in this window.

#### The narrative that exists, and why it is rejected

Trade-press searching does surface a general 2021 context: an unprecedented import surge, vessel
bunching, and the Yantian COVID closure in late May–June 2021 rippling through global schedules.
It would be easy to attach this window to that story. It is rejected on three independent
grounds, any one of which is sufficient:

1. **It is not an exogenous local driver.** A global import surge is arrival-side pressure, not
   a documented local capacity event. The protocol names "more vessels appeared" as explicitly
   *insufficient*, and no Hampton Roads capacity event is documented.
2. **The measurement contradicts it.** This is the decisive point. Across the window the
   regional vessel count barely moves — 50 to 55, with its residual *falling* from 3.40 to 0.29
   — while anchorage occupancy jumps by seven. An arrival surge should raise regional presence.
   It did not. Whatever filled the anchorage, more ships arriving in the region is not it.
3. **It would breach independence from H1 development.** Yantian 2021 is one of the two
   historical events this project used to develop and diagnose H1. An Event #3 whose driver is
   the downstream wake of Yantian is not held out from H1 development, and the eligibility
   contract requires that independence. This disqualifies the narrative even if the first two
   objections were somehow answered.

**Classification: `unknown`.**

### Event #3 eligibility

| # | Requirement | Status |
|---|---|---|
| 1 | Occupancy anomaly independently detected | **met** |
| 2 | Measurement regime interpretable | **met** — 4 of 4 days `stable`, high confidence |
| 3 | Baseline → accumulation → peak → recovery | **met** — flat baseline 9, peak 16, clean recovery by 2021-06-17 |
| 4 | Exogenous driver independently documented | **NOT MET** |
| 5–6 | Representability, contract | n/a |

The best-shaped window in the project, on the cleanest measurement regime, with the clearest
recovery — and it still fails on requirement 4. Three windows have now been rejected for the
same reason. That consistency is itself informative: the instrument keeps finding real
anchorage excursions that no independent source explains.

**Not an Event #3 candidate.** Search continues to block 5.

---

# Search suspended at block 4 — no terminal outcome declared

**Suspended by operator decision after block 4, with 7 of 11 blocks unprocessed.**

## Why no terminal outcome is reported

The four declared outcomes are `EVENT3_FROZEN_READY_FOR_HELDOUT`,
`NO_QUALIFYING_EVENT_IN_SEARCH_UNIVERSE`, `EVENT3_DRIVER_GAP` and
`MEASUREMENT_INTEGRITY_FAILURE`. **None of them applies.**

In particular this is **not** `NO_QUALIFYING_EVENT_IN_SEARCH_UNIVERSE`. Under the amendment
committed at `2b4ca78`, that outcome became a strictly stronger claim: it requires the whole
frozen universe to have been processed. 520 of 801 discovery days — 65% of the universe,
including every block after 2021-08-14 — have never been looked at. Reporting exhaustion here
would assert something untrue.

The correct status is: **search in progress, suspended, resumable.**

## Coverage achieved

| | |
|---|---|
| Blocks processed | 4 of 11 |
| Discovery days covered | **281 of 801 (35.1%)** |
| Days acquired including warmup | 337 |
| National AIS transferred | **98.5 GB** |
| National rows scanned | **2,601,750,679** |
| Regional rows retained | 4,551,207 |
| Period covered | 2020-09-05 → 2021-08-14, with gaps at the spent v1 windows |

## Blocks remaining

| Block | Discovery window | Days |
|---|---|---|
| 5 | 2021-09-05 → 2021-11-14 | 71 |
| 6 | 2021-12-06 → 2022-02-14 | 71 |
| 7 | 2022-03-08 → 2022-05-14 | 68 |
| 8 | 2023-08-14 → 2023-11-11 | 90 |
| 9 | 2023-11-12 → 2023-12-31 | 50 |
| 10 | 2024-07-15 → 2024-10-12 | 90 |
| 11 | 2024-10-13 → 2024-12-31 | 80 |

Resuming requires no protocol change: the ordering, the instrument and the eligibility contract
are all frozen and unchanged. `python scripts/fetch_ais_baseline.py --split discovery --block N`
followed by `python scripts/event3_discovery_block.py --block N`, continuing from block 5.

## What the four processed blocks established

**Three triggers, all classified `unknown`, all rejected on requirement 4** — no independently
documented exogenous driver. None was weather-driven, and in every case the converse check held:
the windiest and wettest days in each context period produced no trigger.

| Block | Window | Occupancy | Peak resid | Regime | Recovery | Class |
|---|---|---|---|---|---|---|
| 1 | — | — | — | — | — | no trigger |
| 2 | 2020-12-08..11 | 6 → 8 on base 3 | 4.0 | `stable` 4/4 | 2021-01-20 | `unknown` |
| 3 | 2021-03-09..12 | 7 → 9 on base 4 | 5.0 | `stable` 3/4 | 2021-04-09 | `unknown` |
| 4 | 2021-06-06..09 | 14 → 16 on base 9 | **7.0** | `stable` 4/4 | 2021-06-17 | `unknown` |

The instrument is doing what it was built to do. All three windows classified
`candidate_port_anomaly` rather than `measurement_confounded` — the coverage model is
discriminating, not rubber-stamping. Block 4's window in particular showed occupancy rising by
seven vessels while the regional vessel count *fell* in residual terms, which is precisely the
port-specific signature the model exists to isolate, and is not something Detector v2 could have
distinguished.

What is missing is not detection. It is **drivers**. Three real, well-measured anchorage
excursions have no independent documentary explanation — no Coast Guard restriction, no channel
closure, no terminal or berth outage, no labour action, no weather.

## The open question this leaves

Two readings remain live, and four blocks are not enough to separate them:

1. **Hampton Roads had no documented disruption in 2020-09 → 2021-08.** Independent evidence
   points this way: the Port of Virginia publicly reported record volumes with *no congestion*
   through 2021 after \$800M of capacity investment. On this reading the remaining 65% of the
   universe — which includes late 2021, 2022, and the whole of 2023-2024 H2 — may still contain
   a qualifying event.
2. **Four-day anchorage excursions at this port routinely have no documented cause.** On this
   reading the driver requirement may never be satisfiable here, and the eventual outcome is
   `NO_QUALIFYING_EVENT_IN_SEARCH_UNIVERSE` after full exhaustion.

Distinguishing them requires processing the remaining blocks. Nothing observed so far settles
it, and this document does not pretend otherwise.

## Invariants at suspension

| | |
|---|---|
| Instrument semantic hash | `b79b6909f48d384c…` — unchanged since the final freeze |
| Detector parameters | unchanged; no Detector v4 exists |
| Event #3 eligibility contract | unchanged, `84a2f8c3df296d0b` |
| Frozen model hashes | `d4670fb1…` / `324a8bf1…` / `880d2d0e…`, drift **NONE** |
| **H1** | **not run** — no simulation, no baseline, no held-out metric |
| Tests | 933 passing |
| `EVENT3_FREEZE_FINAL.md` | deliberately absent |
| `EVENT3_DRIVER_GAP.md` | deliberately absent — no real event was established whose driver could not be represented |

---

# Search resumed at block 5

Resumed under the frozen protocol with no change to ordering, instrument, thresholds, coverage
model, eligibility contract, recovery rule or budget. Blocks 1–4 stand as immutable historical
results.

---

## Block 5 — 2021-09-05 → 2021-11-14

| | |
|---|---|
| Span | 2021-08-22 → 2021-11-14 |
| Warmup | 2021-08-22 → 2021-09-04 |
| Discovery days | 71 |
| Days with observations | **84 / 85** |
| Evaluable discovery days | 70 |
| Artifact set SHA-256 | `1c10756257567abd5951bdec4ee224c5…` |

### The 2021-10-31 dropout — acquisition succeeded, observation did not

Worth separating carefully, because the two failure modes look identical downstream. The
national archive for 2021-10-31 downloaded **cleanly**: 279,515,626 bytes, SHA-256 recorded,
7,204,737 national rows scanned. It then yielded **zero** qualifying regional rows — no
cargo/tanker vessel anywhere in the Hampton Roads box for the entire day.

That is not operationally possible at a port of this size, so it is a **regional coverage
dropout in the source**, not a quiet day. The national file has normal volume; the gap is
specific to this region.

The pipeline treats it as unobserved: no extract, `None` on the contiguous axis, undefined
residual, regime `uncertain`, and it breaks any trigger run. That is the pre-registered
missing-data behaviour and it is correct — an unobserved day is unobserved regardless of why.
Recorded here so the distinction between "not acquired" and "acquired but empty" stays visible.

### Observations

| Series | median | mean | sd | min | max |
|---|---|---|---|---|---|
| `anchorage_occupancy` | 14.0 | 13.88 | 1.85 | 9 | 17 |
| standardised residual | 0.0 | — | 2.05 | −7.0 | **4.0** |

Threshold reachable: max residual 4.0, 8 days at or above 3.0 (11.43%).

Occupancy is both higher and markedly steadier here than in blocks 1–4 — median 14 with sd 1.85,
against medians of 6–10 with sd 2.1–3.7 earlier. A busy but even period.

### Coverage regimes

| Regime | Days | Share |
|---|---|---|
| `stable` | 50 | 71.4% |
| `abrupt_measurement_shift` | 16 | **22.9%** |
| `gradual_shift` | 2 | 2.9% |
| `uncertain` | 2 | 2.9% |

The abrupt rate is the highest of any block so far, just above block 1's 21.1%. Recorded as
context, not applied as a gate — no per-block measurement gate was pre-registered, and creating
one now would be a post-hoc rule change.

### Triggers

**None.** Eight days reached the threshold but no run of four consecutive days occurred.

No historical research performed — there is nothing to research.

---

## Block 6 — 2021-12-06 → 2022-02-14

| | |
|---|---|
| Span | 2021-11-22 → 2022-02-14 |
| Warmup | 2021-11-22 → 2021-12-05 |
| Discovery days | 71 |
| Days with observations | **84 / 85** |
| Evaluable discovery days | 70 |
| Artifact set SHA-256 | `514728d49cf2c5c6804fdab44008b707…` |

A second regional coverage dropout: **2021-12-05** downloaded cleanly (165,012,669 bytes,
4,374,815 national rows) and returned zero regional rows. It falls in the warmup, not the
discovery range, so it affects only the first days' baselines. Treated as unobserved, as before.

### Observations

| Series | median | mean | sd | min | max |
|---|---|---|---|---|---|
| `anchorage_occupancy` | 18.0 | 18.86 | 3.48 | 11 | 27 |
| standardised residual | −0.25 | — | 2.56 | −6.0 | **8.0** |

Threshold reachable: max residual 8.0, 8 days at or above 3.0 (11.43%). This is the busiest
block yet — median occupancy 18 against 6–14 in blocks 1–5.

### Coverage regimes

| Regime | Days | Share |
|---|---|---|
| `stable` | 47 | 67.1% |
| `abrupt_measurement_shift` | 13 | 18.6% |
| `gradual_shift` | 5 | 7.1% |
| `uncertain` | 5 | 7.1% |

### TRIGGER 4 — 2022-01-06 → 2022-01-10

| Field | Value |
|---|---|
| Start | **2022-01-06** |
| Peak | **2022-01-07** |
| End | **2022-01-10** |
| Duration | **5 days** — the first trigger to exceed the 4-day minimum |
| Occupancy trajectory | **19 → 24 → 24 → 21 → 20** |
| Residual trajectory | **3.0 → 8.0 → 8.0 → 4.0 → 3.0** |
| Mean residual | **5.2** |
| Trailing baseline | 16.0 → 17.0 |
| **Coverage regime** | **`stable`** (5 of 5 days) |
| **Candidate class** | **`candidate_port_anomaly`** |
| Measurement confidence | **high** |
| Recovery observed | **yes**, run completed **2022-01-20** |

| Date | Occ | Base | Resid | Vessels | v-res | msg/vessel | m-res | Cells | s-res | Regime |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022-01-04 | 16 | 16.0 | 0.00 | 42 | −2.75 | 210 | −7.54 | 144 | −2.69 | abrupt |
| 2022-01-05 | 18 | 16.0 | 2.00 | 59 | 1.33 | 358 | −1.03 | 188 | 0.56 | stable |
| **2022-01-06** | **19** | 16.0 | **3.00** | 60 | 1.50 | 360 | −0.88 | 182 | 0.19 | stable |
| **2022-01-07** | **24** | 16.0 | **8.00** | 63 | 2.00 | 364 | −0.66 | 231 | 4.00 | stable |
| **2022-01-08** | **24** | 16.0 | **8.00** | 60 | 1.29 | 368 | 0.37 | 174 | −0.31 | stable |
| **2022-01-09** | **21** | 17.0 | **4.00** | 61 | 1.14 | 373 | 0.84 | 186 | 0.54 | stable |
| **2022-01-10** | **20** | 17.0 | **3.00** | 54 | −0.75 | 375 | 1.18 | 167 | −1.33 | stable |
| 2022-01-11 | 18 | 17.0 | 1.00 | 59 | 0.50 | 355 | −0.99 | 165 | −1.56 | stable |

### Reading, before any external source was consulted

**The strongest window in the project, surpassing block 4 on every axis.** It is the first to
exceed the minimum duration (5 days rather than 4), carries the highest peak residual seen
anywhere (8.0, sustained across two consecutive days), and sits on the highest baseline (16),
so the MAD floor plays no part in the result.

The coverage evidence is the cleanest yet. Across the window the regional vessel count moves
only 54–63 with residuals between −0.75 and 2.00 — never approaching the 3.5 shift threshold —
while occupancy rises by eight. Report density is flat throughout (|m-res| ≤ 1.18). All five
days `stable`.

So once again: **the anchorage filled without more ships appearing in the region and without any
change in how they were reported.** On a base of 16 rather than 3, that is a substantial
absolute movement, not a small-count artifact.

One caution: on 2022-01-16/17 the vessel-count residual collapses (−4.00, then −8.67), giving
two `uncertain` days during the recovery tail. As in block 4, this is after the window, not
during it.

### Status at freeze time

Historical research had **not** begun when this entry was written.

---

### Appended after freeze - classification

Added after the above was committed as `921beed`.

**Independent, non-AIS source:** NOAA NCEI daily summaries, station USW00013737,
2021-12-15 to 2022-02-10.

| | Window 2022-01-06..10 | Context period |
|---|---|---|
| Max gust | **16.5 m/s** | p90 17.9, max 24.1 |
| Precipitation | 8.1 mm total | - |
| Snow | **0.0 mm** on all five days | up to 9 mm/day later in the month |

**Not weather-driven.** The windiest days - 2022-01-03 (24.1 m/s), 01-16 (21.9), 01-17 (21.5),
01-28 (20.1) - produced **no trigger**.

#### A documented disruption exists in this block, and it is not this window

Trade-press reporting establishes a real Hampton Roads disruption in January 2022: **two
late-January snowstorms** halted operations for roughly 96 hours, leaving about 11 vessels
anchored outside the harbour, growing to 14 within a week.

The snow dates match the independent weather record exactly - the snowiest days in the period
are **2022-01-22 (9 mm), 01-21 (8 mm), 01-29 (8 mm), 01-28 (2 mm)**.

**That is 11-19 days after this trigger window ended.** The frozen trigger runs 01-06 to 01-10.
Under the causal-timing rule, an effect that clearly precedes its supposed cause is rejected, and
no anticipation mechanism is documented or plausible here. The late-January snowstorms do not
explain the early-January window.

**Classification: `unknown`.** Requirement 4 not met. **Not an Event #3 candidate.**

---

## INSTRUMENT FINDING - the frozen detector missed the documented event

This is the most consequential result of the discovery phase, and it is recorded here rather
than in a footnote because it reframes every prior block.

The late-January disruption **is plainly visible** in the reconstructed series:

| Date | Occupancy | Baseline | Residual | Regime |
|---|---|---|---|---|
| 2022-01-20 | 17 | 19.0 | -2.00 | stable |
| 2022-01-21 | 17 | 19.0 | -2.00 | stable |
| 2022-01-22 | 17 | 19.0 | -2.00 | stable |
| **2022-01-23** | **25** | 18.5 | **4.33** | stable |
| **2022-01-24** | **23** | 18.5 | **3.00** | stable |
| **2022-01-25** | **25** | 18.5 | **4.33** | stable |
| 2022-01-26 | 22 | 19.0 | **1.50** | stable |
| 2022-01-27 | 24 | 19.0 | 2.50 | stable |
| 2022-01-28 | 24 | 19.0 | 2.50 | stable |
| 2022-01-29 | 25 | 19.5 | 2.20 | stable |
| 2022-01-30 | 26 | **21.0** | 1.43 | stable |
| 2022-01-31 | 26 | **22.5** | 1.40 | stable |
| 2022-02-01 | 27 | **23.5** | 1.75 | abrupt |

Occupancy climbs from 17 to a sustained 22-27 and stays there for ten days. **The detector
produced no trigger.** Two mechanisms combined:

1. **The run broke one day short.** Residuals reached 3.0+ on 01-23, 01-24 and 01-25, then 01-26
   fell to 1.50. Three consecutive days against a persistence requirement of four.
2. **The trailing baseline absorbed the event.** As the elevation persisted, the 14-day trailing
   median climbed with it: 18.5, 19.0, 19.5, 21.0, 22.5, 23.5. By 01-30, occupancy of 26 - nine
   above the pre-event level - scored a residual of only 1.43.

### What this means, stated plainly

The frozen instrument detects **short, sharp** excursions and is structurally **blind to
sustained** ones. A 14-day trailing median has a 7-day breakdown point; an event that outlasts
that becomes its own baseline. This was noted as a design property when the lookback was chosen -
"an elevated stretch of up to 7 days cannot corrupt its own baseline" - but its converse was
never tested, because no validation period contained a sustained documented event.

This inverts the reading of blocks 2, 3, 4 and 6. The natural interpretation until now was *the
instrument keeps finding real anomalies that no source explains*. The better-supported
interpretation is now:

> The instrument finds a **class** of anomaly - brief, sharp, 4-5 days - that tends not to have
> documented drivers, while being blind to the class that does: slow-building sustained
> congestion.

Four unexplained short triggers and one missed documented sustained event is a coherent picture,
and it is not a flattering one for the search as designed.

### What is NOT being done about it

- **The detector is not changed.** Detector development is finished and the instrument is frozen
  for the whole of discovery. Adjusting persistence, lookback or baseline estimator now - after
  seeing which event it missed - is precisely the post-hoc move the protocol forbids. The
  instrument semantic hash `b79b6909f48d384c...` stands.
- **Late January 2022 does not become Event #3.** It was **not detected**. Promoting it now would
  be exactly the forbidden inversion: *historical event, then inspect AIS around event*. The
  protocol requires detection to precede research, and it did not detect this.
- **The search continues unchanged** to block 7 under the same rules.

Any future detector generation addressing sustained events would need its own development and
validation split, and this finding is the honest evidence for why one might be warranted.
