# Detector v2 protocol — pre-registered before blind acquisition

> **Written before a single blind day was downloaded.** Every constant below is derived from
> the 56-day development set only
> ([HAMPTON_ROADS_DETECTOR_V2_DATA_SPLIT.md](HAMPTON_ROADS_DETECTOR_V2_DATA_SPLIT.md)) and is
> frozen at publication of this file. Nothing here may be revised once blind data exists — if
> Detector v2 behaves badly, that is reported as a failure and any Detector v3 needs a new
> development/validation split.
>
> Implementation: [`event_sim/detect/detector_v2.py`](../../event_sim/detect/detector_v2.py).

## 1. What v2 has to fix

Detector v1 used one global level threshold, `median + 4 × MAD` over pooled days. On a series
where 94% of variance is between-window drift, that pooled MAD describes the trend, not the
noise. The resulting threshold — 29 vessels — sat above the maximum ever observed, 26. Its
0% false-positive rate was not selectivity; it was a rule that could not fire.

The question v2 must answer instead:

> Is there a short-term disruption signal materially different from the slowly evolving
> background anchorage-utilisation level?

## 2. Metric set — deliberately one

| Used | Not used |
|---|---|
| `anchorage_occupancy` (daily, per the frozen measurement) | entry/exit imbalance |
| `vessels_in_region` — **as an independent coverage diagnostic only** | dwell shift, p90 dwell shift |

Only one detection metric. Entry/exit imbalance is a near-linear function of occupancy
change, so it adds correlated evidence rather than independent evidence. Dwell was excluded
on measurement grounds, not preference: 130 of 174 development spells were censored by the
7-day window edges, so the completed-dwell distribution is biased toward short stays and
cannot support a threshold. Adding metrics that cannot carry their own weight would multiply
the ways to declare a trigger without multiplying the evidence.

## 3. Detector definition

```
expected(t)  = median( occupancy[t-14 .. t-1] )          # strictly trailing
scale(t)     = max( MAD( occupancy[t-14 .. t-1] ), 1.0 )
residual(t)  = ( occupancy(t) - expected(t) ) / scale(t)

trigger      = residual(t) >= 3.0  for  4 consecutive days
```

Level-invariance comes from `expected(t)` being local: when background utilisation drifts
from 3 to 21 vessels, the trailing median drifts with it and the residual stays near zero.
No global occupancy level appears anywhere in the rule.

## 4. Frozen parameters and their derivation

| Parameter | Value | Derived from the development set |
|---|---|---|
| `LOOKBACK_DAYS` | **14** | Worst observed drift is **0.066 vessels/day**. A trailing median lags the present by ~(L+1)/2 days, so lag bias is 0.066 × 7.5 = **0.50 vessels** — half the within-window deviation MAD of 1.0. At L=28 the bias reaches 0.96, a full MAD, and the baseline would begin reading drift as signal. L=14 also gives 14 points for a stable median/MAD and a 50% breakdown point, so an elevated stretch of up to 7 days cannot corrupt its own baseline. |
| `MIN_LOOKBACK_PRESENT` | **10** of 14 | Below this the baseline is too thin to trust; the residual is undefined and the day cannot trigger. |
| `SCALE_FLOOR` | **1.0** vessel | MAD is 0 for a run of identical counts, which would make any positive deviation infinitely significant. One vessel is the smallest change the metric can express. |
| `RESIDUAL_THRESHOLD` | **3.0** | The development distribution of \|deviation from window median\| has MAD 1.0, **p90 = 3**, max = 5. So 3.0 is the 90th percentile of ordinary daily deviation — unusual for a single day, not rare. It sits **inside** the observed range, which is precisely what v1's threshold did not. |
| `PERSISTENCE_DAYS` | **4** | The longest run of consecutive positive deviations anywhere in the development set is **3 days**. Requiring 4 demands a pattern the development period never produced, while staying below the 7-day breakdown limit implied by the lookback. |
| `COVERAGE_GUARD_RESIDUAL` | **3.0** | Same robust scale, applied to `vessels_in_region` (development within-window MAD 3.0 vessels). |
| `COVERAGE_CONFOUND_SHARE` | **0.5** | A trigger window is reported coverage-confounded when half or more of its days carry the flag. |

## 5. Causality — no look-ahead

The baseline for day *t* is computed from the slice `[t-14, t)`. Day *t* is excluded by
construction; the window is never centred; no future observation enters any quantity used at
*t*.

