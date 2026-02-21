"""
Generic action interpreter: maps abstract action_spec to Delta. No domain logic—only increase_variable, decrease_variable, set_variable.
Supports probabilistic uncertainty: variance and success_probability when enable_uncertainty is True.
"""

from __future__ import annotations

import random
from typing import Any

from config.settings import ENABLE_UNCERTAINTY, RANDOM_SEED
from schemas.delta_schema import Delta

# Seed random if RANDOM_SEED is provided
if RANDOM_SEED is not None:
    random.seed(RANDOM_SEED)


def _parse_magnitude(magnitude: Any, default: float = 5.0) -> float:
    try:
        return float(magnitude)
    except (TypeError, ValueError):
        return default


def interpret_action_spec(
    action_spec: dict[str, Any],
    *,
    variable_tradeoffs: dict[str, dict[str, float]] | None = None,
) -> Delta | None:
    """
    Interpret abstract action_spec into a Delta. Supported types:
    - increase_variable, decrease_variable, set_variable (target + magnitude)
    - adjust_variable: variable, direction ("increase"|"decrease"), magnitude (domain-agnostic)
    No hardcoded variable names; target and magnitude come from the spec.
    When variable_tradeoffs is provided and the delta would have a single variable, secondary
    effects are merged from variable_tradeoffs[primary_var] so every action affects at least two variables.
    """
    if not isinstance(action_spec, dict):
        return None

    # Support nested "effect" format for backward compatibility
    effect = action_spec.get("effect")
    if effect and isinstance(effect, dict):
        spec = dict(action_spec)
        spec["type"] = effect.get("type") or spec.get("type")
        spec["target"] = effect.get("variable") or spec.get("target")
        spec["variable"] = effect.get("variable") or spec.get("variable")
        spec["magnitude"] = effect.get("value") or spec.get("magnitude")
        spec["direction"] = effect.get("direction") or spec.get("direction")
        spec["variance"] = effect.get("variance") or spec.get("variance")
        spec["success_probability"] = effect.get("success_probability") or spec.get("success_probability")
        action_spec = spec

    action_type = (action_spec.get("type") or "").strip().lower()
    target = action_spec.get("target") or action_spec.get("variable")
    magnitude = _parse_magnitude(action_spec.get("magnitude"), 5.0)
    variance = action_spec.get("variance")
    success_probability = action_spec.get("success_probability")

    # adjust_variable: { "action_type": "adjust_variable", "variable": "tensions", "direction": "increase", "magnitude": 5 }
    if action_type == "adjust_variable":
        var = action_spec.get("variable") or target
        direction = (action_spec.get("direction") or "increase").strip().lower()
        if not var or not isinstance(var, str):
            return None
        if direction in ("increase", "up", "raise", "1"):
            action_type = "increase_variable"
            target = var
        elif direction in ("decrease", "down", "lower", "reduce", "-1"):
            action_type = "decrease_variable"
            target = var
        else:
            return None

    if not target or not isinstance(target, str):
        return None

    # Apply success probability if uncertainty is enabled
    if ENABLE_UNCERTAINTY and success_probability is not None:
        try:
            prob = float(success_probability)
            if prob < 0.0 or prob > 1.0:
                prob = 1.0
            if random.random() > prob:
                return None
        except (TypeError, ValueError):
            pass

    # Apply variance if uncertainty is enabled
    if ENABLE_UNCERTAINTY and variance is not None:
        try:
            var = float(variance)
            if var < 0:
                var = 0.0
            noise = random.uniform(-var, var)
            magnitude = magnitude + noise
        except (TypeError, ValueError):
            pass

    numeric_updates: dict[str, float] = {}
    if action_type == "increase_variable":
        numeric_updates[target] = magnitude
    elif action_type == "decrease_variable":
        numeric_updates[target] = -magnitude
    elif action_type == "set_variable":
        return None  # Use interpret_action_spec_with_world for set_variable
    else:
        return None

    if not numeric_updates:
        return None

    # Tradeoff: ensure at least two variables when variable_tradeoffs provided
    if variable_tradeoffs and len(numeric_updates) == 1:
        for primary_var in list(numeric_updates.keys()):
            secondary = variable_tradeoffs.get(primary_var) or {}
            if isinstance(secondary, dict):
                for k, v in secondary.items():
                    if isinstance(v, (int, float)):
                        numeric_updates[k] = numeric_updates.get(k, 0) + float(v)
            break

    return Delta(
        numeric_updates=numeric_updates,
        entity_updates={},
        new_entities={},
        relation_updates=[],
        meta_proposals=[],
        rationale=f"Action: {action_type} {target}",
        effects_duration=None,
        mitigation=None,
    )


