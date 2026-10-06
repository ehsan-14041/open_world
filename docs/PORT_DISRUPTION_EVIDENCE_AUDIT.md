# Port Disruption model — evidence audit

**Scope:** the nine causal edges in `world_models/supply_chain/port_disruption.json`.
**Status when this audit was written:** all nine edges `expert_assumption`, zero evidence
records attached, zero historical observations in the repository.
**Rule followed:** no coefficient, lag or polarity was modified while producing this audit.

This document answers one question per edge: *can this parameter be grounded, and how?*

---

## 1. Method

For each edge the audit asks four separable questions:

1. **Estimable from public data?** Does a public time series exist for *both* endpoints, at
   compatible frequency and geography, long enough to fit a lagged relationship?
2. **Constrainable from literature?** Is there a body of published work that bounds the
   effect size or the lag, even if we cannot fit it locally?
3. **Validatable by historical replay?** Would a replay of a real disruption move this edge's
   target observably, so that replay could reject or calibrate it?
4. **Recommended treatment** — one of:

| Treatment | Meaning | Target status |
|---|---|---|
| `data-fit candidate` | public series exist for both endpoints; fit locally | `empirical` |
| `literature-constrained candidate` | published work bounds the range; no local fit | `literature_backed` |
| `historical-calibration candidate` | replay of a real event can constrain it | `historically_calibrated` |
| `customer-data-only` | only a firm's own operational export could ground it | stays `expert_assumption` |

An edge can be a candidate for more than one treatment. **Candidate ≠ promoted:** an edge is
promoted only when the evidence actually arrives and passes
`event_sim/evidence/registry.py` validation.

## 2. The nine edges

| # | Edge | Polarity | Effect (low/central/high) | Lag (wk) | Status | Evidence attached | Public data? | Literature? | Replay can test? | Recommended treatment |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `port_capacity → shipping_delay` | negative | 0.6 / 0.9 / 1.3 | 0–1 | expert_assumption | none | **Partly** — port throughput + schedule reliability/delay series exist, but at different geographies (port-level vs global) and frequencies (weekly vs monthly) | Port congestion/queueing literature bounds the mechanism, not this normalisation | **Yes** — the highest-signal edge in a port disruption | historical-calibration candidate (primary), data-fit candidate (secondary) |
| 2 | `port_capacity → order_backlog` | negative | 0.4 / 0.65 / 0.95 | 1 | expert_assumption | none | **Partly** — backlog proxies (TEU awaiting pickup, ships at anchor) are reported as point estimates, rarely as series | Queueing theory constrains the *shape*, not the index normalisation | **Weakly** — observations are sparse point estimates | historical-calibration candidate (weak) |
| 3 | `order_backlog → shipping_delay` | positive | 0.1 / 0.2 / 0.35 | 1–2 | expert_assumption | none | **No** — requires a backlog series and a delay series at the same port | Congestion-feedback literature supports the sign | **No** — not separately identifiable from edge 1 in a single event (both driven by the same shock) | leave as assumption; document non-identifiability |
| 4 | `shipping_delay → freight_cost` | positive | 0.25 / 0.45 / 0.7 | 0–1 | expert_assumption | none | **Yes in principle** — freight indices (Drewry WCI, Freightos FBX) are weekly and widely reported; full historical series are commercial | Freight-rate formation literature exists | **Yes**, if a weekly freight series can be assembled | data-fit candidate (blocked on series access), historical-calibration candidate |
| 5 | `shipping_delay → inventory_availability` | negative | 0.3 / 0.5 / 0.75 | 1–2 | expert_assumption | none | **No** — no public dataset carries firm inventory cover alongside transit delay. This repository already established this (see `docs/FITTING_FINDINGS.md`: no public dataset jointly contains inventory + demand + lead time + fill rate) | Inventory-theory literature relates lead-time variability to required cover; it bounds the *direction and rough magnitude*, not this index mapping | **No** — no observable public counterpart | customer-data-only |
| 6 | `inventory_availability → service_level` | positive | 0.4 / 0.65 / 0.9 | 0–1 | expert_assumption | none | **No** — fill rate is an internal metric | **Yes, partially** — the stock-cover-to-fill-rate relationship is standard inventory theory | **No** | literature-constrained candidate, then customer-data-only for the coefficient |
| 7 | `inventory_availability → production_capacity` | positive | 0.25 / 0.45 / 0.7 | 1–2 | expert_assumption | none | **Weakly** — industrial production indices are public, component stock cover is not | Some empirical work on supply disruption and output | **Weakly** — confounded by everything else in the economy | customer-data-only |
| 8 | `production_capacity → service_level` | positive | 0.15 / 0.3 / 0.5 | 1–2 | expert_assumption | none | **No** — both endpoints internal | Thin | **No** | customer-data-only |
| 9 | `freight_cost → consumer_price_pressure` | positive | 0.1 / 0.2 / 0.35 | 2–4 | expert_assumption | none | **Yes** — freight indices and CPI are both public | **Yes** — freight-rate pass-through to consumer prices is an established macroeconomic research question | **No** at this slice's resolution — the pass-through horizon (quarters) exceeds the replay window (weeks) | literature-constrained candidate |

