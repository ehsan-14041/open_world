# Event Simulator — Architecture & Repository Audit

> **Status:** Phase A (audit) + Phase B (schemas) + Phase C (first vertical slice: major port
> disruption) + Phase D (minimal demo surface).
>
> **What this is:** an executable, evidence-tagged world model. Not a forecast, not a
> narrative generator. It answers *"how could this unfold under these explicit assumptions,
> and what would have to be different for the answer to change?"*
>
> **What this is not:** a predictor. The system never emits a probability of a future event.

---

## 0. Scientific framing (binding constraint on every layer below)

| Allowed | Forbidden |
|---|---|
| "Trajectory B appeared in 12 of 27 tested parameter worlds." | "There is a 44% probability of Trajectory B." |
| "Under central effect assumptions, service level falls to 0.71 by week 6." | "Service level will fall to 0.71." |
| "This edge is an expert assumption; no study is attached." | Citing a study that was not read. |

Two rules are enforced in code, not just prose:

1. **Every causal edge carries an `EvidenceStatus`.** There is no default that reads as
   "established". An edge with no evidence record cannot claim a status stronger than
   `expert_assumption`; `event_sim/evidence.py::validate_module` raises on violation.
2. **LLMs are not physics.** Nothing in `event_sim/` imports an LLM client. State transitions
   come from `event_sim/engine.py` only. An LLM may later *author a module file* (status
   `ai_hypothesis`) or *narrate a finished trace*; it can never compute a state.

---

## 1. Existing capability → proposed architecture

