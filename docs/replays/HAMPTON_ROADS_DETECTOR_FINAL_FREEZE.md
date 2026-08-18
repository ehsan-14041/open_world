# Hampton Roads measurement instrument — final freeze

> **Detector development is finished.** Detector v3 passed a genuinely fresh blind validation
> (`DETECTOR_V3_VALID`), and is now the final Hampton Roads measurement instrument.
>
> No parameter may change during Event #3 discovery. There is no Detector v4.
>
> From here on, the instrument is fixed and only the world is allowed to surprise us.

## 1. Semantic hashes

Over behaviour-changing parameters only — prose, comments and formatting excluded.

Two hashes, because two different things are being frozen and only one of them is the
instrument. Separating them means "the instrument did not change" stays verifiable even when a
search-protocol parameter is amended.

| Scope | Hash | Status |
|---|---|---|
| **Instrument** — occupancy detector, coverage-regime classifier, validity criteria, measurement rules | `b79b6909f48d384c661818eb1e390e1cabc41704798014fb17a8789b1c5ef472` | **frozen; must never change during discovery** |
| Search protocol — universe bounds, block structure, budget, recovery rules | `8ac1c174bb2839f89477258c3b9fe048…` | amended once before any detection; see universe doc §10 |
| Combined | `94ed22b2c19a876009e464f557cdd1f5…` | was `49ed3b935527f1fb…` before the budget amendment |

The combined hash moved **only** because `MAX_DISCOVERY_BLOCKS` moved from 8 to 11. The
instrument hash is byte-identical across that amendment, which is the claim that matters here.

Full parameter payload and amendment record: `data/external/ais/detector_v3_final_freeze.json`.

## 2. Component hashes

| Component | SHA-256 (first 16) |
|---|---|
| `event_sim/detect/detector_v2.py` (occupancy detector) | `3d2fa42f1ae17089` |
| `event_sim/detect/detector_v3.py` (coverage-regime classifier) | `8ba6b472df62cbde` |
| `event_sim/detect/series.py` (reconstruction) | `65412a51e93ab690` |
| `event_sim/detect/discovery.py` (search ordering) | `4658c289dbcfa456` |
| `event_sim/ingest/ais.py` (measurement rules) | `705bda4507e1b8f0` |
| `event_sim/ingest/cfr_anchorage.py` (geometry parsing) | `a139969441a5ca62` |
| `event_sim/historical/dataset_contract.py` (eligibility contract) | `84a2f8c3df296d0b` |
| `hampton_roads_110.168_2022-01-01.json` (geometry artifact) | `7baa46a782ede9dd` |

## 3. Frozen parameters

### Occupancy detector

| | |
|---|---|
| `LOOKBACK_DAYS` | 14 |
| `MIN_LOOKBACK_PRESENT` | 10 |
| `SCALE_FLOOR` | 1.0 |
| `RESIDUAL_THRESHOLD` | 3.0 |
| `PERSISTENCE_DAYS` | 4 |

### Coverage-regime classifier

| | |
|---|---|
| `V_SHIFT` | 3.5 |
| `M_ABRUPT` | 4.0 |
| `S_ABRUPT` | 4.5 |
| `M_STABLE` | 2.0 |
| `S_STABLE` | 2.5 |
| `WINDOW_REGIME_MIN_DAYS` | 2 (absolute days, never a share) |
| Severity order | `stable` < `gradual_shift` < `uncertain` < `abrupt_measurement_shift` |

### Measurement rules

| | |
|---|---|
| Geometry | 33 CFR 110.168, eCFR effective 2022-01-01 |
| Anchorages used | 10 commercial (F, G, H, I, J, K, M, N, Q, R) |
| Excluded | 4 Naval + 1 Commercial Explosives, by CFR designation |
| Region box | derived from geometry + 0.02° margin: 36.8227–37.3394, −76.4727 – −76.0633 |
| Vessel class | AIS `VesselType` 70–89 |
| Stationarity | SOG < 0.5 kts |
| Aggregation | distinct MMSI per calendar day |
| Footprint cell | 0.01° (~1.1 km) |
| Metric name | `anchorage_occupancy` — **never** `vessel_queue`; guard remains active |
| Observability class | `proxy_observable` |

### Uncertainty rules

`uncertain` when any coverage residual is undefined, or when the vessel count moved (≥ 3.5)
while report density or footprint is not clean enough to attribute it. A day with fewer than
10 present days in its lookback has an undefined residual and cannot trigger; an undefined day
breaks a trigger run rather than extending it.

### Event #3 eligibility contract

Unchanged, hash `84a2f8c3df296d0b`:

```
H1_SENSITIVE_METRICS = vessel_queue, waiting_vessels, average_waiting_time, anchorage_wait,
                       port_dwell_time, container_dwell_time, local_shipping_delay
DRIVER_METRICS       = throughput, arrivals, departures, port_capacity, berth_availability
OBSERVATION_TYPES    = observed, reported, derived, scheduled, estimated
FREQUENCY_RANK       = daily 3, weekly 2, monthly 1, irregular 0
```

## 4. Scientific history — preserved, not rewritten

| Detector | Verdict | Reason |
|---|---|---|
| v1 | `HAMPTON_ROADS_LOW_POWER` | Fixed-level threshold invalidated by severe nonstationarity; 94% of variance was between-window drift and the threshold of 29 exceeded the observed maximum of 26. |
| v2 | `DETECTOR_V2_COVERAGE_CONFOUNDED` | Occupancy detection generalised, but the coverage gate — a share over 2 windows, support {0, 0.5, 1.0} — failed exactly as registered at 0.50 against a `< 0.50` requirement. |
| v3 | `DETECTOR_V3_VALID` | All six criteria passed on a fresh 180-day period. Measurement environment interpretable (4.7% uncertain); stability margin narrow (14.12% abrupt against a 15% limit). |

All development and validation datasets are **spent** and may not serve as Event #3 discovery
evidence:

| Dataset | Days | Role |
|---|---|---|
| 2020-08-15 → 2022-05-21 (8 × 7-day windows) | 56 | `measurement_protocol_development_set_v1` |
| 2022-07-01 → 2022-12-27 | 180 | `detector_v2_blind_validation_spent` |
| 2023-02-01 → 2023-07-30 | 180 | `detector_v3_blind_validation_spent` |

## 5. What the instrument has demonstrated

The occupancy detector's parameters were derived once, from the v1 development set, and never
re-derived. Across three independent periods:

| Period | Median residual | Drift | Tail frequency (design target ~10%) |
|---|---|---|---|
| v2 blind, 2022 H2 | 0.0 | 0.33 | 9.4% |
| v3 blind, 2023 H1 | 0.0 | 0.50 | 11.2% |

Three eras, no re-derivation, the intended behaviour each time. That is the basis for treating
it as an instrument rather than a fit.
