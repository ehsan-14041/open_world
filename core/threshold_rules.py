"""
Generic, declarative threshold/non-linear primitives for the rule engine.

This is the engine's non-linearity mechanism: it lets any scenario JSON express a
tipping point WITHOUT writing Python. Without it, the linear delta-propagation core
can only produce smooth gradients — it cannot model a phase transition / cascade
failure (see the Path A finding in tests/test_failure_mode_bimodality.py).

A scenario rule looks like:
    {
      "id": "churn_cliff",
      "condition_key": "var_above",
      "effect_key": "scale_var",
      "params": {"var": "churn_rate", "threshold": 0.45, "target": "mrr", "factor": 0.6}
    }
Condition reads `var`/`threshold`; effect reads `target`/`factor` (or `amount`).
Both share the rule's single `params` dict.

Primitives are registered on import. `simulation/loop.py` imports this module so the
primitives are always available when a simulation runs.
"""

from __future__ import annotations

from typing import Any

from core.rule_engine import register_condition, register_effect


def _read_var(snapshot: dict[str, Any], var: str) -> float | None:
    """Read a numeric variable from a world snapshot (variables or global_state)."""
    if not isinstance(snapshot, dict) or not var:
        return None
    vars_ = snapshot.get("variables")
    if not isinstance(vars_, dict):
        vars_ = snapshot.get("global_state") or {}
    v = vars_.get(var)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _world_value(world: Any, var: str) -> float | None:
    """Read a numeric variable's current value from the world."""
    store = getattr(world, "variables", None)
    if not isinstance(store, dict):
        store = getattr(world, "global_state", None)
    if not isinstance(store, dict):
        return None
    v = store.get(var)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ---------------- conditions ----------------

def cond_var_above(snapshot: dict[str, Any], params: dict[str, Any]) -> bool:
    """True when params['var'] > params['threshold']."""
    var = params.get("var")
    threshold = params.get("threshold")
    val = _read_var(snapshot, str(var)) if var is not None else None
    if val is None or not isinstance(threshold, (int, float)):
        return False
    return val > float(threshold)


def cond_var_below(snapshot: dict[str, Any], params: dict[str, Any]) -> bool:
    """True when params['var'] < params['threshold']."""
    var = params.get("var")
    threshold = params.get("threshold")
    val = _read_var(snapshot, str(var)) if var is not None else None
    if val is None or not isinstance(threshold, (int, float)):
        return False
    return val < float(threshold)


# ---------------- effects ----------------

def effect_scale_var(world: Any, params: dict[str, Any]) -> dict[str, Any] | None:
    """
    Multiplicative shock: target *= factor. Returned as an additive delta
    (current*(factor-1)) so the world's additive apply_delta yields current*factor.
    Bypasses the smooth propagation chain — this is the cascade.
    """
    target = params.get("target") or params.get("var")
    factor = params.get("factor")
    if target is None or not isinstance(factor, (int, float)):
        return None
    current = _world_value(world, str(target))
    if current is None:
        return None
    delta = current * (float(factor) - 1.0)
    return {
        "numeric_updates": {str(target): delta},
        "rationale": f"threshold cascade: {target} *= {factor}",
    }


def effect_add_to_var(world: Any, params: dict[str, Any]) -> dict[str, Any] | None:
    """Additive shock: target += amount."""
    target = params.get("target") or params.get("var")
    amount = params.get("amount")
    if target is None or not isinstance(amount, (int, float)):
        return None
    return {
        "numeric_updates": {str(target): float(amount)},
        "rationale": f"threshold shock: {target} += {amount}",
    }


_REGISTERED = False


def register_threshold_primitives() -> None:
    """Register all threshold primitives into the rule engine (idempotent)."""
    global _REGISTERED
    if _REGISTERED:
        return
    register_condition("var_above", cond_var_above)
    register_condition("var_below", cond_var_below)
    register_effect("scale_var", effect_scale_var)
    register_effect("add_to_var", effect_add_to_var)
    _REGISTERED = True


# Register on import so primitives are available wherever rules run.
register_threshold_primitives()