This is not a stylistic preference. A centred window lets the event being detected shape the
baseline it is measured against, which suppresses exactly the signal the detector exists to
find. A test asserts the property directly: mutating any future value must leave every
earlier residual bit-identical.

## 6. Coverage handling — flag, never correct

AIS visibility grew 2.10× across the development period, so a rise in occupancy can be a rise
in what the receivers see rather than in what the port is doing.

`vessels_in_region` gets its own trailing residual on the same robust scale. A day whose
coverage residual reaches 3.0 is flagged `measurement_anomaly`.

**Occupancy is never divided by the regional count.** Normalising would fold a measurement
correction into the anomaly statistic itself, where it could be neither audited nor switched
off, and it would also suppress genuine port events that happen to coincide with more
shipping being present. Measurement correction stays distinct from anomaly detection, per the
protocol requirement.

A coverage-flagged window is classified `measurement_artifact`, not `port_event`, unless
independent evidence supports the latter.

## 7. Missing-data handling

- The blind sample is evaluated on a **contiguous daily axis**; a day with no data is `None`,
  never a gap in the sequence, so "no data" and "no vessels" stay distinguishable.
- A day with fewer than 10 present days in its lookback has an undefined residual and cannot
  trigger.
- A day with an undefined residual **breaks** a run rather than extending it. An unmeasured
  day is not evidence of continued elevation.
- **Stop condition:** if more than **10%** of protocol days fail to acquire, acquisition is
  incomplete and the evaluation does not run.

## 8. Pre-registered blind evaluation criteria

Evaluated in this order, before any historical research.

| # | Criterion | Operational test | Failure outcome |
|---|---|---|---|
| C1 | Threshold reachable | max residual over evaluable days **≥ 3.0** | `DETECTOR_V2_TOO_INSENSITIVE` |
| C2 | Does not trigger constantly | share of evaluable days inside a trigger window **≤ 0.10** | `DETECTOR_V2_TOO_SENSITIVE` |
| C3 | Baseline adapts to drift | median residual over evaluable days within **[−0.5, +0.5]**, and \|median residual of first third − median residual of last third\| **≤ 1.0** | `DETECTOR_V2_INCONCLUSIVE` |
| C4 | Events survive adaptation | structural: `PERSISTENCE_DAYS < LOOKBACK_DAYS / 2` | asserted by test, not by data |
| C5 | Not coverage-dominated | fewer than half of trigger windows coverage-confounded | `DETECTOR_V2_COVERAGE_CONFOUNDED` |

**Zero triggers is not automatically a pass and not automatically a failure.** The validity
question is C1, not the trigger count. If C1–C5 pass with no trigger window, the outcome is
`DETECTOR_V2_VALID_NO_EVENT` — a working detector reporting that nothing happened.

### Outcome mapping

```
C1..C5 pass, >=1 non-confounded trigger window  ->  DETECTOR_V2_VALID_EVENT_FOUND
C1..C5 pass, 0 trigger windows                  ->  DETECTOR_V2_VALID_NO_EVENT
C1 fails                                        ->  DETECTOR_V2_TOO_INSENSITIVE
C2 fails                                        ->  DETECTOR_V2_TOO_SENSITIVE
C5 fails                                        ->  DETECTOR_V2_COVERAGE_CONFOUNDED
C3 fails                                        ->  DETECTOR_V2_INCONCLUSIVE
acquisition < 90% of protocol days              ->  STOP, no evaluation
```

## 9. What happens after evaluation

1. Trigger windows are **frozen** into
   `HAMPTON_ROADS_DETECTOR_V2_WINDOWS.md` before any historical research begins.
2. Only then may each window be researched against independent sources and classified
   `capacity_side` / `arrival_side` / `mixed` / `weather` / `administrative` /
   `measurement_artifact` / `unknown`.
3. A window becomes an Event #3 candidate only if an **exogenous driver** is independently
   supported. AIS outcome behaviour cannot establish its own driver.
4. The existing frozen Event #3 eligibility contract applies unchanged.
5. **H1 is not run**, whatever the outcome.

## 10. No re-tuning

If Detector v2 behaves badly on the blind sample, the failure is reported. Thresholds are not
adjusted and re-run against the same days. A Detector v3 requires a new split, and the blind
sample may become development data only after its failure is formally recorded.
