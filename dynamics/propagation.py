"""
Deterministic propagation with edge_model adapters (linear, logistic, ordinal_shift, etc.).
Uses structural causal_links only; delay > 0 links are skipped (handled by delayed_effects queue).
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

try:
    from model.causal_graph import (
        structural_causal_links,
        get_weight_for_propagation,
        get_delay,
    )
except ImportError:
    def structural_causal_links(links: list) -> list:
        out = []
        for link in links or []:
            if not isinstance(link, dict): continue
            if link.get("from_action") or link.get("agent"): continue
            if link.get("from") and link.get("to"): out.append(link)
        return out
    def get_weight_for_propagation(link: dict) -> float:
        w = link.get("weight")
        if w is not None: return float(w)
        pol = (link.get("polarity") or "positive").lower()
        return -float(link.get("strength", 0.5)) if pol == "negative" else float(link.get("strength", 0.5))
    def get_delay(link: dict) -> int:
        em = link.get("edge_model")
        if isinstance(em, dict) and isinstance(em.get("delay"), int): return max(0, em["delay"])
        return max(0, int(link.get("delay", 0)))


def _effective_weight(link: dict[str, Any], variables: dict[str, Any]) -> float:
    """Edge model adapter: linear (default), logistic, ordinal_shift, categorical_influence map to effective weight."""
    em = link.get("edge_model")
    if not isinstance(em, dict):
        return get_weight_for_propagation(link)
    t = (em.get("type") or "linear").strip().lower()
    params = em.get("params") or {}
    w = params.get("weight") or params.get("strength")
    if w is not None:
        try:
            base = float(w)
        except (TypeError, ValueError):
            base = 0.5
    else:
        base = get_weight_for_propagation(link)
    if t == "linear":
        return base
    if t == "logistic":
        # optional: scale by sigmoid slope; for now same as linear
        return base * float(params.get("slope", 1.0))
    if t in ("ordinal_shift", "categorical_influence", "custom"):
        return base
    return base


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
    Propagate along structural causal_links. Uses model.causal_graph.
    Skips links with delay > 0 (apply via delayed_effects queue).
    Returns (primary_effects, secondary_effects, propagation_trace).
    """
    return propagate_with_edge_models(
        world,
        direct_changes,
        primary_variable=primary_variable,
        max_iterations=max_iterations,
        variable_specs=variable_specs,
        damping=damping,
        epsilon=epsilon,
    )


def propagate_with_edge_models(
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
    Same as propagate_variable_changes but uses edge_model for weight and skips delay > 0.
    """
    max_iter = max_iterations if max_iterations is not None else PROPAGATION_MAX_ITER
    damp = damping if damping is not None else PROPAGATION_DAMPING
    eps = epsilon if epsilon is not None else PROPAGATION_EPSILON

    variables = getattr(world, "variables", None)
    causal_links = getattr(world, "causal_links", None) or []
    causal_links = structural_causal_links(causal_links)
    # Only immediate links (delay=0)
    immediate_links = [ln for ln in causal_links if get_delay(ln) == 0]

    primary_effects = {}
    secondary_effects = {}
    propagation_trace = []

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

    if not immediate_links:
        return primary_effects, secondary_effects, propagation_trace

    def _rate_limit(v: str) -> float:
        spec = (variable_specs or {}).get(v)
        if spec and isinstance(spec.get("rate_limit"), (int, float)):
            return float(spec["rate_limit"])
        return 10.0

    def _clamp_delta(var: str, d: float) -> float:
        return max(-_rate_limit(var), min(_rate_limit(var), d))

    round_deltas = dict(direct_changes)
    for iteration in range(max_iter - 1):
        next_deltas = {}
        for link in immediate_links:
            from_var = link.get("from")
            to_var = link.get("to")
            if from_var not in round_deltas or not to_var:
                continue
            w = _effective_weight(link, variables)
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
        max_change = max(abs(d) for d in next_deltas.values())
        if max_change < eps:
            break
        for var, d in next_deltas.items():
            if var != primary_variable:
                secondary_effects[var] = secondary_effects.get(var, 0.0) + d
        round_deltas = next_deltas

    return primary_effects, secondary_effects, propagation_trace
