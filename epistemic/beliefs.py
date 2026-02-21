"""
Belief update with ValueSpec: numeric (mean/std or min/max), ordinal/categorical (distribution), text (value, confidence).
Visibility rules and optional noise via core.observation.
"""

from __future__ import annotations

import copy
from typing import Any

try:
    from core.observation import observe
except ImportError:
    def observe(snapshot: dict, noise_scale: float = 0.0, rng: Any = None) -> dict:
        gs = snapshot.get("variables") or snapshot.get("global_state") or {}
        return {k: float(v) for k, v in (gs if isinstance(gs, dict) else {}).items() if isinstance(v, (int, float))}

DEFAULT_BELIEF_EMA_ALPHA = 0.7


def belief_state_from_observation(
    world_snapshot: dict[str, Any],
    variable_specs: dict[str, Any] | None = None,
    *,
    noise_scale: float = 0.0,
    store_distribution: bool = False,
) -> dict[str, Any]:
    """
    Build belief_state from world observation. If store_distribution and variable_specs
    has non-numeric types, store as distribution/interval; else scalar + confidence.
    """
    observed = observe(world_snapshot, noise_scale=noise_scale)
    variables = observed
    confidence = {k: 0.6 for k in variables}
    if not store_distribution or not variable_specs:
        return {"variables": dict(variables), "confidence": confidence}
    out_vars = {}
    for var, val in variables.items():
        spec = variable_specs.get(var) if isinstance(variable_specs, dict) else None
        if spec and isinstance(spec, dict) and spec.get("type") != "numeric":
            if spec.get("type") == "text":
                out_vars[var] = {"value": val, "confidence": 0.6}
            else:
                out_vars[var] = {"mean": float(val) if isinstance(val, (int, float)) else 0.0, "std": 0.1}
        else:
            out_vars[var] = val
    return {"variables": out_vars, "confidence": confidence}


def observe_and_update_beliefs(
    current_beliefs: dict[str, Any],
    world_snapshot: dict[str, Any],
    variable_specs: dict[str, Any] | None = None,
    *,
    noise_scale: float = 0.0,
    alpha: float = DEFAULT_BELIEF_EMA_ALPHA,
) -> dict[str, Any]:
    """
    Update belief_state from world observation. EMA for numeric; confidence updated.
    Returns updated beliefs dict (variables + confidence); caller can assign to memory.beliefs.
    """
    observed = observe(world_snapshot, noise_scale=noise_scale)
    if not observed:
        return copy.deepcopy(current_beliefs)
    vars_b = current_beliefs.get("variables") or {}
    conf_b = current_beliefs.get("confidence") or {}
    out_vars = dict(vars_b)
    out_conf = dict(conf_b)
    for var, val in observed.items():
        prev = vars_b.get(var)
        if prev is not None and isinstance(prev, (int, float)) and isinstance(val, (int, float)):
            out_vars[var] = alpha * float(prev) + (1 - alpha) * float(val)
        else:
            out_vars[var] = float(val) if isinstance(val, (int, float)) else val
        out_conf[var] = out_conf.get(var, 0.6)
    return {"variables": out_vars, "confidence": out_conf}