| Proposed layer | Existing OWE component | Verdict |
|---|---|---|
| Natural-language event → world | `core/text_to_scenario.py`, `pipeline/orchestrator.py`, `core/scenario_compiler.py` | **Do not touch (yet).** LLM-driven, scenario-shaped. The Event Simulator's first slice is hand-authored world modules; NL entry can front it later. |
| World Builder / World Slice | *(none)* | **New component.** `event_sim/world_builder.py` |
| Evidence layer | `schemas/provenance.py` (transition provenance only — no *epistemic* provenance) | **New component.** `event_sim/schemas.py` + `event_sim/evidence.py`. Different axis: existing provenance answers "what happened", new evidence answers "why do we believe the mechanism". |
| Causal world model (nodes/edges/**delays**) | `model/causal_graph.py` (`get_delay`, `get_decay`, `edge_model`), `core/propagation.py` | **Reusable as vocabulary; needs a new evolution rule.** `model/causal_graph.get_delay()` exists but **`core/propagation.py` ignores it** — propagation is same-turn, delta-driven, multi-hop-in-one-step. That is fine for the Ops decision product and wrong for a six-week cascade. See §3. |
| Actors / agents | `agents/`, `core/agent_constructor.py`, `epistemic/beliefs.py` | **Reuse later, not in slice 1.** Interface reserved (§6); no LLM calls added. |
| Simulation engine | `simulation/loop.py` (1927 lines: agents, governance, oracle, narrative, calibration) | **Not reused for the Event Simulator.** It is an *agent-arbitration* loop; the Event Simulator needs a *mechanism-evolution* loop. Reusing it would drag LLM/agent machinery into a layer that must stay deterministic. Both sit on the same state container and provenance schema. |
| World state container | `core/world_model.py::WorldModel` (`snapshot()` / `load_snapshot()`) | **Reused as-is.** Event Simulator holds a `WorldModel` with `causal_links=[]` so `apply_delta`'s same-turn propagation cannot double-count our lagged propagation. |
| Checkpoints / branching | `simulation/checkpoints.py::CheckpointStore` | **Reused as-is.** No second state-management mechanism. Branch = restore a checkpoint into a fresh engine. |
| Transition provenance | `schemas/provenance.py::TransitionProvenance`, `EffectRecord` | **Reused as-is**, extended by composition: `EffectRecord.params_or_delta` carries per-edge contributions and the edge's evidence status. No schema change → no risk to `simulation/loop.py`. |
| Event injection | `core/event_queue.py` (`{trigger_turn, event_type, params}`) | **Shape reused.** `EventDefinition.to_engine_events()` compiles to exactly that dict shape, so events are readable by both surfaces. Handler execution is the Event Simulator's own (needs multi-week duration + typed effects). |
| Bounds / units | `model/valuespec.py::clamp_state_to_specs` | **Reused as-is.** |
| Parameter sweeps | `simulation/ensemble.py`, `simulation/perturbation.py`, `simulation/monte_carlo_runner.py` | **Pattern reused, code not.** Existing sweeps jitter *initial conditions* with RNG per member. The Event Simulator sweeps *named uncertain assumptions* over a **deterministic grid** — every world is reproducible and attributable to a named assumption setting, which is what pivotal-assumption analysis requires. |
| Trajectory analysis | `simulation/robustness.py` (`_failure_modes`, `_pivotal_assumption`, `_divergence_point`) | **Concept reused, reimplemented deterministically.** Existing version clusters stochastic ensemble members; ours groups grid worlds by outcome rule and measures each axis's outcome span. |
| Ops Decision Simulator | `adapters/ops_scenario_builder.py`, `ui/ops_outcomes.py`, `ui/decision_brief.py`, `/`, `/api/brief` | **Do not touch.** Zero imports into it, zero imports from it. |

## 2. Reuse summary

**Reused unchanged:** `core/world_model.py`, `simulation/checkpoints.py`, `schemas/provenance.py`,
`model/valuespec.py`, `model/causal_graph.py` (delay/decay accessors), `core/event_queue.py` (dict shape),
`config/settings.py`.

**New (all additive, all under `event_sim/` + `world_models/`):** evidence & world-model schemas,
world-module registry, world builder, lag-aware evolution engine, causal trace, deterministic
assumption sweep, trajectory grouping, pivotal-assumption analysis, branch comparison,
historical-replay scaffolding, `/event-sim` demo surface.

**Modified:** `ui.py` — one blueprint registration and one entry in the engine-only path list.
Nothing on the `/` or `/api/brief` path changes.

**Technical debt that would block this direction (recorded, not fixed here):**

- `core/propagation.py` collapses multi-hop propagation into one turn and drops `delay`. Any
  future attempt to run *timed* cascades through the shared propagation function will silently
  lose lag. The Event Simulator therefore owns its own evolution rule rather than patching a
  function the Ops product depends on.
- `core/physics_core.py` applies a **default 1%/turn STOCK decay** to any variable ≤100 with no
  spec — a scale-dependent implicit trend. The Event Simulator requires every module variable to
  declare `dynamics` explicitly; there is no implicit decay.
- Determinism is global-RNG based (`random.seed`) and process-wide. The Event Simulator's core
  loop draws no randomness at all, so reproducibility does not depend on RNG discipline.
- `simulation/loop.py` mixes orchestration, LLM budgeting, narrative and calibration in one
  1900-line class. Not blocking, but it is why the Event Simulator did not extend it.

## 3. Why a new evolution rule (the one substantive engine addition)

Ops propagation (existing, correct for its job): a decision produces a delta; the delta fans out
along weighted edges **within a single turn**, damped by hop distance.

Event propagation (new): a shock displaces a variable from baseline and the system **relaxes over
weeks**, with each mechanism carrying its own lag.

The Event Simulator evolves *deviations from baseline*, not deltas:

```
dev(v, t)        = (value(v, t) − baseline(v)) / scale(v)
pressure(v, t)   = Σ  coef(e) · dev(source(e), t − lag(e))        over edges e → v
dev(v, t+1)      = dev(v, t) + response(v) · (pressure(v, t) − dev(v, t)) + injected(v, t)
value(v, t+1)    = clamp(baseline(v) + scale(v) · dev(v, t+1))
```

Properties that matter for the product claims:

- **Lag is real.** `lag(e)` weeks of history are read, so a 2-week edge cannot move its target
  this week. (test: `test_delayed_effects`)
- **Recovery is a consequence, not a script.** With the shock over, `pressure → 0` and
  `response(v)` pulls the variable back at its own rate. Recovery speed is therefore an
  *assumption axis*, not a hard-coded curve.
- **Every term is attributable.** `coef(e) · dev(source, t−lag)` is recorded per edge per turn,
  so the causal trace is read out of execution, never reconstructed afterwards.
- **`coef(e)` is drawn from the edge's evidence range** (`effect.low / central / high`) by a named
  assumption setting — the sweep axis and the evidence record are the same object.
- **Fully deterministic.** No RNG in the step function. Same slice + same config + same seed →
  byte-identical trajectory. (test: `test_deterministic_reproducibility`)

## 4. Schemas (Phase B)

Defined in `event_sim/schemas.py` (dataclasses, `from_dict`/`to_dict`, JSON-round-trippable —
matching the repo's existing plain-dict-over-the-wire convention):

| Schema | Purpose | Key fields |
|---|---|---|
| `Evidence` | one provenance record for a claim | `type`, `reference`, `year`, `note` |
| `EvidenceStatus` | 7-level epistemic ladder | `observed`, `empirical`, `literature_backed`, `historically_calibrated`, `expert_assumption`, `user_assumption`, `ai_hypothesis` |
| `EffectRange` | uncertain magnitude | `low`, `central`, `high` (+ `value_for(setting)`) |
| `Lag` | delay window | `min`, `max`, `unit` |
| `CausalEdgeEvidence` | one causal edge + its provenance | `source`, `target`, `polarity`, `effect`, `lag`, `evidence[]`, `geography[]`, `confidence`, `status`, `calibration` |
| `VariableDefinition` | one node | `id`, `unit`, `range`, `baseline`, `scale`, `dynamics.response`, `observability` |
| `WorldModule` | reusable domain slice | `id`, `domain`, `variables[]`, `edges[]`, `geography`, `version` |
| `WorldSlice` | what this run instantiates | `included_systems`, `excluded_systems`, `variables`, `edges`, `assumptions`, `missing_evidence`, `coverage` |
| `EventDefinition` | the injected shock | `id`, `targets[]`, `magnitude`, `start_turn`, `duration`, `shape`, `status` |
| `AssumptionAxis` | a named uncertain dimension | `id`, `settings[]`, `applies_to` |
| `WorldBranch` | a fork point | `branch_id`, `parent_id`, `fork_turn`, `interventions[]` |
| `Trajectory` | a grouped family of worlds | `label`, `member_configs[]`, `conditions`, `failure_points`, `critical_assumptions` |
| `HistoricalObservation` | ground truth for replay | `variable`, `turn`, `value`, `unit`, `source`, `status` |

## 5. First vertical slice — major port disruption

`world_models/supply_chain/port_disruption.json` — 8 variables, 9 edges, weekly resolution.

```
port_capacity ──(−, lag 0–1)──▶ shipping_delay ──(+, lag 1–2)──▶ inventory_availability (−)
      │                              │                                    │
      │                              └──(+, lag 0–1)──▶ freight_cost       ├──▶ service_level (+)
      │                                                     │             └──▶ production_capacity (+)
      └──(−, lag 1)──▶ order_backlog ◀──(−, lag 1)───────────┘                        │
                                                  freight_cost ──(+, lag 2–4)──▶ consumer_price_pressure
```

**Evidence honesty:** every edge in this module ships as `expert_assumption` with an empty
`evidence[]` list and an explicit `note`. No study, DOI, or coefficient was fabricated to make the
demo look authoritative. The evidence-coverage panel therefore reads **0% empirical /
0% literature-backed / 100% assumption** — that is the correct reading of a module whose numbers
have not been fitted, and it is exactly the signal the coverage feature exists to send. Attaching
real studies is a data task (`docs/DATA_REQUIREMENTS.md`), not a code task.

**Assumption axes swept:** `recovery_rate` (slow/central/fast), `alternative_capacity`
(none/partial/high), `demand_response` (low/central/high). 3×3×3 = 27 deterministic worlds.

**Intervention modelled:** `redirect_cargo` — restores a fraction of effective port capacity from
a chosen week, at a freight-cost premium. Applied by the engine, never by an agent directly.

## 6. Agentic layer (reserved, not built)

An actor is `{goal, beliefs, available_actions, constraints, observation, memory}` and returns an
**intervention id + parameters** — the same object a human clicks in the UI. `engine.apply_intervention()`
is the only mutation path; an actor cannot write a variable and cannot invent a coefficient. Slice 1
ships zero actors and zero LLM calls, per the non-goals.

## 7. Product-surface separation

```
Open World Engine
├── Operations Decision Simulator   /  ·  /api/brief  ·  /graph  ·  /journal      (untouched)
└── Event Simulator                 /event-sim  ·  /api/event_sim/*              (new blueprint)
```

Shared: `WorldModel`, `CheckpointStore`, `TransitionProvenance`, `valuespec`.
Not shared: scenario builders, outcome copy, UI, decision templates.
`/event-sim` is listed in `ui.py::_ENGINE_ONLY_PATHS`, so the enterprise product-mode SKU
(`OWE_PRODUCT_MODE=true`) does not expose it. The Ops product's behaviour is unchanged in both modes.

## 8. Historical replay (architecture only)

```
event_sim/historical/
    events/          # historical_events/*.json — event definitions with real dates
    observations/    # observations/*.json — HistoricalObservation series
    replay.py        # historical state → inject event → simulate → envelope
    evaluation.py    # coverage(), band_error(), directional_accuracy() vs observed
```

`replay.py` produces a **trajectory envelope** (min/max across swept worlds per variable per turn)
and `evaluation.py` scores observed series against it. Both directories ship **empty except for a
README and a schema**: no historical series was invented. `evaluation.py` refuses to score against
observations whose `status` is weaker than `observed`.

## 9. Test coverage (Phase C)

`tests/test_event_sim_*.py` — 10 required areas:
determinism · event injection · delayed effects · causal propagation · branch isolation ·
identical fork state · intervention comparison · provenance preservation · evidence-status
propagation · Ops-product regression (existing `tests/test_ops_brief_e2e.py` + an explicit
no-interference test).

## 10. Does this beat asking an LLM the same question?

| Capability | LLM answer | Event Simulator |
|---|---|---|
| Persistent state over 12 weeks | narrated, not held | held, inspectable per week |
| Same question twice | drifts | byte-identical |
| "Which assumption decides the answer?" | plausible guess | measured outcome span per axis |
| "Show the same world with and without the intervention" | two independent stories | one checkpoint, two forward runs, diffed |
| "Why did service level fall?" | post-hoc rationalisation | recorded per-edge contributions |
| "How much of this is evidence?" | unanswerable | counted by status |

Where the answer would have been "no", the feature was not built (no vector DB, no clustering
library, no ML, no agents in slice 1, no LLM in the physics path).
