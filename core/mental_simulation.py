"""
Light mental simulation for planner: deterministic propagation, no noise, bounded hops.
Mirrors world.apply_delta physics for planner consistency (Unified Physics).
"""

from __future__ import annotations

import copy
from typing import Any

from core.propagation import (
    _structural_causal_links,
    _flow_damping_for_var,
    PROPAGATION_DAMPING,
    PROPAGATION_DECAY_FACTOR,
    PROPAGATION_SIGNIFICANCE_THRESHOLD,
)


def _apply_direct_to_state(
    state: dict[str, Any],
    direct_changes: dict[str, float],
) -> None:
    """Apply direct numeric updates to state in place. Uses variables or global_state."""
    vars_ref = state.get("variables") or state.get("global_state") or {}
    if not isinstance(vars_ref, dict):
        return
    for key, value in direct_changes.items():
        if isinstance(value, (int, float)):
            current = vars_ref.get(key, 0)
            if isinstance(current, (int, float)):
                vars_ref[key] = current + value
            else:
                vars_ref[key] = value
    if "global_state" not in state and "variables" in state:
        state["global_state"] = state["variables"]
    elif "variables" not in state and "global_state" in state:
        state["variables"] = state["global_state"]


def apply_delta_light(
    delta: dict[str, Any],
    state: dict[str, Any],
    causal_links: list[dict[str, Any]],
    variable_specs: dict[str, dict[str, Any]] | None = None,
    *,
    max_hops: int = 1,
    decay_factor: float | None = None,
    damping: float | None = None,
    significance_threshold: float | None = None,
) -> dict[str, float]:
    """
    Apply delta with deterministic propagation only; no noise.
    Bounded to max_hops propagation steps; causal decay applied.
    Returns combined primary + secondary effects (variable -> total delta).
    Does not mutate state; caller should apply returned effects to state if desired.
    """
    variable_specs = variable_specs or {}
    decay = decay_factor if decay_factor is not None else PROPAGATION_DECAY_FACTOR
    damp = damping if damping is not None else PROPAGATION_DAMPING
    sig_thresh = (
        significance_threshold
        if significance_threshold is not None
        else PROPAGATION_SIGNIFICANCE_THRESHOLD
    )
    direct_changes = dict(delta.get("numeric_updates") or {})
    for k, v in list(direct_changes.items()):
        if not isinstance(v, (int, float)):
            del direct_changes[k]
    if not direct_changes:
        return {}

    # Build a minimal world-like object for propagation
    variables = dict(state.get("variables") or state.get("global_state") or {})
    links = _structural_causal_links(causal_links or [])

    primary_variable = max(direct_changes.items(), key=lambda x: abs(x[1]))[0]
    primary_effects: dict[str, float] = {}
    secondary_effects: dict[str, float] = {}
    for var, d in direct_changes.items():
        if var == primary_variable:
            primary_effects[var] = float(d)
        else:
            secondary_effects[var] = float(d)

    def _rate_limit(v: str) -> float:
        spec = variable_specs.get(v)
        if spec and isinstance(spec.get("rate_limit"), (int, float)):
            return float(spec["rate_limit"])
        return 10.0

    def _clamp_delta(var: str, d: float) -> float:
        return max(-_rate_limit(var), min(_rate_limit(var), d))

    round_deltas: dict[str, float] = dict(direct_changes)
    max_iter = max(1, min(max_hops + 1, 10))  # at most max_hops propagation rounds

    for iteration in range(max_iter - 1):
        next_deltas: dict[str, float] = {}
        distance = iteration + 1
        decay_mult = decay ** distance
        for link in links:
            from_var = link.get("from")
            to_var = link.get("to")
            if from_var not in round_deltas or not to_var:
                continue
            # Per-var decay_rate from ValueSpec overrides global decay for this target
            to_spec = variable_specs.get(to_var)
            link_decay = float(to_spec["decay_rate"]) if isinstance(to_spec, dict) and isinstance(to_spec.get("decay_rate"), (int, float)) else decay
            link_decay_mult = link_decay ** distance
            weight = link.get("weight")
            if weight is None:
                pol = (link.get("polarity") or "positive").lower()
                strength = float(link.get("strength", 0.5))
                weight = -strength if pol == "negative" else strength
            try:
                w = float(weight)
            except (TypeError, ValueError):
                w = 0.0
            delta_source = round_deltas[from_var]
            add = delta_source * w * damp * link_decay_mult
            add = add * _flow_damping_for_var(to_var, variable_specs)
            add = _clamp_delta(to_var, add)
            if sig_thresh > 0 and abs(add) < sig_thresh:
                continue
            next_deltas[to_var] = next_deltas.get(to_var, 0.0) + add
        if not next_deltas:
            break
        for var, d in next_deltas.items():
            if var != primary_variable:
                secondary_effects[var] = secondary_effects.get(var, 0.0) + d
        round_deltas = next_deltas

    # Combined effects (primary + secondary) as total delta per var
    combined: dict[str, float] = {}
    for var, d in primary_effects.items():
        combined[var] = combined.get(var, 0.0) + d
    for var, d in secondary_effects.items():
        combined[var] = combined.get(var, 0.0) + d
    return combined


def run_mental_simulation(
    snapshot: dict[str, Any],
    delta: dict[str, Any],
    causal_links: list[dict[str, Any]],
    variable_specs: dict[str, dict[str, Any]] | None = None,
    *,
    max_hops: int = 1,
    decay_factor: float | None = None,
) -> dict[str, Any]:
    """
    Clone snapshot, run apply_delta_light (deterministic, no noise), return updated state.
    State variables = initial + combined_effects (direct + propagated). Does not mutate snapshot.
    """
    from world.world_state import clone_world_state

    state = clone_world_state(snapshot, include_causal_links=True)
    combined_effects = apply_delta_light(
        delta,
        state,
        causal_links,
        variable_specs,
        max_hops=max_hops,
        decay_factor=decay_factor,
    )
    initial_vars = copy.deepcopy(
        snapshot.get("variables") or snapshot.get("global_state") or {}
    )
    for var, d in combined_effects.items():
        initial_vars[var] = initial_vars.get(var, 0) + d
    state["variables"] = initial_vars
    state["global_state"] = initial_vars
    return state
