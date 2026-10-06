# Detector v2 blind evaluation — outcome `DETECTOR_V2_COVERAGE_CONFOUNDED`

> **The pre-registered validity gate was not passed.** Detector v2's triggers therefore
> cannot nominate Event #3. No threshold was adjusted, and the detector was not re-run.
>
> **H1 was not run.** Frozen hashes verify unchanged.

## 1. Acquisition

| | |
|---|---|
| Frozen range | 2022-07-01 → 2022-12-27, contiguous |
| Days requested / acquired | **180 / 180** — zero missing, zero failures, zero bad checksums |
| National AIS transferred | **61.46 GB** |
| National rows scanned | **1,568,409,942** |
| Regional rows retained | 2,892,902 |
| Evaluable days after 14-day warmup | **170** |
| Missingness | **0.0%** (tolerance was ≤10%) |

## 2. What the blind sample looked like

| Series | mean | median | sd | MAD | min | max |
|---|---|---|---|---|---|---|
| `anchorage_occupancy` | 11.93 | 12.0 | 3.31 | 2.0 | 3 | 20 |
| `vessels_in_region` (coverage) | 45.92 | 46.0 | 6.01 | — | 27 | 59 |

Worth noting: development ended at ~21 vessels/day in 2022-Q2, and the blind period sits at
~12. **The trend reversed.** A detector tuned to a rising level would have been wrong in a new
way here; a level-invariant one does not care, which is the first evidence that the v2 design
choice was the right one.

## 3. Residual behaviour

| | value |
|---|---|
| n | 170 |
| mean / median | −0.0003 / **0.0** |
| sd / MAD | 2.07 / 1.0 |
| min / p10 / p25 / p75 / p90 / max | −5.0 / −2.5 / −1.0 / 1.0 / 2.5 / **7.0** |

Residuals are coarse-valued (3.0, 4.0, 5.0 …) because occupancy is an integer count and the
trailing MAD is frequently exactly 1.0 or 2.0. The metric's resolution is one vessel; the
residual inherits that. Worth stating, because it means the threshold of 3.0 operationally
reads as *"at least 3 vessels above the trailing median when MAD is 1"*.

## 4. Criteria, applied as written

| # | Criterion | Result | Evidence |
|---|---|---|---|
| C1 | Threshold reachable | **PASS** | max residual **7.0** vs threshold 3.0; 16 days (9.4%) at or above |
| C2 | Not constantly triggering | **PASS** | 8 trigger days / 170 evaluable = **4.71%** (limit 10%) |
| C3 | Baseline adapts to drift | **PASS** | median residual **0.0**; first-third vs last-third drift **0.33** (limit 1.0) |
| C4 | Events survive adaptation | **PASS** | structural: persistence 4 < lookback 14 / 2 |
| C5 | Not coverage-dominated | **FAIL** | 1 of 2 windows confounded = **0.50**; criterion required **< 0.50** |

**Outcome: `DETECTOR_V2_COVERAGE_CONFOUNDED`.**

## 5. What v2 fixed, stated before what it got wrong

Detector v1's defining failure was a threshold above anything that had ever happened (29 vs
observed max 26), producing a rule that could not fire. That is repaired, and the repair
generalised out of sample:

- **The threshold was derived from development data as the p90 of |deviation|, predicting
  roughly 10% of days at or above it. On 170 unseen days, 9.4% landed at or above.** That is
  the parameter behaving on new data exactly as its derivation said it would.
- **The trend is gone.** The development series drifted 6.26× with 94% of variance between
  windows. On the blind sample the median residual is 0.0 and first-to-last-third drift is
  0.33 robust units — the slow background level, in both directions, is fully absorbed.
- **Level invariance held across a reversal**, from ~21 vessels/day down to ~12.

## 6. Why C5 failed, and why it is not being changed

Both facts matter and they point in opposite directions.

**The coverage guard worked.** Window 2 (2022-12-11..14) has coverage residuals of 1.71,
3.20, 3.00 and 4.50 — on 12-14 the *coverage* residual exceeds the occupancy residual. More
ships were visible in the region, and occupancy rose with them. The guard correctly refused
to call that a port-specific disruption. Window 1 was left alone, with 1 flagged day of 4.
That is exactly the discrimination the guard was designed to perform.

