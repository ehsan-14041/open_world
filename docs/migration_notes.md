# Migration notes (Phases 1–2)

Notes for migrating to the Phase 1 and Phase 2 architecture and reducing reliance on legacy behavior.

## 1. Dict snapshots → State (optional)

- **Current:** Most code uses dict snapshots with keys `variables`, `global_state`, `causal_links`, `entities`, `relations`, `version`, `turn`, optional `narrative`, `ontology`.
- **Migration:** Use `State.from_dict(snapshot)` when you need a typed view; call `.to_dict()` when passing to code that expects a dict. No need to change all call sites in Phase 1.
- **Adapters:** `state_from_dict(snapshot)` in `schemas/contracts.py` builds a `State` from any legacy snapshot dict.

## 2. Variable_specs: non_negative and protected

- **Current:** Core infers non-negative and protected variables from names (e.g. "population", "cash") when `variable_specs` do not specify them. This logic lives in `core/legacy_semantics.py` and is used only when declarative metadata is absent.
- **Migration:** Add explicit metadata to scenario `variable_specs` so core does not rely on legacy inference:
  - For variables that must not go negative, set `non_negative: true` in the variable spec (or use ValueSpec and map to ConstraintSpec with `non_negative=True`).
  - For policy-protected variables, set `protected: true` in the variable spec where supported, or supply a policy dict with `protected_keys` (e.g. from config) to WorldState.
- **Where legacy is used:** `core/llm_action_guard.py` (sanitize), `core/governance.py` (_default_non_negative_check), `core/world_state.py` (policy from legacy_default_policy when not provided). All prefer variable_specs/ConstraintSpec when present.
- **Turning off legacy:** In a future phase, scenarios can be required to set `non_negative`/`protected` for relevant variables; then legacy inference can be disabled or gated by config.

## 3. Dashboard payload move and loop callback

- **Current:** Dashboard payload is built in `ui/dashboard_payload.py`. Calibration metrics are computed in `core/calibration_metrics.py`. The simulation loop does not import the payload builder; it accepts an optional `build_turn_payload` callback.
- **Migration for consumers:**
  - **UI / main:** When creating `SimulationLoop`, pass `build_turn_payload=build_dashboard_payload` so that when `DEBUG_PERF` is set, the loop can call the callback to build the payload. Import `build_dashboard_payload` from `ui.dashboard_payload` or `ui.dashboard`.
  - **Tests:** Import `build_dashboard_payload` from `ui.dashboard_payload` (or `ui.dashboard`). For calibration-only tests, import `compute_calibration_from_provenance` from `core.calibration_metrics`.
  - **Legacy import:** `core.dashboard_payload` was removed; do not use `from core.dashboard_payload import ...`. Use `ui.dashboard_payload` or `ui.dashboard` instead.

## 4. Legacy semantics module

- **Location:** `core/legacy_semantics.py`.
- **Exports:** `legacy_infer_non_negative_variables`, `legacy_is_non_negative_variable`, `legacy_protected_keys`, `legacy_default_policy`, `legacy_steady_action_name`, `legacy_strategy_class_from_action_type`, `legacy_goal_to_var_direction`, `legacy_fallback_action_for_variables`.
- **When it is used:** When scenario or config does not supply the corresponding metadata (e.g. variable_specs without `non_negative`, no policy with `protected_keys`, no strategy_classes for an action type). Safe to keep enabled; add declarative metadata to reduce reliance over time.
- **Do not add new domain keywords** in this module; prefer scenario variable_specs and strategy_classes.

## 5. Isolated semantic hardcodes (list)

| Location | What was isolated | Now in |
|----------|-------------------|--------|
| Non-negative variable inference | Keyword set + name check | `core/legacy_semantics.py` (NON_NEGATIVE_KEYWORDS, legacy_infer_non_negative_variables, legacy_is_non_negative_variable) |
| Protected keys | Default list + policy dict | `core/legacy_semantics.py` (legacy_protected_keys, legacy_default_policy); config/policy_default.json |
| Steady action name | "steady_finance" | `core/legacy_semantics.py` (legacy_steady_action_name) |
| Action type → strategy class | Name patterns (launch_, steady_, propose_, etc.) | `core/legacy_semantics.py` (legacy_strategy_class_from_action_type) |
| Goal/objective → (var, direction) | increase_/decrease_/maximize_/minimize_ prefixes | `core/legacy_semantics.py` (legacy_goal_to_var_direction) |
| Fallback action when no candidates | increase_{first_var} or adjust_variable | `core/legacy_semantics.py` (legacy_fallback_action_for_variables) |

Core and agents call into these functions instead of inlining name-based logic. Variable_specs and ConstraintSpec are preferred where available.

## 6. Transition kernel and typed provenance (Phase 2)

- **Transition kernel:** `core/transition_kernel.py` introduces:
  - `TransitionOptions` to control mode (`planning` vs `execution`) and propagation/flags.
  - `apply_core` as the shared deterministic core delegating to `core.physics_core.apply_delta_deterministic`.
  - `transition_planning` used by `agents/planner.py` so depth-2 planning shares physics with execution.
  - `transition_execution` which builds a typed `TransitionProvenance` from loop outputs (no additional side effects in Phase 2).
- **Planner migration:** `_apply_delta_for_planning` in `agents/planner.py` now delegates to `transition_planning` instead of calling physics directly. Call sites of `plan_depth2*` do not need changes.
- **Typed provenance:** `schemas/provenance.py` defines:
  - `EffectRecord` for unified effect/event representation.
  - `TransitionProvenance` capturing `proposed_delta`, `governance_modified_delta`, `constrained_delta`, `propagation_trace`, `noise_component`, delayed/events/rules/shock effects, `final_variable_changes`, and `effect_records` in canonical ordering.
- **Loop wiring:** `simulation/loop.py`:
  - Still owns governance, constraints, `world.apply_delta`, delayed events, rules, shocks.
  - Calls `transition_execution` after `world.apply_delta` and regime/shock processing to attach `transition_provenance` to each provenance entry.
  - Keeps existing `turn_record` shape for backward compatibility; new consumers should prefer `transition_provenance`.

### 6.1. Reading transition provenance

- From a provenance entry:
  - `entry["transition_provenance"]["proposed_delta"]` — merged delta before soft constraints.
  - `entry["transition_provenance"]["constrained_delta"]` — delta after constraints (matches `turn_record["delta_applied"]`).
  - `entry["transition_provenance"]["final_variable_changes"]` — reconciled numeric diff between pre/post state.
  - `entry["transition_provenance"]["effect_records"]` — ordered list of `EffectRecord` instances (`direct → delayed → event → rule → shock → recalibration`).

Existing tooling that only reads `turn_record.delta_applied` or `variable_changes` continues to work without change.

### 6.2. Updated semantics (Phase 3 gap-closure)

- `proposed_delta` is now defined as the merged numeric delta **after** governance repair and merge, but **before** soft constraints.
- `governance_modified_delta` is populated as a governance-only correction term:
  - For each variable it records the difference `merged_after_governance[var] - merged_before_governance[var]`.
  - It is `None` when governance did not modify the merged delta.
- `constrained_delta` continues to mirror `turn_record["delta_applied"]` (numeric delta after soft constraints).
- `effect_records` are built in a canonical order (`direct → delayed → events → rules → shocks → recalibration`) and draw only on structural fields and metadata already present on delayed events, event queue entries, rule activations, and shock results.