def _apply_fallback_tradeoff(
    numeric_updates: dict[str, float],
    world_snapshot: dict[str, Any],
) -> None:
    """When numeric_updates has only one key, add a secondary cost from world variables if possible."""
    if len(numeric_updates) >= 2:
        return
    variables = world_snapshot.get("variables") or world_snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        return
    # Prefer generic cost-like variables for secondary effect
    cost_vars = [v for v in variables if v and isinstance(v, str) and (
        "stress" in v.lower() or "cost" in v.lower() or "strain" in v.lower()
        or "dissatisfaction" in v.lower() or "budget" in v.lower()
    )]
    if not cost_vars:
        # Any other variable except the one we're already changing
        primary = next(iter(numeric_updates.keys()), None)
        cost_vars = [v for v in variables if v != primary]
    if cost_vars:
        secondary_var = cost_vars[0]
        numeric_updates[secondary_var] = numeric_updates.get(secondary_var, 0) + 3.0  # small cost


def interpret_action_spec_with_world(
    action_spec: dict[str, Any],
    world_snapshot: dict[str, Any],
    *,
    action_type: str | None = None,
    action_tradeoffs: dict[str, dict[str, float]] | None = None,
    variable_tradeoffs: dict[str, dict[str, float]] | None = None,
) -> Delta | None:
    """
    Like interpret_action_spec but supports set_variable (computes delta from current value).
    Also supports uncertainty fields: variance and success_probability.
    Optional action_tradeoffs (action_type -> secondary vars) and variable_tradeoffs (var -> secondary)
    ensure at least two variables are affected when scenario supplies tradeoff specs.
    """
    if not isinstance(action_spec, dict):
        return None

    # Support nested "effect" format for backward compatibility
    effect = action_spec.get("effect")
    if effect and isinstance(effect, dict):
        # Map nested format to legacy format
        spec = dict(action_spec)
        spec["type"] = effect.get("type") or spec.get("type")
        spec["target"] = effect.get("variable") or spec.get("target")
        spec["magnitude"] = effect.get("value") or spec.get("magnitude")
        spec["value"] = effect.get("value") or spec.get("value")
        spec["variance"] = effect.get("variance") or spec.get("variance")
        spec["success_probability"] = effect.get("success_probability") or spec.get("success_probability")
        action_spec = spec

    spec_action_type = action_spec.get("type")
    target = action_spec.get("target")
    variance = action_spec.get("variance")
    success_probability = action_spec.get("success_probability")
    
    variables = world_snapshot.get("variables") or world_snapshot.get("global_state") or {}
    current = variables.get(target, 0) if isinstance(variables, dict) else 0
    try:
        cur = float(current)
    except (TypeError, ValueError):
        cur = 0.0
    
    # Apply success probability if uncertainty is enabled
    if ENABLE_UNCERTAINTY and success_probability is not None:
        try:
            prob = float(success_probability)
            if prob < 0.0 or prob > 1.0:
                prob = 1.0  # Invalid probability, treat as always succeed
            if random.random() > prob:
                # Action fails - return None
                return None
        except (TypeError, ValueError):
            pass  # Invalid success_probability, ignore
    
    if spec_action_type == "set_variable":
        value = action_spec.get("value", 0)
        try:
            v = float(value)
        except (TypeError, ValueError):
            v = 0.0

        # Apply variance if uncertainty is enabled
        if ENABLE_UNCERTAINTY and variance is not None:
            try:
                var = float(variance)
                if var < 0:
                    var = 0.0
                # Apply uniform random noise: ±variance
                noise = random.uniform(-var, var)
                v = v + noise
            except (TypeError, ValueError):
                pass  # Invalid variance, ignore

        numeric_updates = {target: v - cur}
        # Tradeoff: add secondary effects
        if variable_tradeoffs and target in variable_tradeoffs:
            for k, d in (variable_tradeoffs.get(target) or {}).items():
                if isinstance(d, (int, float)):
                    numeric_updates[k] = numeric_updates.get(k, 0) + float(d)
        if action_type and action_tradeoffs and action_type in action_tradeoffs:
            for k, d in (action_tradeoffs.get(action_type) or {}).items():
                if isinstance(d, (int, float)):
                    numeric_updates[k] = numeric_updates.get(k, 0) + float(d)
        if len(numeric_updates) < 2:
            _apply_fallback_tradeoff(numeric_updates, world_snapshot)

        return Delta(
            numeric_updates=numeric_updates,
            entity_updates={},
            new_entities={},
            relation_updates=[],
            meta_proposals=[],
            rationale=f"Action: set_variable {target}",
            effects_duration=None,
            mitigation=None,
        )

    delta = interpret_action_spec(action_spec, variable_tradeoffs=variable_tradeoffs)
    if delta is None:
        return None
    numeric_updates = dict(delta.numeric_updates or {})
    if action_type and action_tradeoffs and action_type in action_tradeoffs:
        for k, d in (action_tradeoffs.get(action_type) or {}).items():
            if isinstance(d, (int, float)):
                numeric_updates[k] = numeric_updates.get(k, 0) + float(d)
    if len(numeric_updates) < 2:
        _apply_fallback_tradeoff(numeric_updates, world_snapshot)
    return Delta(
        numeric_updates=numeric_updates,
        entity_updates=delta.entity_updates or {},
        new_entities=delta.new_entities or {},
        relation_updates=delta.relation_updates or [],
        meta_proposals=delta.meta_proposals or [],
        rationale=delta.rationale or "",
        effects_duration=delta.effects_duration,
        mitigation=delta.mitigation,
    )
