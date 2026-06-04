"""
Light mental simulation for planner: uses unified physics_core (deterministic, no noise).
Mirrors world.apply_delta physics for planner consistency (Unified Physics).
"""

from __future__ import annotations

from typing import Any

try:
    from core.physics_core import apply_delta_deterministic
except ImportError:
    apply_delta_deterministic = None  # type: ignore[misc, assignment]


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
    Thin wrapper around physics_core.apply_delta_deterministic.
    Returns combined primary + secondary effects (variable -> total delta). Does not mutate state.
    """
    if not apply_delta_deterministic:
        return {}
    result = apply_delta_deterministic(
        state,
        delta,
        causal_links or [],
        variable_specs=variable_specs,
        action_type=delta.get("action_type") if isinstance(delta, dict) else None,
        propagation_params={"max_hops": max_hops, "decay_factor": decay_factor} if decay_factor is not None else None,
    )
    prev = state.get("variables") or state.get("global_state") or {}
    new_vars = result.get("variables") or result.get("global_state") or {}
    combined: dict[str, float] = {}
    for var, new_val in new_vars.items():
        if isinstance(new_val, (int, float)):
            old = prev.get(var, 0)
            if isinstance(old, (int, float)):
                d = float(new_val) - float(old)
            else:
                d = float(new_val)
            if abs(d) >= 1e-12:
                combined[var] = d
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
    Clone snapshot, run apply_delta_deterministic (unified physics, no noise), return updated state.
    Does not mutate snapshot.
    """
    if not apply_delta_deterministic:
        return dict(snapshot)
    try:
        from config.settings import PROPAGATION_DECAY_FACTOR
    except ImportError:
        PROPAGATION_DECAY_FACTOR = 1.0
    result = apply_delta_deterministic(
        dict(snapshot),
        delta,
        causal_links or [],
        variable_specs=variable_specs,
        action_type=delta.get("action_type") if isinstance(delta, dict) else None,
        propagation_params={
            "max_hops": max_hops,
            "decay_factor": decay_factor if decay_factor is not None else PROPAGATION_DECAY_FACTOR,
        },
    )
    state = dict(snapshot)
    state["variables"] = result.get("variables") or result.get("global_state") or {}
    state["global_state"] = state["variables"]
    if "propagation_trace" in result:
        state["propagation_trace"] = result["propagation_trace"]
    return state
