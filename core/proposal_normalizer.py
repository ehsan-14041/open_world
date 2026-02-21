"""
Deterministic normalization of creative proposals: qualitative -> numeric delta_vector.
Magnitude scaling from variable_specs.rate_limit; direction -> sign.
"""

from __future__ import annotations

from typing import Any

MAGNITUDE_SCALE = {
    "tiny": 0.15,
    "small": 0.35,
    "medium": 0.70,
    "large": 1.00,
}


def _rate_limit_for_var(
    var: str,
    variable_specs: dict[str, dict[str, Any]],
    variables: dict[str, float],
) -> float:
    """Get rate_limit for variable; else derive from range (0-100 -> 10)."""
    spec = variable_specs.get(var)
    if spec and isinstance(spec.get("rate_limit"), (int, float)):
        return float(spec["rate_limit"])
    val = variables.get(var, 50.0)
    if isinstance(val, (int, float)):
        if 0 <= val <= 100:
            return 10.0
        return max(1.0, abs(val) * 0.1)
    return 10.0


def normalize_creative_proposal(
    proposal: dict[str, Any],
    known_variables: set[str],
    variable_specs: dict[str, dict[str, Any]],
    variables: dict[str, float],
    *,
    change_budget: float | None = None,
) -> dict[str, float] | None:
    """
    Convert qualitative effects to numeric delta_vector. Returns None if invalid.
    """
    effects = proposal.get("effects") or []
    if not isinstance(effects, list):
        return None

    delta_vector: dict[str, float] = {}
    for eff in effects:
        if not isinstance(eff, dict):
            continue
        var = eff.get("var") or eff.get("variable")
        if not var or (known_variables and var not in known_variables):
            continue
        mag = (eff.get("magnitude") or "medium").lower().strip()
        direction = (eff.get("direction") or "up").lower().strip()
        scale = MAGNITUDE_SCALE.get(mag, 0.5)
        rl = _rate_limit_for_var(var, variable_specs, variables)
        delta_val = scale * rl
        if direction == "down":
            delta_val = -delta_val
        delta_vector[var] = delta_vector.get(var, 0.0) + delta_val

    if not delta_vector:
        return None

    # Clamp to rate_limit per var
    for var in list(delta_vector.keys()):
        rl = _rate_limit_for_var(var, variable_specs, variables)
        v = delta_vector[var]
        delta_vector[var] = max(-rl, min(rl, v))

    # Global change budget
    if change_budget is not None and change_budget > 0:
        total = sum(abs(v) for v in delta_vector.values())
        if total > change_budget:
            scale = change_budget / total
            for k in delta_vector:
                delta_vector[k] *= scale

    return delta_vector
