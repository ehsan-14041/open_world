from __future__ import annotations

"""
Transition kernel: shared transition semantics for planning and execution.

Phase 2 scope:
- Provide a pure deterministic core (`apply_core`) that delegates to
  `core.physics_core.apply_delta_deterministic`.
- Provide lightweight entrypoints for planning (`transition_planning`)
  and execution (`transition_execution`) that wrap existing behavior
  without changing world physics or governance semantics.

Notes:
- WorldModel.apply_delta remains the single place that owns stochastic
  noise, entity/relation updates, and narrative side effects.
- SimulationLoop.step() can call transition_execution to orchestrate
  governance/constraints/world.apply_delta/events/rules/shocks while
  building a structured TransitionProvenance record.
"""

from dataclasses import dataclass
from typing import Any, Literal

from config.settings import (
    LIGHT_PROP_HOPS,
    PLANNER_DECAY_FACTOR,
    PROPAGATION_DECAY_FACTOR,
)
from core.physics_core import apply_delta_deterministic as physics_apply_delta_deterministic
from schemas.delta_schema import Delta
from schemas.provenance import EffectRecord, TransitionProvenance
from world.delayed_events import DelayedEvent  # only for type hints


ModeLiteral = Literal["planning", "execution"]


@dataclass
class TransitionOptions:
    """
    Options for a single transition step.

    Booleans are explicit so callers can be clear about which stages are
    enabled in a given mode. Planning typically disables governance,
    constraints, noise, delayed events, event queue, rules, and shocks.
    """

    mode: ModeLiteral = "execution"
    enable_propagation: bool = True
    enable_governance: bool = False
    enable_constraints: bool = False
    enable_noise: bool = False
    enable_delayed_events: bool = True
    enable_event_queue: bool = True
    enable_rules: bool = True
    enable_shocks: bool = True
    max_prop_hops: int | None = None
    decay_factor: float | None = None
    propagation_params: dict[str, Any] | None = None


def _build_propagation_params(
    options: TransitionOptions | None,
) -> dict[str, Any] | None:
    """Resolve propagation parameters from options and config defaults."""
    if options is None:
        return None
    params: dict[str, Any] = {}
    if options.max_prop_hops is not None:
        params["max_hops"] = options.max_prop_hops
    if options.decay_factor is not None:
        params["decay_factor"] = options.decay_factor
    elif options.mode == "planning" and PLANNER_DECAY_FACTOR is not None:
        params["decay_factor"] = PLANNER_DECAY_FACTOR
    elif options.decay_factor is None:
        params["decay_factor"] = PROPAGATION_DECAY_FACTOR
    if options.propagation_params:
        params.update(options.propagation_params)
    return params or None


def apply_core(
    state: dict[str, Any],
    delta: Delta | dict[str, Any],
    causal_links: list[dict[str, Any]] | None,
    variable_specs: dict[str, dict[str, Any]] | None = None,
    *,
    action_type: str | None = None,
    options: TransitionOptions | None = None,
) -> dict[str, Any]:
    """
    Pure deterministic core: apply delta + propagation only via physics_core.

    - Delegates to core.physics_core.apply_delta_deterministic.
    - Returns a NEW state dict; does not mutate the input.
    - No governance, constraints, noise, or post-delta effects.
    """
    links = causal_links or []
    if isinstance(delta, dict):
        delta_obj: Any = Delta.from_dict(delta)
    else:
        delta_obj = delta
    if not options:
        options = TransitionOptions(mode="planning", enable_noise=False)
    propagation_params = _build_propagation_params(options)
    return physics_apply_delta_deterministic(
        state,
        delta_obj,
        links,
        variable_specs=variable_specs,
        action_type=action_type or getattr(delta_obj, "action_type", None),
        propagation_params=propagation_params,
    )


