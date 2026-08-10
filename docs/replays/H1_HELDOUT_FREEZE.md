# H1 held-out freeze — snapshot taken BEFORE Event #3 was searched for

> **Purpose.** A held-out test is only held out if the model provably predates the data.
> This file records the exact semantic state of the baseline and H1 experimental models, and
> of the evaluation code, at a moment when **no Event #3 candidate had been searched for,
> named, or inspected**. Everything after this point can be checked against it.
>
> Written at `2026-08-09T18:38:17Z`, repository at `0f5ea45` plus the uncommitted Event
> Simulator working tree.

## 1. Frozen semantic hashes

| Artefact | SHA-256 |
|---|---|
| `port_disruption` (baseline module) | `d4670fb108c2e9a3c45d33455a652578e7a72bfce69f88ed44c6b355ead13f5b` |
| `port_disruption_h1_queue_experimental` | `324a8bf1d67d56ad082b9c7540f7d155466af50ad71359c1b4836ef79f8f3889` |
| Evaluation + engine code | `880d2d0ef0cc0e3d32ea6f7b1464248a825225cdb1f2445cd372ce2f9239f992` |

Code files covered by the third hash:

```
event_sim/engine.py
event_sim/sweep.py
event_sim/historical/evaluation.py
event_sim/historical/replay.py
```

The module hash is **semantic**, not file-level: it covers every field that changes
behaviour (baselines, scales, ranges, responses, `kind`, stock rules, edge polarities,
effect ranges, lags, `mechanism_type`, axis settings and mappings, intervention effects) and
deliberately excludes prose fields. Documentation may improve; dynamics may not move without
the hash moving. Computed by `event_sim/freeze.py::snapshot()`.

## 2. What is frozen, in words

### Baseline — `port_disruption`

8 variables, 9 edges, 3 assumption axes. Every variable is `kind="relaxation"`; there are no
stocks. The nine edges, with polarity / effect range / lag in weeks:

| Edge | Polarity | Effect (low/central/high) | Lag |
|---|---|---|---|
| `port_capacity → shipping_delay` | negative | 0.6 / 0.9 / 1.3 | 0–1 |
| `port_capacity → order_backlog` | negative | 0.4 / 0.65 / 0.95 | 1–1 |
| `order_backlog → shipping_delay` | positive | 0.1 / 0.2 / 0.35 | 1–2 |
| `shipping_delay → freight_cost` | positive | 0.25 / 0.45 / 0.7 | 0–1 |
| `shipping_delay → inventory_availability` | negative | 0.3 / 0.5 / 0.75 | 1–2 |
| `inventory_availability → service_level` | positive | 0.4 / 0.65 / 0.9 | 0–1 |
| `inventory_availability → production_capacity` | positive | 0.25 / 0.45 / 0.7 | 1–2 |
| `production_capacity → service_level` | positive | 0.15 / 0.3 / 0.5 | 1–2 |
| `freight_cost → consumer_price_pressure` | positive | 0.1 / 0.2 / 0.35 | 2–4 |

Variable dynamics (baseline / scale / response): `port_capacity` 100 / 100 / 0.55 ·
`shipping_delay` 4.0 / 10 / 0.5 · `freight_cost` 100 / 100 / 0.35 · `order_backlog`
100 / 100 / 0.4 · `inventory_availability` 100 / 100 / 0.3 · `production_capacity`
100 / 100 / 0.35 · `service_level` 0.95 / 0.5 / 0.45 · `consumer_price_pressure`
100 / 100 / 0.2.

### H1 experimental — `port_disruption_h1_queue_experimental`

Identical to the baseline except:

- **Added** `vessel_queue`, `kind="stock"`, unit *normal-flow-weeks of unprocessed
  arrivals*, baseline 0.0, scale 1.0, range [0, 60].
- **Replaced** `port_capacity → shipping_delay` with
  `port_capacity → vessel_queue` (`mechanism_type="conservation"`, effect 1.0/1.0/1.0, lag 0)
  and `vessel_queue → shipping_delay` (linear, effect 0.08 / 0.15 / 0.25, lag 0–1, bound to
  the existing `alternative_capacity` axis).
- **Added** axis `queue_clearance` with surge multipliers slow 1.05 / central 1.15 / fast 1.35.

### The frozen queue conservation rule

```
processed(t)           = min( queue(t) + arrivals(t), processing_capacity(t) )
queue(t+1)             = max( 0, queue(t) + arrivals(t) − processed(t) )
processing_capacity(t) = ( port_capacity(t) / 100 ) × surge
arrivals(t)            = 1.0                      (definitional; steady state ⇒ queue = 0)
```

### The frozen queue → shipping_delay mapping

Linear, in deviation space, with the standard engine propagation:
`contribution = coefficient × deviation(vessel_queue, t − lag)`, where
`deviation = (value − baseline) / scale = value / 1.0`, coefficient from the effect range
selected by the `alternative_capacity` axis setting, lag from the 0–1 window.

### Frozen normalisation

`deviation(v) = (value(v) − baseline(v)) / scale(v)` for every variable; bounds enforced by
`model.valuespec.clamp_state_to_specs`; clamping folded back into deviation space; exogenous
intervention offsets held out of the endogenous state so they cannot ratchet.

## 3. H1 parameters as frozen

| Parameter | Value / range | Status |
|---|---|---|
| `inflow` (arrivals) | 1.0, fixed | definitional |
| `queue_clearance` surge | 1.05 / 1.15 / 1.35 | `expert_assumption`, swept |
| `vessel_queue → shipping_delay` effect | 0.08 / 0.15 / 0.25 | `expert_assumption`, swept |

## 4. Prior evidence, all predating this freeze

| Stage | Evidence | Used data |
|---|---|---|
| Mechanism support | [H1_QUEUE_MECHANISM.md](H1_QUEUE_MECHANISM.md) | San Pedro Bay at-anchor counts, Jun–Oct 2021 |
| In-sample experiment | [H1_EXPERIMENT_RESULTS.md](H1_EXPERIMENT_RESULTS.md) | Yantian 2021, Baltimore 2024 |

**Any Event #3 candidate drawing on San Pedro Bay 2021–22, Yantian 2021 or Baltimore 2024 is
disqualified as non-independent**, because those data shaped H1's formulation, its parameter
ranges, or its prior evaluation.

## 5. The rule this file exists to enforce

After this snapshot, **no H1 parameter, coefficient, lag, mapping, normalisation or topology
may change before the held-out evaluation is complete and reported.** If the held-out test
fails because one of them is wrong, the failure is recorded; the repair becomes a new
hypothesis requiring its own future held-out event.

Enforced by `tests/test_event_sim_heldout.py::TestFreezeHolds`, which recomputes these
hashes and fails on any drift.

## 6. What was *not* known when this was written

At the moment of this snapshot no Event #3 candidate had been searched for, named, or
inspected. The eligibility contract in
[EVENT3_ELIGIBILITY_CONTRACT.md](EVENT3_ELIGIBILITY_CONTRACT.md) was written next, also
before searching, so candidate selection could not be steered by H1's performance.
