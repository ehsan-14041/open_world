# Open World Engine 2 — Architecture

This document describes the core architecture of the **open_world_engine2** project: causal variable graph, belief state, rule engine, event queue, action contract, trace, and narrative flow.

## World state (causal variable graph)

- **variables**: `dict[str, float]` — primary store for numeric state (replaces flat global_state conceptually; snapshot still exposes `global_state` as alias for backward compatibility).
- **causal_links**: `list[{ "from": str, "to": str, "weight": float }]` — when a variable changes, deltas propagate along links: `delta_target += delta_source * weight`. Capped iterations avoid infinite loops.
- **entities**, **relations**, **narrative**, **ontology**, **version**, **turn**, **delayed_events**, **events** — unchanged or extended as below.

Propagation is implemented in `core/propagation.py` and invoked from `WorldModel.apply_delta()` after applying direct numeric updates. The V2 generalized engine provides `dynamics/propagation.py` with edge_model adapters for optional use.

**Canonical cloning:** All world-state cloning uses `world/world_state.py`: `clone_world_state(snapshot, include_causal_links=False|True)` for planning (no causal_links) or full snapshot; `clone_snapshot(snapshot)` for a full copy. The planner delegates to this module; no other deep copies of world state.

## Agent belief state

- Each agent has **beliefs**: `{ "variables": dict[str, float], "confidence": dict[str, float] }`. Agents observe the real world through a **noisy filter** (`core/observation.py`: `observed_value = real_value + small_noise`). Beliefs are updated over time (e.g. exponential moving average). **Decisions use beliefs, not real world state**: in `propose()`, a belief snapshot (same shape as world snapshot but with variables from `agent.beliefs["variables"]`) is passed to goal evaluation, candidate generation, and planning.
- **Advanced belief layer (optional):** When `ENABLE_BELIEF_LAYER` is true, `agents/belief_model.py` provides **BeliefState** (beliefs, uncertainty per key, global confidence), Bayesian-lite updates (`update_belief_state`), belief–action alignment scoring (`belief_alignment`), and shock impact on uncertainty (`shock_impact_on_belief_variance`). The simulation loop updates agent belief state after each turn; dashboard payload can include `belief_alignment` (entropy, dominant_belief, divergence_index).

## Action evaluation (MC + RL)

- When **MC_RL_ENABLED** is true, agents choose actions via a hybrid path in `agents/action_evaluation.py`: **planner scores** (one apply + utility per candidate), **Monte Carlo evaluation** (average utility over `n_sims` shallow sims per action), and **RL weights** per action are combined with softmax selection (configurable temperature). This preserves exploration; when disabled, the engine falls back to argmax planning (`plan_depth2` or `plan_depth2_with_callback`). **Mental simulation:** When the scenario has `causal_links`, the planner uses `core/mental_simulation.run_mental_simulation()` for apply-delta (Unified Physics): deterministic propagation with bounded hops and decay, no noise—so planner outcomes align with execution propagation. Without causal_links, `apply_delta_to_state()` is used. All evaluation uses the canonical `world/world_state.clone_world_state()`; diversity is optionally preserved via `core/synthesizer.ensure_action_diversity()`.

## Generic rule engine

- **Scenario-defined, domain-agnostic** rules: scenario lists `rules: [{ "id", "condition_key", "effect_key", "params" }]`. Core holds a **registry** (`core/rule_engine.py`): condition_key → `(snapshot) -> bool`, effect_key → `(world, params) -> delta | None`. No domain logic in core—only “evaluate condition” and “run effect”. Rules are evaluated after each turn; activations are recorded for the trace.

## Event queue

- **Unified event handling**: `WorldModel.events` holds scenario-defined events `{ "trigger_turn", "event_type", "params", "origin", "metadata" }`. At each turn, `process_delayed_events()` runs both (1) legacy **delayed_events** (apply_delta at trigger_turn) and (2) **events** via an event_type handler registry (`core/event_queue.py`). No domain logic in core—only “at trigger_turn run handler for event_type with params”.

## Agent action contract

- Agents may propose **abstract actions** via **action_spec**: e.g. `{ "type": "increase_variable", "target": "trust", "magnitude": 5 }`. The **core action interpreter** (`core/action_interpreter.py`) maps these to a Delta generically (increase_variable, decrease_variable, set_variable). No hardcoded domain variable names in core. Legacy proposals (action_type string) still go through WorldModelAgent normalizer.

## Simulation trace and narrative

