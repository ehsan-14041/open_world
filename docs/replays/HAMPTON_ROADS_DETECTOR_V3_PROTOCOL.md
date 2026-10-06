# Detector v3 protocol — pre-registered before blind acquisition

> **Written and committed before any v3 blind day was selected or downloaded.** Every constant
> below comes from the spent v1/v2 datasets. Nothing here may be revised once blind data
> exists; if v3 fails, the failure is recorded and any v4 needs another fresh validation set.
>
> Implementation: [`event_sim/detect/detector_v3.py`](../../event_sim/detect/detector_v3.py).

## 1. The question v3 answers

> Did anchorage utilisation behave unusually relative to its own recent history, **while the
> broader AIS observation environment remained interpretable**?

This is deliberately *not* the question "did occupancy increase faster than total vessels?".
That second question turns coverage into part of the anomaly statistic, which is exactly what
this protocol forbids.

## 2. Occupancy detector — unchanged from v2

Kept identical, because v2's occupancy logic demonstrably generalised to unseen data: median
residual 0.0, first-to-last-third drift 0.33, threshold reachable at max residual 7.0, and a
tail frequency of 9.4% against a design target of ~10%.

```
expected(t)  = median( occupancy[t-14 .. t-1] )          strictly trailing
scale(t)     = max( MAD( occupancy[t-14 .. t-1] ), 1.0 )
residual(t)  = ( occupancy(t) - expected(t) ) / scale(t)
trigger      = residual(t) >= 3.0  for  4 consecutive days
```

| Parameter | Value | Changed? |
|---|---|---|
| `LOOKBACK_DAYS` | 14 | no |
| `MIN_LOOKBACK_PRESENT` | 10 | no |
| `SCALE_FLOOR` | 1.0 | no |
| `RESIDUAL_THRESHOLD` | 3.0 | no |
| `PERSISTENCE_DAYS` | 4 | no |

`detector_v3.py` **imports** these from `detector_v2.py` rather than restating them, so
"unchanged" is verifiable by a test rather than asserted in prose.

## 3. Coverage is context, never correction

Two variables, kept conceptually and computationally separate:

| Variable | Role |
|---|---|
| `anchorage_occupancy` | the port-state observable |
| `vessels_in_region`, report density, spatial footprint | measurement/traffic context diagnostics |

**Forbidden, and asserted by tests:**

- computing `anchorage_occupancy / vessels_in_region` as the anomaly metric,
- regressing occupancy on coverage and calling the residual a queue,
- subtracting any fitted coverage effect from occupancy.

Each of those silently converts an observable into a model-corrected latent quantity that
still carries the observable's name. The correction would be applied before anyone could see
it, and the number would no longer be anything that was measured.

## 4. Coverage diagnostics

All three are computed over the whole region, never over the anchorages, so they cannot be
confused with the port-state observable. All use the same causal trailing-residual machinery
as occupancy — 14-day trailing window, robust scale, day *t* excluded from its own baseline.

| Diagnostic | Definition | What it detects |
|---|---|---|
| `vessels_in_region` | distinct deep-draft MMSI in the region that day | volume of observed traffic |
| `messages_per_vessel` | regional AIS rows ÷ distinct MMSI | *character* of observation — how densely each vessel is reported |
| `region_cells` | distinct 0.01° (~1.1 km) grid cells with at least one report | spatial footprint of observation |

The second and third are the ones that separate traffic change from measurement change. More
ships reported the same way is traffic. The same ships reported differently is instrumentation.

## 5. Regime classifier

Thresholds from |trailing residual| distributions over the spent v1/v2 data (median / p75 /
p90 / p95 / max): `vessels_in_region` 1.29 / 2.50 / 3.67 / 4.50 / 10.00;
`messages_per_vessel` 1.19 / 1.94 / 2.99 / 3.85 / 6.46; `region_cells` 1.17 / 2.23 / 3.85 /
4.62 / 9.10.

| Constant | Value | Basis |
|---|---|---|
| `V_SHIFT` | 3.5 | ≈ p90 of vessel-count residual |
| `M_ABRUPT` | 4.0 | ≈ p95 of report-density residual |
| `S_ABRUPT` | 4.5 | ≈ p95 of footprint residual |
| `M_STABLE` | 2.0 | ≈ p75 — "report density approximately steady" |
| `S_STABLE` | 2.5 | ≈ p75 — "footprint approximately steady" |

Rules, applied in order to |residuals| `v`, `m`, `s`:

```
any residual undefined                     -> uncertain
m >= 4.0  or  s >= 4.5                     -> abrupt_measurement_shift
v >= 3.5 and m < 2.0 and s < 2.5           -> gradual_shift          (traffic)
v >= 3.5                                   -> uncertain
otherwise                                  -> stable
```

Order matters: a change in the *character* of observation outranks a change in its volume,
because an instrument that started reporting differently invalidates the count it produces.

**`uncertain` is a first-class outcome.** A classifier that always decides is not more
informative than one that admits when it cannot. Rule 4 exists precisely so that "the count
moved and I cannot attribute it" is sayable.

