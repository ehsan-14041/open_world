"""
Generic rule engine: scenario-defined rules keyed by condition_key and effect_key.
Domain-agnostic: core only evaluates conditions and runs effects; scenario or domain loaders register implementations.
Rules are { "id": str, "condition_key": str, "effect_key": str, "params": {} }; registry maps keys to callables.
"""

from __future__ import annotations

from typing import Any, Callable


# Registry: condition_key -> (snapshot -> bool), effect_key -> (world, params) -> None or delta dict
_condition_registry: dict[str, Callable[[dict[str, Any]], bool]] = {}
_effect_registry: dict[str, Callable[[Any, dict[str, Any]], None | dict[str, Any]]] = {}


def register_condition(key: str, fn: Callable[[dict[str, Any]], bool]) -> None:
    """Register a condition callable for the given key. Used by scenario/domain loaders."""
    _condition_registry[key] = fn


def register_effect(key: str, fn: Callable[[Any, dict[str, Any]], None | dict[str, Any]]) -> None:
    """Register an effect callable (world, params) -> None or delta. Used by scenario/domain loaders."""
    _effect_registry[key] = fn


def get_registry_counts() -> tuple[int, int]:
    """Return (condition_registry_count, effect_registry_count) for health check."""
    return len(_condition_registry), len(_effect_registry)


def run_rules(
    snapshot: dict[str, Any],
    world: Any,
    rules: list[dict[str, Any]],
    *,
    max_rule_activations_per_turn: int = 100,
) -> list[dict[str, Any]]:
    """
    Evaluate each rule: if condition(snapshot) then run effect(world, params). One-shot per rule per turn.
    Returns list of activated rule records for trace: [{"id": str, "condition_key": str, "effect_key": str}, ...].
    """
    activated: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("id", "")
        cond_key = rule.get("condition_key")
        effect_key = rule.get("effect_key")
        params = rule.get("params") or {}
        if not cond_key or not effect_key:
            continue
        cond_fn = _condition_registry.get(cond_key)
        effect_fn = _effect_registry.get(effect_key)
        if cond_fn is None or effect_fn is None:
            continue
        try:
            if not cond_fn(snapshot):
                continue
        except Exception:
            continue
        try:
            result = effect_fn(world, params)
            if isinstance(result, dict) and hasattr(world, "apply_delta"):
                from schemas.delta_schema import Delta
                world.apply_delta(Delta.from_dict(result))
        except Exception:
            pass
        activated.append({"id": rule_id, "condition_key": cond_key, "effect_key": effect_key})
        if len(activated) >= max_rule_activations_per_turn:
            break
    return activated
