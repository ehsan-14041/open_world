"""
Legacy semantics: compatibility layer for variable-name-based and domain-inferred behavior.
All name-based inference (non-negative, protected, steady action, strategy class, goal direction)
lives here so core can prefer declarative metadata (variable_specs, ValueSpec) and fall back
to this module only when needed. Do not add new domain keywords here; prefer scenario variable_specs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# --- Non-negative variable inference (legacy) ---

NON_NEGATIVE_KEYWORDS: set[str] = {
    "population",
    "count",
    "resource",
    "cash",
    "money",
    "fund",
    "stock",
    "inventory",
    "supply",
    "runway",
}


def legacy_infer_non_negative_variables(variable_names: list[str]) -> set[str]:
    """
    Infer which variables should be treated as non-negative from their names.
    Used when scenario variable_specs do not set non_negative explicitly.
    """
    result: set[str] = set()
    for name in variable_names or []:
        if not isinstance(name, str):
            continue
        v = name.lower()
        if any(kw in v for kw in NON_NEGATIVE_KEYWORDS):
            result.add(name)
    return result


def legacy_is_non_negative_variable(var_name: str) -> bool:
    """Single-variable check for legacy callers (e.g. guard). Prefer variable_specs when available."""
    if not var_name or not isinstance(var_name, str):
        return False
    v = var_name.lower()
    return any(kw in v for kw in NON_NEGATIVE_KEYWORDS)


# --- Protected keys (policy) ---

_DEFAULT_PROTECTED_KEYS = ["population", "people"]


def legacy_protected_keys() -> list[str]:
    """
    Return protected variable keys from config/policy_default.json.
    Used when no policy is supplied to WorldState or when scenario does not override.
    """
    base = Path(__file__).resolve().parent.parent
    path = base / "config" / "policy_default.json"
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                keys = data.get("protected_keys")
                if isinstance(keys, list):
                    return [str(k) for k in keys if k]
        except (json.JSONDecodeError, OSError):
            pass
    return list(_DEFAULT_PROTECTED_KEYS)


def legacy_default_policy() -> dict[str, Any]:
    """Return full default policy dict (protected_keys, caps, max_magnitude). Matches world_state.DEFAULT_POLICY shape."""
    base = Path(__file__).resolve().parent.parent
    path = base / "config" / "policy_default.json"
    default: dict[str, Any] = {
        "protected_keys": _DEFAULT_PROTECTED_KEYS,
        "caps": {"churn": [0, 1]},
        "max_magnitude": 1e7,
    }
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                default.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return default


# --- Steady / default action name (planner) ---

def legacy_steady_action_name() -> str:
    """
    Default second-step action for depth-2 planning when no scenario-specific steady action.
    """
    return "steady_finance"


# --- Action type -> strategy class (base_agent) ---

def legacy_strategy_class_from_action_type(action_type: str) -> str:
    """
    Map action_type string to strategy class label from name patterns.
    Used when scenario strategy_classes do not define the action. Do not add new domain patterns here.
    """
    if not action_type or not isinstance(action_type, str):
        return "default"
    at = action_type.lower()
    if at.startswith("launch_") or (at.startswith("increase_") and "growth" in at) or "growth" in at:
        return "growth"
    if at.startswith("steady_") or "conserve" in at or "finance" in at:
        return "conservation"
    if at.startswith("propose_") or at.startswith("form_") or "regulation" in at or "governance" in at:
        return "governance"
    if at.startswith("request_") or "investment" in at:
        return "investment"
    return "default"


# --- Goal / objective string -> (variable, direction) ---

def legacy_goal_to_var_direction(goal_str: str) -> tuple[str, int] | None:
    """
    Map goal or objective key to (variable_name, direction). direction: +1 = higher better, -1 = lower better.
    Parses increase_/decrease_/maximize_/minimize_/reduce_ prefixes. Used by utility and narrative_engine.
    """
    if not goal_str or not isinstance(goal_str, str):
        return None
    o = goal_str.lower().strip()
    if o.startswith("increase_") or o.startswith("maximize_"):
        var = o.replace("increase_", "").replace("maximize_", "").strip()
        return (var, 1) if var else None
    if o.startswith("decrease_") or o.startswith("reduce_") or o.startswith("minimize_"):
        var = o.replace("decrease_", "").replace("reduce_", "").replace("minimize_", "").strip()
        return (var, -1) if var else None
    # Plain variable name: higher is better
    return (goal_str, 1)


def legacy_fallback_action_for_variables(variables: dict[str, Any]) -> str:
    """
    Fallback action when no candidates available. Uses first variable for increase_{var} or 'adjust_variable'.
    """
    if not variables or not isinstance(variables, dict):
        return "adjust_variable"
    first_var = next(iter(variables.keys()), None)
    if first_var:
        return f"increase_{first_var}"
    return "adjust_variable"
