# Detector v3 blind evaluation — outcome `DETECTOR_V3_VALID`, no Event #3

> **The detector passed all six pre-registered validity criteria.** It found one trigger
> window, and that window does **not** qualify as Event #3: no exogenous driver is
> independently documented.
>
> `STOP_HAMPTON_ROADS` was **not** reached — the measurement environment proved interpretable.
>
> **H1 was not run.** Frozen hashes verify unchanged.

## 1. Acquisition

| | |
|---|---|
| Frozen range | 2023-02-01 → 2023-07-30, contiguous |
| Days requested / acquired | **180 / 180** |
| National AIS transferred | **59.91 GB** |
| National rows scanned | **1,529,724,767** |
| Regional rows retained | 3,363,172 |
| Evaluable days after warmup | **170** |
| Missingness | **0.0%** |

**Four days initially failed** — 2023-02-25, 02-26, 02-27, 03-03 — all with `BadZipFile`, i.e.
a truncated transfer rather than a missing artifact. Re-probing the source showed all four
present (HTTP 200, ~300 MB, `application/zip`), and a retry at lower concurrency acquired them
cleanly. Recorded rather than silently absorbed: the first pass was 176/180 (97.8%), above the
90% tolerance, so the run would have been *permitted* to proceed incomplete. It was completed
instead.

## 2. Measurement stability — reported before any event interpretation

| Regime | Days | Share of evaluable |
|---|---|---|
| `stable` | 128 | 75.3% |
| `abrupt_measurement_shift` | 24 | **14.1%** |
| `gradual_shift` | 10 | 5.9% |
| `uncertain` | 8 | **4.7%** |

| Diagnostic | median | sd | min | max |
|---|---|---|---|---|
| `vessels_in_region` | 54.0 | 8.97 | 33 | 76 |
| `messages_per_vessel` | 351.8 | 29.0 | 228.6 | 439.5 |
| `region_cells` | 184.0 | 21.2 | 144 | 257 |

**The measurement environment is interpretable.** Only 4.7% of days are `uncertain` against a
25% limit — the classifier makes a call on 95% of the period — and all four regimes occur, so
it is not degenerate.

**But the stability margin is thin.** `abrupt_measurement_shift` ran at **14.12%** against a
**15%** limit: a pass by 0.88 percentage points. Stated in the body rather than a footnote,
because it bounds how much weight any single window can carry, and because a slightly worse
period would have produced `DETECTOR_V3_MEASUREMENT_UNSTABLE` and with it a recommendation to
abandon Hampton Roads entirely.

## 3. Occupancy detection

| Series | median | mean | sd | min | max |
|---|---|---|---|---|---|
| `anchorage_occupancy` | 15.0 | 14.75 | 3.57 | 6 | 26 |
| standardised residual | 0.0 | −0.00 | 2.13 | −5.0 | **7.0** |

| | |
|---|---|
| Threshold | 3.0 |
| Max observed residual | **7.0** — reachable |
| Days at or above threshold | 19 (**11.2%**) |
| Trigger windows | **1** |
| Trigger days | 5 (**2.94%** of evaluable) |
| Median residual | **0.0** |
| First-to-last-third drift | **0.5** |

The occupancy detector, unchanged from v2, behaved on a third independent period exactly as
designed: median residual 0.0, drift 0.5, tail frequency 11.2% against the ~10% design target
derived once from the v1 development set. Three periods, three eras, no re-derivation.

## 4. Criteria

| # | Criterion | Result | Value |
|---|---|---|---|
| V1 | Threshold reachable | **PASS** | max residual 7.0 ≥ 3.0 |
| V2 | Not too sensitive | **PASS** | 2.94% trigger days (limit 15%) |
| V3 | Measurement interpretable | **PASS** | 4.71% uncertain (limit 25%) |
| V4 | Measurement stable | **PASS** | 14.12% abrupt (limit 15%) — narrow |
| V5 | Classifier discriminates | **PASS** | 4 distinct regimes |
| V6 | Baseline adapts | **PASS** | median 0.0, drift 0.5 |

**Outcome: `DETECTOR_V3_VALID`.** `recommend_stop_hampton_roads = False`.

## 5. The trigger window

Frozen before research in
[HAMPTON_ROADS_DETECTOR_V3_WINDOWS.md](HAMPTON_ROADS_DETECTOR_V3_WINDOWS.md), committed
`363b934`.

**2023-06-01 → 2023-06-05.** Occupancy 19 → 22 → 21 → 21 → 21 against a baseline rising
14.5 → 16.0; peak residual 7.0. Coverage regime **`gradual_shift`** → candidate class
**`candidate_with_context`**.