On the spent v2 period this classifier yields stable 77.8%, uncertain 8.3%, abrupt 8.3%,
gradual 5.6% — all four regimes occur, so it is not degenerate.

## 6. Regime gating, not normalisation

```
occupancy trigger + stable                    -> candidate_port_anomaly
occupancy trigger + gradual_shift             -> candidate_with_context
occupancy trigger + abrupt_measurement_shift  -> measurement_confounded
occupancy trigger + uncertain                 -> uncertain
```

A window takes the **most severe regime present on at least 2 of its days**
(`WINDOW_REGIME_MIN_DAYS = 2`). Severity order: `stable` < `gradual_shift` < `uncertain` <
`abrupt_measurement_shift`.

An absolute day count, deliberately not a share — see §8.

## 7. Causality

Every component is causal. At day *t*, both the occupancy baseline and all three coverage
residuals use only the slice `[t-14, t)`. No centred windows, no future-informed smoothing, no
future regime classification.

Mutation tests assert that changing any future observation leaves unchanged: the occupancy
residual, the coverage classification, and the trigger state at every earlier day.

## 8. Validity criteria — all at the day level

Detector v2's gate was a share over 2 windows, whose support was {0, 0.5, 1.0}. Every
criterion here is either a rate over evaluable days (n in the hundreds) or a structural
property, so none degenerates at small trigger counts.

| # | Criterion | Test | Failure outcome |
|---|---|---|---|
| V1 | Threshold reachable | max occupancy residual **≥ 3.0** | `DETECTOR_V3_TOO_INSENSITIVE` |
| V2 | Not too sensitive | trigger days ≤ **15%** of evaluable days | `DETECTOR_V3_TOO_SENSITIVE` |
| V3 | Measurement interpretable | `uncertain` days ≤ **25%** of evaluable days | `DETECTOR_V3_TOO_MANY_UNCERTAIN_DAYS` |
| V4 | Measurement stable | `abrupt_measurement_shift` days ≤ **15%** of evaluable days | `DETECTOR_V3_MEASUREMENT_UNSTABLE` |
| V5 | Classifier discriminates | at least **2 distinct regimes** occur | `DETECTOR_V3_MEASUREMENT_UNSTABLE` |
| V6 | Baseline adapts | median residual in **[−0.5, +0.5]** and first-to-last-third drift ≤ **1.0** | `DETECTOR_V3_INCONCLUSIVE` |

All pass → **`DETECTOR_V3_VALID`**.

Zero triggers is neither automatically pass nor automatically fail; V1 is the validity
question, not the trigger count. That lesson is retained from v1, whose zero false-positive
rate meant only that its threshold could never be reached.

## 9. Missing data

Contiguous daily axis; a missing day is `None`, never a gap. Fewer than 10 present days in a
lookback leaves the residual undefined and the regime `uncertain`. An undefined day breaks a
trigger run rather than extending it. **If more than 10% of protocol days fail to acquire,
STOP — no evaluation runs.**

## 10. Project-level exit condition

Pre-registered, because detectors must not be iterated indefinitely.

If v3 fails with **`DETECTOR_V3_MEASUREMENT_UNSTABLE`** or
**`DETECTOR_V3_TOO_MANY_UNCERTAIN_DAYS`**, the failure is about the measurement environment
rather than a narrow implementation defect, and the recommendation is:

```
STOP_HAMPTON_ROADS
```

— reject Hampton Roads as the Event #3 measurement path and return to dataset selection. No
Detector v4 is created automatically. Three detector generations are enough to decide whether
this is a viable scientific measurement system.

If v3 fails with `TOO_SENSITIVE`, `TOO_INSENSITIVE` or `INCONCLUSIVE`, that is an
implementation defect; the failure is recorded, the blind sample is spent, and any v4 requires
another fresh validation period.

## 11. Candidate ordering and stopping

If multiple windows qualify, they are ranked by:

1. measurement confidence (`candidate_port_anomaly` > `candidate_with_context` > others),
2. eligibility completeness against the frozen contract,
3. independent driver observability,
4. chronological order as final tie-break.

**The first candidate that passes the frozen eligibility contract stops the search.** No
searching for a more dramatic event. Expected H1 performance is not a criterion and H1 remains
uninspected.

## 12. After detection

1. Trigger windows frozen into `HAMPTON_ROADS_DETECTOR_V3_WINDOWS.md`, committed, **before**
   any historical search.
2. Only then, independent historical research; drivers classified `capacity_side` /
   `arrival_side` / `weather` / `mixed` / `administrative` / `measurement_artifact` /
   `unknown`.
3. Weather may be used **after** trigger freeze as potential causal evidence. It is never fed
   into the detector and is not AIS coverage correction.
4. A trigger becomes an Event #3 candidate only with an independently documented exogenous
   driver, an interpretable measurement regime, a trajectory with accumulation/peak/recovery,
   and an unchanged pass of the frozen eligibility contract.
5. If a real event is found whose driver cannot be represented without abusing `port_capacity`,
   **STOP** and write `EVENT3_DRIVER_GAP.md` rather than faking the intervention.
6. **H1 is not run**, whatever the outcome. This task ends at a frozen Event #3, if any.
