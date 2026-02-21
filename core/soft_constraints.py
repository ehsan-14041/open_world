"""
Soft constraints: rate_limit, diminishing returns (soft_max + softness), optional hard clip.
Change budget: scale deltas if total absolute magnitude exceeds budget.
Backward compatible: no variable_specs -> no new clipping.
Variables missing from variable_specs get DEFAULT_VARIABLE_SPEC (min/max/rate_limit) to prevent logical errors.
"""

from __future__ import annotations

from typing import Any

# Default bounds for any variable not listed in variable_specs (prevents unbounded values)
DEFAULT_VARIABLE_SPEC: dict[str, Any] = {
    "min": 0,
    "max": 100,
    "clip": True,
    "rate_limit": 10,
}


def apply_soft_constraints(
    variables: dict[str, float],
    variable_specs: dict[str, dict[str, Any]] | None,
    pending_deltas: dict[str, float],
    *,
    change_budget: float | None = None,
) -> dict[str, float]:
    """
    Apply soft constraints to pending_deltas. Returns the (possibly scaled) deltas to apply.
    Order: rate_limit per var, then change_budget, then diminishing returns, then hard clip.
    """
    if not variable_specs and change_budget is None:
        return dict(pending_deltas)

    result: dict[str, float] = {}
    for var, delta in pending_deltas.items():
        if not isinstance(delta, (int, float)):
            continue
        spec = (variable_specs or {}).get(var) or DEFAULT_VARIABLE_SPEC
        current = variables.get(var, 0.0)
        if not isinstance(current, (int, float)):
            current = 0.0

        # 1. Rate limit (spec may be from variable_specs or DEFAULT_VARIABLE_SPEC)
        if isinstance(spec.get("rate_limit"), (int, float)):
            rl = float(spec["rate_limit"])
            if abs(delta) > rl:
                delta = rl if delta > 0 else -rl

        result[var] = float(delta)

    # 2. Change budget: scale down proportionally if exceeded
    if change_budget is not None and change_budget > 0:
        total = sum(abs(v) for v in result.values())
        if total > change_budget:
            scale = change_budget / total
            for k in result:
                result[k] = result[k] * scale

    # 3. Diminishing returns: scale delta as value approaches soft_max
    for var, delta in list(result.items()):
        spec = (variable_specs or {}).get(var) or DEFAULT_VARIABLE_SPEC
        soft_max = spec.get("soft_max")
        softness = spec.get("softness")
        if soft_max is not None and softness is not None and isinstance(softness, (int, float)):
            current = variables.get(var, 0.0)
            if not isinstance(current, (int, float)):
                current = 0.0
            # Diminishing returns: scale factor decreases as current approaches soft_max
            if delta > 0 and current < soft_max:
                gap = soft_max - current
                if gap > 0:
                    # Scale factor: 1 when far, 0 when at soft_max
                    scale = min(1.0, (gap / (soft_max * 0.5 + 1e-6)) ** float(softness))
                    result[var] = delta * scale
            elif delta < 0 and current > soft_max:
                # Allow decrease when above soft_max
                pass

    return result


def apply_hard_clip(
    variables: dict[str, float],
    variable_specs: dict[str, dict[str, Any]] | None,
    pending_deltas: dict[str, float],
) -> dict[str, float]:
    """
    Apply hard clip (min/max) so variables stay within bounds.
    Variables missing from variable_specs use DEFAULT_VARIABLE_SPEC (min=0, max=100).
    """
    result: dict[str, float] = {}
    for var, delta in pending_deltas.items():
        if not isinstance(delta, (int, float)):
            continue
        spec = (variable_specs or {}).get(var) or DEFAULT_VARIABLE_SPEC
        current = variables.get(var, 0.0)
        if not isinstance(current, (int, float)):
            current = 0.0
        new_val = current + delta
        vmin = spec.get("min")
        vmax = spec.get("max")
        clip = spec.get("clip", False)
        if clip or vmin is not None or vmax is not None:
            if vmin is not None and isinstance(vmin, (int, float)) and new_val < vmin:
                delta = float(vmin) - current
            if vmax is not None and isinstance(vmax, (int, float)) and new_val > vmax:
                delta = float(vmax) - current
        result[var] = float(delta)
    return result


def apply_all_constraints(
    variables: dict[str, float],
    variable_specs: dict[str, dict[str, Any]] | None,
    pending_deltas: dict[str, float],
    *,
    change_budget: float | None = None,
) -> dict[str, float]:
    """
    Full pipeline: soft constraints (rate_limit, budget, diminishing returns) then hard clip.
    """
    step1 = apply_soft_constraints(variables, variable_specs, pending_deltas, change_budget=change_budget)
    return apply_hard_clip(variables, variable_specs, step1)
