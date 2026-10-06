# Detector v3 data-role split

> Written before the v3 protocol was finalised and before any v3 blind day was selected or
> acquired. Both earlier datasets have finished their validation lives; this file records
> that, so neither can quietly be reused as evidence.

## 1. Immutable historical results

Neither verdict is edited, reinterpreted, or re-run.

| Detector | Verdict | Why it ended that way |
|---|---|---|
| v1 | `HAMPTON_ROADS_LOW_POWER` | Fixed-level anomaly protocol invalidated by severe baseline nonstationarity: 94% of variance was between-window drift, and the pooled threshold of 29 sat above the observed maximum of 26. |
| v2 | `DETECTOR_V2_COVERAGE_CONFOUNDED` | Occupancy detection generalised well, but the frozen coverage gate failed exactly as registered: 1 of 2 windows confounded, share 0.50, criterion required < 0.50. |

Also preserved unchanged: the v1 report, the v2 protocol, blind-sample and windows documents,
the v2 results, the Event #3 eligibility contract, the baseline and H1 models, the evaluation
code, and the lifecycle history.

## 2. The protocol lesson from v2

Recorded precisely, because the tempting summaries are both wrong.

**The lesson is not** "coverage should be divided out", and **not** "the threshold should be
changed".

**The supported lesson is:** a port-specific occupancy anomaly may coincide with a broad change
in the number of observable or in-region vessels, and Detector v2 lacked a sufficiently
explicit measurement-regime model to distinguish those cases. Its coverage guard could see that
something moved; it could not say whether what moved was the port or the instrument.

**The separate protocol-design flaw:** the coverage gate was a *proportion* evaluated over only
two trigger windows, so its entire support was {0, 0.5, 1.0}. At n=2, "fewer than half
confounded" silently means "none permitted". The same detector producing 4 windows with 1
confounded would have scored 0.25 and passed on identical per-window evidence.

**The v2 verdict is not changed because of this flaw.** The criterion was registered in
advance and applied as written. Recognising afterwards that it was poorly specified is a reason
to design the next one differently, not a licence to rescore the last one.

## 3. Data roles

| Dataset | Days | Role now |
|---|---|---|
| 2020-08-15 → 2022-05-21 (8 × 7-day windows) | 56 | `measurement_protocol_development_set_v1` |
| 2022-07-01 → 2022-12-27 (contiguous) | 180 | `detector_v2_blind_validation_spent` |
| 2023-02-01 → 2023-07-30 (contiguous) | 180 | **v3 blind validation — not yet acquired** |

Detector v3 may inspect **both** earlier datasets freely for development: characterising normal
coverage variation, gradual drift, abrupt changes, report density, vessel-count variation,
spatial consistency, and the relationship between occupancy triggers and coverage diagnostics.

Neither may provide validation evidence for v3. In particular, no statement of the form
"v3 correctly classifies the two v2 windows" is a performance claim; those windows are
development examples, not targets, and v3 was not tuned to them.

## 4. What the development data was used for

Only to set the coverage-regime thresholds. The |trailing residual| distributions over the
spent v2 period:

| Diagnostic | median | p75 | p90 | p95 | max |
|---|---|---|---|---|---|
| `vessels_in_region` | 1.29 | 2.50 | 3.67 | 4.50 | 10.00 |
| `messages_per_vessel` | 1.19 | 1.94 | 2.99 | 3.85 | 6.46 |
| `region_cells` (spatial footprint) | 1.17 | 2.23 | 3.85 | 4.62 | 9.10 |

These fixed `V_SHIFT`, `M_ABRUPT`, `S_ABRUPT`, `M_STABLE` and `S_STABLE`. See
[HAMPTON_ROADS_DETECTOR_V3_PROTOCOL.md](HAMPTON_ROADS_DETECTOR_V3_PROTOCOL.md).

## 5. Window 1 stays unpromoted

The v2 trigger 2022-10-24..27 remains classified **`unknown`**. It looks like clean
accumulation — occupancy 13 → 14 → 15 → 17 against a baseline of 10 — and the day before it
was the third windiest in the period. Neither fact is sufficient. The wind observation was
made after the fact, from one station, with no documented restriction, inside a run that failed
its own validity gate. It does not become Event #3.
