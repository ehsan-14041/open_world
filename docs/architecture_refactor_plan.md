# Architecture Refactor Plan

This document summarizes the current state, target architecture, Phase 1 scope, and Phase 2 scope (completed) plus Phase 3+ preview.

## 1. Current state (pre–Phase 1)

### Engine core modules

- **Core:** `core/world_model.py`, `core/propagation.py`, `core/physics_core.py`, `core/governance.py`, `core/event_queue.py`, `core/rule_engine.py`, `core/action_interpreter.py`, `core/soft_constraints.py`, `core/world_state.py`, `core/mental_simulation.py`, `core/delta_aggregation.py`, `core/delta_attribution.py`, `core/action_definitions_store.py`, plus narrative, calibration, risk, and oracle modules.
- **Model:** `model/state.py` (snapshot helpers), `model/valuespec.py` (ValueSpec + legacy adapter), `model/causal_graph.py`.
- **Simulation:** `simulation/loop.py` (main loop), checkpoints, monte_carlo_runner, shock_engine.
- **Agents:** `agents/base_agent.py`, `agents/planner.py`, `agents/utility.py`, `agents/world_model_agent.py`.
- **World:** `world/world_state.py` — canonical `clone_world_state` / `clone_snapshot`.
- **Schemas:** `schemas/delta_schema.py`, `schemas/proposal_schema.py`, `schemas/llm_action_schema.py`, `schemas/scenario_schema.py`, `schemas/contracts.py` (Phase 1).

### Top architectural issues addressed in Phase 1

1. **Semantic hardcoding:** Non-negative and protected variable inference from variable names; steady action and strategy-from-name in agents; goal/direction from prefixes in utility and narrative_engine.
2. **Product/UI leakage:** Dashboard payload builder lived in core; calibration logic depended on it; loop imported it directly.
3. **Missing canonical contracts:** No typed SimulationSpec, State, ActionSpec, EventSpec, ConstraintSpec, TraceEntry, or TransitionResult.
4. **Duplicate/competing abstractions:** Multiple apply_delta paths, clone_snapshot in two places (Phase 2).

## 2. Target architecture

- **Canonical contracts:** All core boundaries use typed models (see `docs/engine_contracts.md`). Legacy dicts supported via adapters.
- **Declarative metadata:** Variable-level constraints from `variable_specs` or ValueSpec; legacy name-based inference isolated in `core/legacy_semantics.py`.
- **Boundaries:** Engine core has no dependency on UI/dashboard. Calibration metrics in `core/calibration_metrics.py`. Dashboard payload in `ui/dashboard_payload.py`. Loop accepts optional `build_turn_payload` callback.
- **No new domain keywords in core:** All name-based behavior in `legacy_semantics`.

## 3. Phase 1 scope (completed)

- **Contracts:** `schemas/contracts.py` with SimulationSpec, State, ActionSpec, EventSpec, ConstraintSpec, TraceEntry, TransitionResult and adapters.
- **Legacy semantics:** `core/legacy_semantics.py`; core and agents call into it.
- **Declarative preference:** llm_action_guard and governance prefer variable_specs/ConstraintSpec; fall back to legacy. Loop attaches variable_specs to world for governance.
- **Dashboard boundary:** `compute_calibration_from_provenance` in `core/calibration_metrics.py`. Payload builder in `ui/dashboard_payload.py`. Loop uses optional `build_turn_payload` callback.
- **Documentation:** This file, `docs/engine_contracts.md`, `docs/migration_notes.md`.
- **Tests:** `tests/test_contracts.py` plus synthetic variable and name-assumption tests.

## 4. Phase 2 scope (completed)

- **Shared transition kernel:** `core/transition_kernel.py` with `TransitionOptions`, `apply_core`, `transition_planning`, and `transition_execution`.
- **Planning/execution alignment:** `agents/planner.py` routes `_apply_delta_for_planning` through `transition_planning` so depth-2 planning uses the same deterministic physics as execution (via `physics_core.apply_delta_deterministic`).
- **Typed transition provenance:** `schemas/provenance.py` defines `EffectRecord` and `TransitionProvenance`. `simulation/loop.py` calls `transition_execution` to build a structured `transition_provenance` per turn from loop outputs (delta lifecycle, propagation, delayed events, rules, shocks). `transition_execution` is the canonical owner of the typed transition record, including `proposed_delta`, `governance_modified_delta`, `constrained_delta`, and unified `effect_records`.
- **Backward compatibility:** Existing provenance fields (`turn_record.delta_applied`, `variable_changes`, `events_triggered`, `rule_activations`, `shock`) remain populated; `transition_provenance` is additive and used by calibration, surprise analysis, and dashboards.

## 5. Phase 3+ preview

- Use `action_spec` directly in the loop when set, reducing ad-hoc interpretation.
- Further unify `apply_delta` and primary-variable handling around `TransitionResult`.
- Consolidate snapshot/clone to the canonical `State`/`WorldState` APIs.
- Reduce `legacy_semantics` usage as `variable_specs` gain richer metadata.

## 6. Remaining risks

- Legacy inference remains default when metadata is absent.
- Some older consumers may still use ad-hoc provenance fields instead of `transition_provenance`. Both legacy fields and the typed `TransitionProvenance` block will be maintained for the foreseeable future so downstream tools can migrate incrementally.

## 7. Changed-files summary (Phase 1)

Contracts: schemas/contracts.py, schemas/__init__.py. Legacy: core/legacy_semantics.py, core/llm_action_guard.py, core/governance.py, core/world_state.py, agents/base_agent.py, agents/planner.py, agents/utility.py, core/narrative_engine.py. Calibration/dashboard: core/calibration_metrics.py, core/calibration.py, ui/dashboard_payload.py (moved from core), simulation/loop.py, ui/dashboard.py, ui.py, tests/test_determinism.py, research/paper_draft.py. Docs: docs/architecture_refactor_plan.md, docs/engine_contracts.md, docs/migration_notes.md. Tests: tests/test_contracts.py.
