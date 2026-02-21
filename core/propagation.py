"""
Causal variable propagation: deterministic propagation along structural causal_links only.
Uses damping, epsilon convergence, per-iteration clamp. Returns propagation_trace.
No noise is applied here - noise is applied at final stage after propagation.
"""

from __future__ import annotations

from typing import Any

try:
    from config.settings import (
        PROPAGATION_MAX_ITER,
        PROPAGATION_EPSILON,
        PROPAGATION_DAMPING,
    )
except ImportError:
    PROPAGATION_MAX_ITER = 5
    PROPAGATION_EPSILON = 1e-6
    PROPAGATION_DAMPING = 0.6


def _structural_causal_links(causal_links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter to structural links only: must have 'from' and 'to' keys. Exclude action provenance."""
    out = []
    for link in causal_links or []:
        if not isinstance(link, dict):
            continue
        from_var = link.get("from")
        to_var = link.get("to")
        if not from_var or not to_var:
            continue
        # Exclude action provenance (from_action, agent, variable, delta)
        if "from_action" in link or "agent" in link:
            continue
        out.append(link)
    return out


def propagate_variable_changes(
    world: Any,
    direct_changes: dict[str, float],
    primary_variable: str | None = None,
    max_iterations: int | None = None,
    *,
    variable_specs: dict[str, dict[str, Any]] | None = None,
    damping: float | None = None,
    epsilon: float | None = None,
) -> tuple[dict[str, float], dict[str, float], list[dict[str, Any]]]:
    """
    Propagate variable changes along structural causal_links deterministically.
    Uses damping, epsilon convergence, per-iteration clamp by rate_limit.
    Returns (primary_effects, secondary_effects, propagation_trace).
    """
    max_iter = max_iterations if max_iterations is not None else PROPAGATION_MAX_ITER
    damp = damping if damping is not None else PROPAGATION_DAMPING
    eps = epsilon if epsilon is not None else PROPAGATION_EPSILON

    variables = getattr(world, "variables", None)
    causal_links = getattr(world, "causal_links", None) or []
    causal_links = _structural_causal_links(causal_links)

    primary_effects: dict[str, float] = {}
    secondary_effects: dict[str, float] = {}
    propagation_trace: list[dict[str, Any]] = []

    if not isinstance(variables, dict):
        return primary_effects, secondary_effects, propagation_trace

    if primary_variable is None and direct_changes:
        primary_variable = max(direct_changes.items(), key=lambda x: abs(x[1]))[0]

    for var, delta in direct_changes.items():
        if not isinstance(delta, (int, float)):
            continue
        if var == primary_variable:
            primary_effects[var] = float(delta)
        else:
            secondary_effects[var] = float(delta)

    if not causal_links:
        return primary_effects, secondary_effects, propagation_trace

    def _rate_limit(v: str) -> float:
        spec = (variable_specs or {}).get(v)
        if spec and isinstance(spec.get("rate_limit"), (int, float)):
            return float(spec["rate_limit"])
        return 10.0  # default

    def _clamp_delta(var: str, d: float) -> float:
        rl = _rate_limit(var)
        return max(-rl, min(rl, d))

    round_deltas: dict[str, float] = dict(direct_changes)
    for iteration in range(max_iter - 1):
        next_deltas: dict[str, float] = {}
        for link in causal_links:
            from_var = link.get("from")
            to_var = link.get("to")
            if from_var not in round_deltas or to_var is None:
                continue
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
            add = delta_source * w * damp
            add = _clamp_delta(to_var, add)

            propagation_trace.append({
                "iter": iteration,
                "from": from_var,
                "to": to_var,
                "weight": w,
                "delta_source": float(delta_source),
                "delta_contrib": add,
            })

            if to_var not in next_deltas:
                next_deltas[to_var] = 0.0
            next_deltas[to_var] += add

        if not next_deltas:
            break

        # Epsilon convergence: stop if max change is below epsilon
        max_change = max(abs(d) for d in next_deltas.values()) if next_deltas else 0.0
        if max_change < eps:
            break

        for var, d in next_deltas.items():
            if var != primary_variable:
                secondary_effects[var] = secondary_effects.get(var, 0.0) + d

        round_deltas = next_deltas

    return primary_effects, secondary_effects, propagation_trace