def _diff_variables(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compute simple variable diff between two snapshots."""
    changes: list[dict[str, Any]] = []
    all_keys = set(before.keys()) | set(after.keys())
    for key in sorted(all_keys):
        old = before.get(key, 0.0)
        new = after.get(key, 0.0)
        if not isinstance(old, (int, float)) or not isinstance(new, (int, float)):
            continue
        delta_val = float(new) - float(old)
        if abs(delta_val) < 1e-12:
            continue
        changes.append({"var": key, "delta": delta_val, "source": "total"})
    return changes


def transition_planning(
    snapshot: dict[str, Any],
    delta: dict[str, Any] | Delta,
    causal_links: list[dict[str, Any]] | None,
    variable_specs: dict[str, dict[str, Any]] | None,
    options: TransitionOptions | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Planning entrypoint: clone snapshot, run deterministic physics, return new snapshot + minimal provenance slice.

    The returned provenance slice is a dict containing:
    - propagation_trace
    - variable_changes
    """
    options = options or TransitionOptions(
        mode="planning",
        enable_governance=False,
        enable_constraints=False,
        enable_noise=False,
        max_prop_hops=LIGHT_PROP_HOPS,
        decay_factor=PLANNER_DECAY_FACTOR or PROPAGATION_DECAY_FACTOR,
    )
    base_state = {
        "variables": dict(snapshot.get("variables") or snapshot.get("global_state") or {}),
        "global_state": dict(snapshot.get("variables") or snapshot.get("global_state") or {}),
    }
    result = apply_core(
        base_state,
        delta,
        causal_links or snapshot.get("causal_links") or [],
        variable_specs=variable_specs or snapshot.get("variable_specs") or {},
        action_type=delta.get("action_type") if isinstance(delta, dict) else getattr(delta, "action_type", None),
        options=options,
    )
    before_vars = base_state["variables"]
    after_vars = result.get("variables") or result.get("global_state") or {}
    variable_changes = _diff_variables(before_vars, after_vars)
    new_snapshot = dict(snapshot)
    new_snapshot["variables"] = dict(after_vars)
    new_snapshot["global_state"] = dict(after_vars)
    provenance_slice: dict[str, Any] = {
        "propagation_trace": list(result.get("propagation_trace") or []),
        "variable_changes": variable_changes,
    }
    return new_snapshot, provenance_slice


def transition_execution(
    *,
    pre_state: dict[str, Any],
    post_state: dict[str, Any],
    proposed_delta: dict[str, float],
    constrained_delta: dict[str, float],
    governance_modified_delta: dict[str, float] | None,
    outcome: dict[str, Any] | list[dict[str, Any]] | None,
    events_triggered: list[dict[str, Any]],
    rule_activations: list[dict[str, Any]],
    shock_result: dict[str, Any] | None,
    options: TransitionOptions | None = None,
) -> TransitionProvenance:
    """
    Execution entrypoint: build a structured TransitionProvenance from loop outputs.

    Phase 2 keeps side effects (world.apply_delta, delayed events, event queue,
    rules, shocks) orchestrated by SimulationLoop.step() and uses this helper
    purely to construct a typed provenance record.
    """
    options = options or TransitionOptions(mode="execution")

    # 1) Extract physics details from outcome
    if isinstance(outcome, dict):
        propagation_trace = outcome.get("propagation_trace", [])
        noise_component = outcome.get("noise_component", {})
    else:
        propagation_trace = []
        noise_component = {}

    # 2) Final variable changes via diff (pre_state -> post_state)
    before_vars = (pre_state.get("variables") or pre_state.get("global_state") or {}) or {}
    after_vars = (post_state.get("variables") or post_state.get("global_state") or {}) or {}
    final_variable_changes = _diff_variables(
        before_vars if isinstance(before_vars, dict) else {},
        after_vars if isinstance(after_vars, dict) else {},
    )

    # 3) EffectRecord list in canonical ordering
    effect_records: list[EffectRecord] = []
    if constrained_delta:
        effect_records.append(
            EffectRecord(
                source="direct",
                trigger_turn=int(post_state.get("turn", 0)),
                origin_id=None,
                params_or_delta=dict(constrained_delta),
                description="Direct constrained delta",
            )
        )
    # Delayed + generic events are both in events_triggered; we distinguish by metadata.source when present.
    for ev in events_triggered:
        meta = ev.get("metadata") or {}
        source: Literal["delayed", "event"] = "event"
        if isinstance(meta, dict) and meta.get("source") == "delayed_event":
            source = "delayed"
        # Generic, metadata-driven payload: capture core structural fields only.
        params_or_delta: dict[str, Any] = {
            "event_type": ev.get("event_type"),
            "trigger_turn": ev.get("trigger_turn"),
        }
        if "params" in ev and isinstance(ev.get("params"), dict):
            params_or_delta["params"] = dict(ev["params"])
        if isinstance(meta, dict) and meta:
            params_or_delta["metadata"] = dict(meta)
        effect_records.append(
            EffectRecord(
                source=source,
                trigger_turn=int(ev.get("trigger_turn", post_state.get("turn", 0))),
                origin_id=str(ev.get("event_type") or ""),
                params_or_delta=params_or_delta,
                description="Delayed event effect" if source == "delayed" else "Scenario or conflict event",
            )
        )
    for r in rule_activations:
        rule_payload: dict[str, Any] = {
            "condition_key": r.get("condition_key"),
            "effect_key": r.get("effect_key"),
        }
        if "params" in r and isinstance(r.get("params"), dict):
            rule_payload["params"] = dict(r["params"])
        effect_records.append(
            EffectRecord(
                source="rule",
                trigger_turn=int(post_state.get("turn", 0)),
                origin_id=str(r.get("id") or ""),
                params_or_delta=rule_payload,
                description="Rule activation",
            )
        )
    if options.enable_shocks and shock_result and isinstance(shock_result, dict) and shock_result.get("active"):
        effect_records.append(
            EffectRecord(
                source="shock",
                trigger_turn=int(post_state.get("turn", 0)),
                origin_id="shock_engine",
                params_or_delta={
                    "shocks": shock_result.get("shocks", []),
                    "impact_delta": shock_result.get("impact_delta", {}),
                    "intensity": shock_result.get("intensity"),
                },
                description="Shock engine effect",
            )
        )

    # 4) Build TransitionProvenance
    transition_prov = TransitionProvenance(
        proposed_delta=dict(proposed_delta or {}),
        governance_modified_delta=dict(governance_modified_delta or {}) if governance_modified_delta else None,
        constrained_delta=dict(constrained_delta or {}),
        propagation_trace=list(propagation_trace or []),
        noise_component=dict(noise_component or {}),
        delayed_effects=[
            ev for ev in events_triggered if (ev.get("metadata") or {}).get("source") == "delayed_event"
        ],
        events_fired=[
            ev for ev in events_triggered if (ev.get("metadata") or {}).get("source") != "delayed_event"
        ],
        rule_effects=list(rule_activations),
        shock_effect=dict(shock_result or {}),
        final_variable_changes=final_variable_changes,
        effect_records=effect_records,
    )

    return transition_prov