## 3. What this tells us

**The model splits cleanly into two halves, and only one half is groundable in public data.**

```
GROUNDABLE HALF (upstream, physical, publicly observed)
    port_capacity → shipping_delay → freight_cost
    port_capacity → order_backlog
        ↑ port throughput, congestion, schedule reliability, freight indices are published

NOT GROUNDABLE IN PUBLIC DATA (downstream, firm-internal)
    shipping_delay → inventory_availability → service_level
                                            → production_capacity → service_level
        ↑ inventory cover, fill rate and plant output are internal metrics
```

This is the *same wall* the Operations product hit (`docs/FITTING_FINDINGS.md`: "No public
dataset jointly contains the full causal structure"). It is a structural feature of the
domain, not a search failure, and it has a direct product consequence: **the downstream half
of the model can only ever be grounded by a customer's own data.** That is a commercial
argument for consultant-assisted onboarding, and it is stated in the evidence-gap report the
simulator now produces.

**Edge 3 is not separately identifiable in a single-event replay.** `order_backlog` and
`shipping_delay` are both driven by `port_capacity` in the same window, so one event cannot
attribute movement between them. It stays an assumption, and the calibration code refuses to
touch it rather than fitting an unidentifiable parameter.

**Only edges 1, 2 and 4 are reachable by the first historical replay.** Everything else needs
either literature work (6, 9) or customer data (5, 7, 8).

## 4. Frequency and geography mismatch (the binding constraint)

| Quantity | Best public source found | Frequency | Geography |
|---|---|---|---|
| Port throughput / operating capacity | carrier advisories, port authority statements, press | irregular, event-driven | port-specific |
| Vessel delay | Sea-Intelligence Global Liner Performance press releases | **monthly** | **global aggregate** |
| Freight cost | Drewry WCI / Freightos FBX | weekly | lane or global composite |
| Backlog | press point estimates (TEU awaiting pickup, ships at anchor) | irregular | port-specific |

The simulation runs **weekly** and models **one port**. The best delay series available is
**monthly** and **global**. That mismatch is the single most important limitation of the
first replay, and it is recorded as a `proxy` mapping with an explicit `limitations` field
rather than silently resampled.

## 5. Recommended treatment summary

| Treatment | Edges | Count |
|---|---|---|
| historical-calibration candidate | 1, 2, 4 | 3 |
| data-fit candidate (blocked on series access) | 4 | 1 |
| literature-constrained candidate | 6, 9 | 2 |
| customer-data-only | 5, 7, 8 | 3 |
| leave as assumption (non-identifiable) | 3 | 1 |

**Expected best case after this task: 3 of 9 edges reachable, 6 of 9 unavoidably assumptions.**
That is the honest ceiling for a public-data-only grounding effort on this model, and it is
what the evidence-coverage panel should report afterwards.

## 6. What was explicitly *not* done

- No coefficient, lag or polarity was changed while writing this audit.
- No edge was promoted above `expert_assumption` in anticipation of evidence.
- No source was cited that was not actually retrieved and read.
- No dataset was assumed to exist because it "should".