The coverage model is what produces that classification, and it is precisely what v2 could not
do. Across the window, vessel count rose 59 → 68 alongside occupancy, while report density
stayed flat (never above 0.99 robust units) and spatial footprint stayed flat until the final
day. *More ships, reported the same way.* That is traffic rather than instrumentation — and
equally, it is not a demonstrated port-specific anomaly, because the occupancy rise co-occurs
with a regional traffic rise the detector cannot attribute to the port.

A genuine observation-regime change begins at 06-05 and runs through 06-08: footprint expands
from ~190 to ~250 cells while vessel count and report density move much less. It starts *after*
the peak, so it does not explain the window — but it is exactly the kind of shift that would
have been invisible to v2, and that a coverage-normalised statistic would have silently
absorbed instead of flagging.

## 6. Historical research

Conducted only after the window document was committed (`363b934`), so the ordering is provable
from git history rather than asserted.

**Independent, non-AIS source:** NOAA NCEI daily summaries, station USW00013737 (Norfolk
International Airport), 2023-05-10 → 2023-06-30.

| | Window 2023-06-01..05 | Context period |
|---|---|---|
| Max gust | **13.9 m/s** | p90 15.7, max 21.0 |
| Precipitation | 0.5 mm across all 5 days | up to 55.4 mm in one day |

**Not weather-driven**, and the converse check holds: the windiest and wettest days in the
period — 2023-06-27 (21.0 m/s), 06-25 (21.0), 06-23 (55.4 mm), 06-21, 06-16 — produced **no
trigger at all**.

Searches of Coast Guard, Port of Virginia, Army Corps and maritime trade press surfaced no
channel closure, port condition, terminal shutdown, berth outage or labour action in the
window.

**Classification: `unknown`.**

## 7. Event #3 eligibility

| # | Requirement | Status |
|---|---|---|
| 1 | Occupancy anomaly independently detected | **met** |
| 2 | Measurement regime sufficiently interpretable | **partial** — `gradual_shift`, moderate confidence |
| 3 | Trajectory with accumulation / peak / recovery | **not met** — occupancy does not recover; it keeps rising after the window, reaching 26 by 06-08 |
| 4 | Exogenous driver independently documented | **NOT MET** |
| 5 | Driver representable by the simulator | n/a |
| 6 | Frozen eligibility contract passes unchanged | n/a |

Requirement 4 fails outright and requirement 3 fails on the observed trajectory. **No Event #3
candidate.**

`EVENT3_FREEZE_V5.md` is deliberately not created. Neither is `EVENT3_DRIVER_GAP.md` — that
document exists for a *real event* whose driver the simulator cannot represent, and no real
event was established here. Writing one would dress an absence of evidence up as a
representational limitation.

Candidate ordering (§30) is trivial with a single window, and the first-qualified stopping rule
never engaged because nothing qualified.

## 8. What this run does and does not establish

**Established:** Hampton Roads now has a *working* measurement protocol. Across three
independent periods spanning 2020–2023, the occupancy detector's parameters — derived once from
the v1 development set and never re-derived — produced the intended tail frequency, a zero
median residual and minimal drift every time. The coverage-regime model separates traffic
growth from observation-regime change on unseen data, and does so without ever touching the
occupancy statistic.

**Not established:** that Hampton Roads contains a usable Event #3. Three validation periods
have now yielded three windows, classified `unknown`, `measurement_artifact` and `unknown`.
None had a documented exogenous driver.

**The honest reading:** the instrument works; the site may simply be quiet. Hampton Roads is a
well-run port with no major documented disruption in any period examined so far, which is a
fact about the port rather than a defect in the method. That distinction is why
`STOP_HAMPTON_ROADS` was not triggered — the pre-registered exit condition is for an
*uninterpretable measurement environment*, and this environment turned out to be interpretable.

## 9. Status

| | |
|---|---|
| Outcome | `DETECTOR_V3_VALID` |
| `STOP_HAMPTON_ROADS` | **not reached** — measurement environment is interpretable |
| Event #3 | none nominated |
| H1 | **not run**; lifecycle remains `experimental_no_effect` |
| Known model defect | remains `known` |
| Frozen hashes | verified, drift NONE |
| v1 verdict | preserved: `HAMPTON_ROADS_LOW_POWER` |
| v2 verdict | preserved: `DETECTOR_V2_COVERAGE_CONFOUNDED` |

The v3 blind sample is now spent. Detector v3 itself is validated and needs no successor;
searching for Event #3 would use it unchanged on further unseen periods, which is a decision
for a separate task.