**The criterion consuming the guard's output was badly specified.** `confounded_share < 0.5`
is a *share*, and with 2 windows a share can only take the values 0, 0.5 or 1.0. At n=2 the
criterion silently becomes "zero confounded windows permitted" — far stricter than intended,
and it fails on the exact boundary. The same detector producing 4 windows with 1 confounded
would have scored 0.25 and passed, on identical per-window evidence.

This is a defect in my pre-registration, not in the detector. It is the same class of error
as the H1 experiment's aggregator: a rule that is reasonable in the abstract and unstable at
the sample size it actually meets.

**It is not being fixed here.** Changing a criterion after seeing the data it failed on is
precisely the move the protocol exists to prevent, and the fact that I can articulate a
principled reason for the change does not make it less post-hoc. The failure is recorded; a
Detector v3 needs a new development/validation split.

## 7. Coverage diagnostic behaviour

20 of 170 evaluable days (11.8%) carried a coverage flag, clustered in late July, mid-to-late
August, mid-September, and early December. Coverage varied over a wide range (27–59 vessels
in region) with no monotonic drift across the period.

This vindicates keeping the coverage check **separate from** the anomaly statistic. Had
occupancy been normalised by regional vessel count, window 2 would have been silently damped
rather than visibly flagged, and there would have been no record that the detector had made a
judgement at all.

## 8. Historical classification

Performed only after [HAMPTON_ROADS_DETECTOR_V2_WINDOWS.md](HAMPTON_ROADS_DETECTOR_V2_WINDOWS.md)
was written and committed (`9657261`), so the ordering is provable from git history rather
than asserted.

Independent source used: **NOAA NCEI daily summaries, station USW00013737** (Norfolk
International Airport) — non-AIS, machine-readable, covering 2022-10-18 → 2022-12-20.

| Window | Max gust | Precip | Period p90 gust | Classification |
|---|---|---|---|---|
| 2022-10-24..27 | 12.5 m/s | 0.0 mm all days | 14.3 m/s | **`unknown`** |
| 2022-12-11..14 | 13.0 m/s | 0.0 mm all days | 14.3 m/s | **`measurement_artifact`** |

**Neither window is weather-driven.** Both sit *below* the period's p90 gust, with no
precipitation on any of the eight days. The check also runs the other way: the three windiest
days in the context period — 2022-11-12 (18.3 m/s), 2022-11-11 (17.0), 2022-10-23 (16.5) —
produced **no trigger at all**. So the detector is not a wind sensor.

News and trade-press searches found no Coast Guard port condition, channel closure, terminal
shutdown, labour action or berth outage in either window. The December 2022 blizzard (Winter
Storm Elliott) fell on **21–26 December**, *after* window 2, and does not explain it.

One observation recorded as a hypothesis and explicitly **not** a finding: 2022-10-23, the day
immediately before window 1 began, was the third windiest day in the context period (16.5 m/s),
and occupancy rose monotonically 10 → 13 → 14 → 15 → 17 over the following four days. That is
consistent with vessels held at anchor after a blow. It is one day at one station with no
documented restriction, it was noticed after the fact, and it comes from a run that failed
validation. It is not a driver.

## 9. Driver requirement — not met

Per the protocol, AIS outcome behaviour cannot establish its own driver. For window 1 no
exogenous driver was independently supported, so it does not become an Event #3 candidate.
Window 2 is a measurement artifact.

**No Event #3 candidate. `EVENT3_FREEZE_V4.md` is deliberately not created.**

## 10. Status

| | |
|---|---|
| Outcome | `DETECTOR_V2_COVERAGE_CONFOUNDED` |
| Event #3 | none nominated |
| H1 | **not run**; lifecycle remains `experimental_no_effect` |
| Known model defect | remains `known` |
| Frozen hashes | verified, drift NONE |
| Detector v1 verdict | preserved unchanged as `HAMPTON_ROADS_LOW_POWER` |

Per the no-re-tuning rule, the 180-day blind sample is now **spent as validation data** and
may serve only as development data for any future Detector v3, which requires a fresh
validation period.