- Each step appends to **trace** (provenance): `turn`, `actions` (proposals), `variable_changes` (from apply_delta + propagation), `events_triggered`, `rule_activations`. At the end of a run, the **narrative builder** (`core/narrative_builder.py`) uses `core/narrative_synthesizer.py` for structural phases, **core/narrative_templates.py** for domain-agnostic directional templates (relational, state_transition, trajectory), and the **summarization/** package for the two-layer narrative firewall: Layer 1 = deterministic NarrativeFacts from trace/snapshots (`summarization/facts.py`); Layer 2 = deterministic renderer or optional LLM narrator (`summarization/renderer.py`, `summarization/llm_narrator.py`). Narrative emerges from the simulation trace, not fallback boilerplate.

## Backward compatibility

- If a scenario omits **causal_links**, **rules**, or **events**, the engine uses empty lists; behavior is unchanged for existing scenarios.
- Snapshot always exposes both **variables** and **global_state** (alias); **load_snapshot** and WorldModel **__init__** accept either. CLI and UI remain unchanged.

---

## V2 Engine (Generalized)

The v2 refactor adds domain-agnostic data models, a strict turn pipeline, and full traceability. Existing entrypoints and scenarios remain supported.

### Module responsibilities

| Module | Responsibility |
|--------|----------------|
| **model/valuespec.py** | ValueSpec schema (numeric/ordinal/categorical/text), clamp, to_scalar_for_utility, unknowns |
| **model/causal_graph.py** | Structural causal links only (from, to, edge_model); no action logs |
| **model/state.py** | Versioned snapshots, world_state vs belief_state shapes |
| **policy/action_dsl.py** | Universal DSL: intervene, allocate, communicate, probe, modify_constraint, create_relation, dissolve_relation, noop → delta_raw |
| **dynamics/propagation.py** | Deterministic propagation with edge_model adapters (linear, logistic, etc.), delay/decay |
| **governance/constraints.py** | Hard/soft constraints; ValueSpec adapter for variable_specs |
| **trace_log/action_trace.py** | action_trace[] (turn, agent_id, action, delta_raw, delta_applied); never in causal_links |
| **epistemic/beliefs.py** | Belief update with ValueSpec (distributions/intervals), observe_and_update_beliefs |
| **learning/adaptive_kernel.py** | Strategy weight update f(…); bounded; objectives never overwritten |
| **shocks/shock_engine.py** | Optional shock sampling; disabled ⇒ deterministic (with seed) |
| **simulation/shock_engine.py** | Shock-driven global mode: macro shocks (supply_chain, financial, political, information_warfare); probabilistically applied when `SIMULATION_MODE=shock_global`; impact_delta on world.variables; provenance records `shock` for dashboard |
| **summarization/** | facts.py (NarrativeFacts from trace/snapshot), lang.py (opening phrase, detect), bucketing.py, renderer.py, validators.py, llm_narrator.py; narrative.py token substitution, lang re-export |

### Turn pipeline (deterministic order)

1. Collect delta_raw from agent actions (DSL or legacy interpreter).
2. Propagate structurally through causal_graph (delay/decay + edge_model).
3. Apply constraints (hard clamps, soft penalties).
4. Merge deltas deterministically (explicit rule; no silent overwrite).
5. Apply delayed effects due this turn.
6. Clamp using ValueSpec.clamp.
7. Commit versioned world_state snapshot.
8. Observe → agent observations (visibility + optional noise).
9. Update belief_state per agent; agents act on belief_state only.
10. Diagnostics/stagnation (optional).

### Scenario pipeline (text → JSON)

When scenario text is provided, the **pipeline** (`pipeline/orchestrator.py`) runs: Entity Extraction → Variable Discovery → Causal Graph → Incentive Modeling → Incentive Validation (`objective_validator`) → Action Discovery → JSON. Stages raise `pipeline.errors.PipelineError` on failure. See `docs/SYSTEM_GUIDE.md` for details.

### Scenario analysis output

After a run, `core/scenario_analysis_output.py` produces Logic Core (JSON), Executive Summary, and Strategic Analysis envelope (`build_strategic_analysis()`) using `attribution_layer`, `delta_aggregation`, and `convergence_analysis`. Provenance includes `predicted_deltas` (from agents' planning) for strategic analysis.

### Live Enterprise Dashboard and payload

- **core/dashboard_payload.py:** Builds a single JSON payload from snapshot, provenance entry, scenario, and optional provenance history: `state_snapshot`, `risk_report` (from `core/risk_assessment.py`), `calibration_metrics` (prediction_vs_realized, rmse_over_time, overconfidence_flags, health), `selected_action`, `explanation`, `assumption_summary`, `edition`, optional `belief_alignment` (when belief layer enabled), `shock` (when shock active), and optional `oracle_analysis` (when `ENABLE_ORACLE`). No simulation imports; used by the Live Dashboard.
- **core/oracle.py:** LLM Advisor (Oracle) layer: advisory-only analysis of proposed actions. `summarize_history_for_oracle(provenance_history, last_n, max_chars)` builds a short text summary of recent turns (no LLM). `analyze_action(...)` returns JSON with Action, Confidence (0–100), Risk Factors, Alternative Scenarios, optional Hidden Variables, Prediction Failure Reasons, and optional **causal_learning_suggestion** (`{source, target, polarity, strength_estimate}`) for belief-graph updates. Does not modify simulation state. Enabled via `ENABLE_ORACLE`; `ORACLE_HISTORY_TURNS`, `ORACLE_MAX_TOKENS` in config.
- **core/mental_simulation.py:** Light mental simulation for the planner: `apply_delta_light()` and `run_mental_simulation()` apply delta with deterministic propagation (same damping/decay/significance as `core/propagation`), bounded hops (`LIGHT_PROP_HOPS`), no noise. Used by `agents/planner.apply_delta_to_state_or_mental_simulation()` when `causal_links` exist.
- **core/surprise_analysis.py:** `run_surprise_analysis(predicted_delta_light, actual_outcome, deviation_threshold)` compares predicted vs actual variable changes; returns `triggered`, `deviation_by_var`, `message`. Stored in provenance as `surprise_analysis`; used for self-correction and logging when deviation exceeds `DEVIATION_THRESHOLD`.
- **core/synthesizer.py:** `ensure_action_diversity(candidates, scores, min_size)` keeps at least `min_size` options by score to avoid over-conservative single action; `expected_utility(reward_potential, P_success, tail_risk, P_failure)` for EU. Used in `agents/base_agent` for candidate filtering.
- **core/causal_learning.py:** `suggest_causal_link_from_trace(provenance_history, min_occurrences)` suggests a causal link from recurring co-change patterns; `apply_belief_drift(edge_confidence, suggestion, rate)` updates edge confidence by `BELIEF_DRIFT_RATE`. Optional input to Oracle and belief graph.
- **core/trace_compression.py:** `compress_trace_to_causal_chain(raw_logs, slm_callback, max_events)` compresses provenance into a Causal Event Chain (`turn`, `cause_var`, `effect_var`, `direction`, `magnitude`) for long-trace analysis; optional SLM summarization.
- **core/calibration.py:** Recalibration trigger (periodic or drift) via `check_recalibration_trigger()`; `apply_recalibration_action()` returns `calibration_event` for provenance/dashboard.
- **core/risk_assessment.py:** `agent_behavior_summary()`, `next_turn_risk_score()`, optional `tail_risk_from_mc()`; feeds dashboard `risk_report`.
- **core/rule_learner.py:** Offline `suggest_rule_updates(history)` for governance strictness/rules; output for human review only.
- **core/simulation_mode.py:** Runtime state for `simulation_mode`, `enable_shocks`, `enable_uncertainty`; get/set API without restart.
- **simulation/checkpoints.py:** `CheckpointStore` for rollback; `rollback_to_turn()`, `rollback_last_step()` when `CHECKPOINT_ENABLED`.
- **ui/dashboard.py:** In-memory buffer of payloads (`DASHBOARD_HISTORY_SIZE`), `on_turn_complete(payload)` called from simulation loop; routes `/dashboard`, `/api/dashboard/config`, `/api/dashboard/latest`, `/api/dashboard/history`, `/api/dashboard/events` (SSE), `/api/dashboard/research_draft` (markdown download). Enabled via `DASHBOARD_ENABLED`.
- **enterprise/positioning.py:** Tier labels (Research Edition, Enterprise Core, Enterprise Pro, Government) and per-tier `feature_flags` (belief_layer, shock_global, research_export), `dashboard_modules_enabled`, `simulation_horizon`, `calibration_depth`. No billing; positioning only. `ENTERPRISE_TIER` in config/settings.
- **research/paper_draft.py:** `generate_research_draft(simulation_history, config)` produces structured markdown (Abstract, Methodology, Model Architecture, Belief Modeling, Calibration & Risk, Results, Limitations, Future Work) from provenance; no LLM.

### Extension points

- **Edge models:** linear, logistic, ordinal_shift, categorical_influence, custom (in causal link edge_model).
- **Observation/noise:** core/observation.py; epistemic/beliefs.py for ValueSpec-aware update.
- **Shocks:** shocks/shock_engine.py; simulation/shock_engine.py when `SIMULATION_MODE=shock_global`; enable_shocks / SIMULATION_MODE config; seed plumbed.
- **Learning:** learning/adaptive_kernel.py; strategy_weights only; objectives fixed.

### Invariants

- **Domain-agnostic:** No hardcoded domain action lists or variable names; actions discovered from scenario.
- **causal_links structural only:** No action/turn logs in causal_links; action trace in trace_log.
- **Beliefs vs world_state:** Decisions use belief snapshot; world_state for application and summarization.
- **Traceability:** action_trace per run; self_effect vs world_delta attribution; no silent merges.

### Language handling (presentation only)

- **Language does not affect engine semantics:** Variable discovery, action discovery, governance, propagation, causal graph, scoring, shocks, and state updates are independent of language. Language is applied only in summarization/formatting (opening phrase, prose language). Engine-core modules (simulation, model, dynamics, governance, policy, pipeline) do not import summarization or summarization.lang.
- **lang:** Config default `"auto"`; resolved from scenario (summarization.lang.detect_narrative_language_from_scenario).
- **Narrative:** Same structure for fa and en; first sentence must start with "در آغاز" when lang==fa, "At the beginning" when en.
- **Narrative Firewall:** Layer 1 = deterministic fact extraction from run snapshots/turn_records → NarrativeFacts; Layer 2 = weaving from NarrativeFacts only (deterministic renderer or optional LLM). No raw trace or state dumps to the narrator.
