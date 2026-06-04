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
        PROPAGATION_DECAY_FACTOR,
        PROPAGATION_SIGNIFICANCE_THRESHOLD,
        FLOW_DAMPING_DEFAULT,
    )
except ImportError:
    PROPAGATION_MAX_ITER = 5
    PROPAGATION_EPSILON = 1e-6
    PROPAGATION_DAMPING = 0.6
    PROPAGATION_DECAY_FACTOR = 1.0
    PROPAGATION_SIGNIFICANCE_THRESHOLD = 1e-6
    FLOW_DAMPING_DEFAULT = 0.8


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


def propagate_variable_changes_from_state(
    base_state: dict[str, float],
    primary_updates: dict[str, float],
    causal_graph: list[dict[str, Any]],
    *,
    decay_factor: float = 0.85,
    max_hops: int = 3,
    variable_specs: dict[str, dict[str, Any]] | None = None,
    significance_threshold: float | None = None,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """
    BFS/wave propagation from a state dict. For hop distance d:
    delta_d = delta_0 * weight * (decay_factor ** d).
    Returns (secondary_effects, propagation_trace). Primary effects are in primary_updates;
    this function returns only propagated secondary effects and trace for explainability.
    """
    sig_thresh = (
        significance_threshold
        if significance_threshold is not None
        else PROPAGATION_SIGNIFICANCE_THRESHOLD
    )
    causal_links = _structural_causal_links(causal_graph or [])
    secondary_effects: dict[str, float] = {}
    propagation_trace: list[dict[str, Any]] = []

    if not primary_updates or not causal_links:
        return secondary_effects, propagation_trace

    def _rate_limit(v: str) -> float:
        spec = (variable_specs or {}).get(v)
        if spec and isinstance(spec.get("rate_limit"), (int, float)):
            return float(spec["rate_limit"])
        return 10.0

    def _clamp_delta(var: str, d: float) -> float:
        rl = _rate_limit(var)
        return max(-rl, min(rl, d))

    primary_variable = max(primary_updates.items(), key=lambda x: abs(x[1]))[0]
    round_deltas: dict[str, float] = {
        k: float(v) for k, v in primary_updates.items() if isinstance(v, (int, float))
    }

    for iteration in range(max_hops):
        next_deltas: dict[str, float] = {}
        distance = iteration + 1
        decay_mult = decay_factor ** distance

        for link in causal_links:
            from_var = link.get("from")
            to_var = link.get("to")
            if from_var not in round_deltas or not to_var:
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
            add = delta_source * w * decay_mult
            add = add * _flow_damping_for_var(to_var, variable_specs)
            add = _clamp_delta(to_var, add)

            propagation_trace.append({
                "hop": distance,
                "from": from_var,
                "to": to_var,
                "weight": w,
                "delta_source": float(delta_source),
                "delta_contrib": add,
                "decay_factor": decay_factor,
            })

            if sig_thresh > 0 and abs(add) < sig_thresh:
                continue
            if to_var != primary_variable:
                secondary_effects[to_var] = secondary_effects.get(to_var, 0.0) + add
            next_deltas[to_var] = next_deltas.get(to_var, 0.0) + add

        if not next_deltas:
            break
        round_deltas = next_deltas

    return secondary_effects, propagation_trace


def _flow_damping_for_var(var: str, variable_specs: dict[str, dict[str, Any]] | None) -> float:
    """Return multiplier for FLOW variables (damping_factor or FLOW_DAMPING_DEFAULT); 1.0 for STOCK."""
    spec = (variable_specs or {}).get(var)
    if not spec or not isinstance(spec, dict):
        return 1.0
    bt = str(spec.get("behavior_type", "STOCK")).upper()
    if bt != "FLOW":
        return 1.0
    df = spec.get("damping_factor")
    if isinstance(df, (int, float)):
        return max(0.0, min(1.0, float(df)))
    return FLOW_DAMPING_DEFAULT


def propagate_variable_changes(
    world: Any,
    direct_changes: dict[str, float],
    primary_variable: str | None = None,
    max_iterations: int | None = None,
    *,
    variable_specs: dict[str, dict[str, Any]] | None = None,
    damping: float | None = None,
    epsilon: float | None = None,
    decay_factor: float | None = None,
    significance_threshold: float | None = None,
) -> tuple[dict[str, float], dict[str, float], list[dict[str, Any]]]:
    """
    Propagate variable changes along structural causal_links deterministically.
    Uses damping, causal decay (delta_n = delta_0 * decay_factor^distance), epsilon convergence,
    per-iteration clamp by rate_limit. FLOW variables get additional per-target damping.
    Sparse propagation: skip contributions below significance_threshold.
    Returns (primary_effects, secondary_effects, propagation_trace).
    """
    max_iter = max_iterations if max_iterations is not None else PROPAGATION_MAX_ITER
    damp = damping if damping is not None else PROPAGATION_DAMPING
    eps = epsilon if epsilon is not None else PROPAGATION_EPSILON
    decay = decay_factor if decay_factor is not None else PROPAGATION_DECAY_FACTOR
    sig_thresh = significance_threshold if significance_threshold is not None else PROPAGATION_SIGNIFICANCE_THRESHOLD

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
        distance = iteration + 1  # first hop = 1, second = 2, ...
        decay_mult = decay ** distance
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
            add = delta_source * w * damp * decay_mult
            flow_mult = _flow_damping_for_var(to_var, variable_specs)
            add = add * flow_mult
            add = _clamp_delta(to_var, add)

            skipped = sig_thresh > 0 and abs(add) < sig_thresh
            propagation_trace.append({
                "iter": iteration,
                "from": from_var,
                "to": to_var,
                "weight": w,
                "delta_source": float(delta_source),
                "delta_contrib": add,
                "skipped": skipped,
            })

            if not skipped:
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


def primary_propagation_check(
    world: Any,
    outcome: dict[str, Any],
    primary_variable: str | None = None,
) -> tuple[bool, str]:
    """
    Verify propagation outcome: no NaN/Inf in world variables; optional check that
    primary effect variable received the direct change. Returns (ok, message).
    """
    variables = getattr(world, "variables", None)
    if not isinstance(variables, dict):
        return True, ""
    for var, val in variables.items():
        if isinstance(val, float) and (val != val or val == float("inf") or val == float("-inf")):
            return False, f"variable '{var}' has invalid value after propagation (NaN/Inf)"
    primary_effect = outcome.get("primary_effect") if isinstance(outcome, dict) else None
    if primary_variable and isinstance(primary_effect, dict):
        pvar = primary_effect.get("var")
        if pvar and pvar == primary_variable and primary_effect.get("delta") is not None:
            if pvar not in variables:
                return False, f"primary variable '{pvar}' missing from world after apply"
    return True, ""
