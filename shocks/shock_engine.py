"""
Optional shock engine: probability, impact_distribution, targets, effect_mode.
When disabled, no shock sampling; deterministic given seed.
"""

from __future__ import annotations

import random
from typing import Any


def ShockSpec(
    id: str,
    probability: float,
    impact_distribution: dict[str, Any],
    targets: list[str],
    effect_mode: str = "additive",
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a shock spec dict. effect_mode: additive|multiplicative|ordinal_shift|categorical_flip."""
    return {
        "id": id,
        "probability": probability,
        "impact_distribution": impact_distribution,
        "targets": targets,
        "effect_mode": effect_mode,
        "constraints": constraints or {},
    }


def _sample_impact(dist: dict[str, Any], rng: random.Random) -> float:
    t = (dist.get("type") or "gaussian").strip().lower()
    params = dist.get("params") or {}
    if t == "gaussian":
        mu = float(params.get("mean", 0.0))
        sigma = float(params.get("std", 1.0))
        return rng.gauss(mu, sigma)
    if t == "uniform":
        a = float(params.get("min", 0.0))
        b = float(params.get("max", 1.0))
        return rng.uniform(a, b)
    if t == "categorical":
        probs = params.get("probs", [])
        outcomes = params.get("outcomes", list(range(len(probs))))
        if not probs:
            return 0.0
        return rng.choices(outcomes, weights=probs, k=1)[0]
    return 0.0


def apply_shocks_if_enabled(
    world: Any,
    shock_specs: list[dict[str, Any]],
    *,
    enabled: bool = False,
    rng: random.Random | None = None,
) -> dict[str, float]:
    """
    If enabled, sample each shock by probability and apply to world.variables (targets).
    effect_mode: additive (delta += impact), multiplicative (delta *= (1+impact)).
    Returns dict of variable -> delta applied (for traceability). When disabled, returns {}.
    """
    if not enabled or not shock_specs:
        return {}
    rng = rng or random.Random()
    variables = getattr(world, "variables", None)
    if not isinstance(variables, dict):
        return {}
    applied: dict[str, float] = {}
    for spec in shock_specs:
        if rng.random() > float(spec.get("probability", 0.0)):
            continue
        constraints = spec.get("constraints") or {}
        if constraints.get("max_frequency") is not None:
            pass  # would need turn history to enforce
        targets = spec.get("targets") or []
        impact_dist = spec.get("impact_distribution") or {}
        effect_mode = (spec.get("effect_mode") or "additive").strip().lower()
        impact = _sample_impact(impact_dist, rng)
        for var in targets:
            if var not in variables:
                continue
            current = variables.get(var)
            if isinstance(current, (int, float)):
                if effect_mode == "additive":
                    delta = impact
                elif effect_mode == "multiplicative":
                    delta = current * impact
                else:
                    delta = impact
                variables[var] = current + delta
                applied[var] = applied.get(var, 0.0) + delta
    return applied
