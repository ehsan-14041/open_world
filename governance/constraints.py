"""
Hard/soft constraints. Re-exports core.soft_constraints and adds ValueSpec adapter.
Domain-agnostic; variable_specs can be legacy (min, max, clip, rate_limit) or from ValueSpec.
"""

from __future__ import annotations

from typing import Any

from core.soft_constraints import (
    apply_soft_constraints as _apply_soft_constraints,
    apply_hard_clip as _apply_hard_clip,
    apply_all_constraints as _apply_all_constraints,
)


def variable_specs_from_valuespecs(
    value_specs: dict[str, Any] | None,
) -> dict[str, dict[str, Any]] | None:
    """
    Convert ValueSpec-style dicts (type, scale, ordinal_labels, etc.) to legacy
    variable_specs (min, max, clip, rate_limit) for constraint functions.
    """
    if not value_specs:
        return None
    out = {}
    for var_id, spec in value_specs.items():
        if not isinstance(spec, dict):
            continue
        leg = {}
        scale = spec.get("scale")
        if isinstance(scale, dict):
            if scale.get("min") is not None:
                leg["min"] = float(scale["min"])
            if scale.get("max") is not None:
                leg["max"] = float(scale["max"])
        if spec.get("rate_limit") is not None:
            leg["rate_limit"] = float(spec["rate_limit"])
        if spec.get("soft_max") is not None:
            leg["soft_max"] = float(spec["soft_max"])
        if spec.get("softness") is not None:
            leg["softness"] = float(spec["softness"])
        clamp = spec.get("clamp")
        if isinstance(clamp, dict) or spec.get("clip"):
            leg["clip"] = True
        if leg or spec.get("min") is not None or spec.get("max") is not None:
            leg.setdefault("min", spec.get("min"))
            leg.setdefault("max", spec.get("max"))
            out[var_id] = leg
    return out if out else None


def apply_soft_constraints(
    variables: dict[str, float],
    variable_specs: dict[str, dict[str, Any]] | None,
    pending_deltas: dict[str, float],
    *,
    change_budget: float | None = None,
) -> dict[str, float]:
    """Apply soft constraints (rate_limit, change_budget, diminishing returns)."""
    return _apply_soft_constraints(
        variables,
        variable_specs,
        pending_deltas,
        change_budget=change_budget,
    )


def apply_hard_clip(
    variables: dict[str, float],
    variable_specs: dict[str, dict[str, Any]] | None,
    pending_deltas: dict[str, float],
) -> dict[str, float]:
    """Apply hard clip (min/max)."""
    return _apply_hard_clip(variables, variable_specs, pending_deltas)


def apply_all_constraints(
    variables: dict[str, float],
    variable_specs: dict[str, dict[str, Any]] | None,
    pending_deltas: dict[str, float],
    *,
    change_budget: float | None = None,
) -> dict[str, float]:
    """Full pipeline: soft then hard clip."""
    return _apply_all_constraints(
        variables,
        variable_specs,
        pending_deltas,
        change_budget=change_budget,
    )
