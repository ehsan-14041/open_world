"""
Shared deterministic physics for planning and execution: numeric_updates + propagation only.
No noise, governance, narrative, ontology, or entity/relation updates.
When ENABLE_UNCERTAINTY=False, planning and execution produce identical numeric results.
Supports stock/flow dynamics: STOCK uses decay and inertia; FLOW applies change directly.
"""

from __future__ import annotations

import copy
from typing import Any

try:
    from config.settings import (
        PROPAGATION_DECAY_FACTOR,
        PROPAGATION_SIGNIFICANCE_THRESHOLD,
        PROPAGATION_MAX_ITER,
        ENABLE_STOCK_FLOW,
    )
except ImportError:
    PROPAGATION_DECAY_FACTOR = 1.0
    PROPAGATION_SIGNIFICANCE_THRESHOLD = 1e-6
    PROPAGATION_MAX_ITER = 5
    ENABLE_STOCK_FLOW = True

try:
    from core.propagation import propagate_variable_changes
except ImportError:
    propagate_variable_changes = None  # type: ignore[misc, assignment]

try:
    from schemas.delta_schema import Delta
except ImportError:
    Delta = None  # type: ignore[misc, assignment]

try:
    from model.valuespec import clamp_value, clamp_state_to_specs, _spec_min_max
except ImportError:
    clamp_value = None  # type: ignore[misc, assignment]
    clamp_state_to_specs = None  # type: ignore[misc, assignment]
    _spec_min_max = None  # type: ignore[misc, assignment]


def _get_prop_decay() -> float:
    try:
        from config.settings import PROPAGATION_DECAY_FACTOR as decay
        return decay
    except ImportError:
        return 1.0


def _get_prop_sig() -> float:
    try:
        from config.settings import PROPAGATION_SIGNIFICANCE_THRESHOLD as sig
        return sig
    except ImportError:
        return 1e-6


def _get_max_iter() -> int:
    try:
        from config.settings import PROPAGATION_MAX_ITER as mi
        return mi
    except ImportError:
        return 5


def _get_enable_stock_flow() -> bool:
    try:
        from config.settings import ENABLE_STOCK_FLOW as esf
        return bool(esf)
    except ImportError:
        return True


def _get_spec_behavior_type(var: str, variable_specs: dict[str, dict[str, Any]] | None) -> str:
    """Return 'STOCK' or 'FLOW' for variable."""
    spec = (variable_specs or {}).get(var)
    if not spec or not isinstance(spec, dict):
        return "STOCK"
    bt = str(spec.get("behavior_type", spec.get("v_type", "STOCK"))).upper()
    if bt == "FLOW":
        return "FLOW"
    return "STOCK"


def _get_spec_inertia(var: str, variable_specs: dict[str, dict[str, Any]] | None) -> float:
    spec = (variable_specs or {}).get(var)
    if not spec or not isinstance(spec, dict):
        return 0.2
    v = spec.get("inertia")
    if isinstance(v, (int, float)):
        return max(0.0, min(1.0, float(v)))
    return 0.2


def _get_spec_decay(
    var: str,
    variable_specs: dict[str, dict[str, Any]] | None,
    current_value: float | None = None,
) -> float:
    spec = (variable_specs or {}).get(var)
    if not spec or not isinstance(spec, dict):
        # No explicit spec: the default 1% STOCK decay assumes a normalized [0,100]
        # variable bleeding toward baseline. A large-scale variable (e.g. mrr=10000)
        # is clearly on a different scale — applying default decay would erode ~1%/turn
        # (a scale-blind common-mode trend). Leave such variables un-decayed.
        if isinstance(current_value, (int, float)) and abs(current_value) > 100:
            return 0.0
        return 0.01
    v = spec.get("decay")
    if isinstance(v, (int, float)):
        return max(0.0, min(1.0, float(v)))
    return 0.01


def _identify_primary_variable(
    action_type: str | None,
    numeric_updates: dict[str, float],
    primary_variable_from_delta: str | None = None,
) -> str | None:
    """
    Identify primary variable from action_type or magnitude.
    Compatible with WorldModel._identify_primary_variable logic.
    """
    if primary_variable_from_delta and primary_variable_from_delta in numeric_updates:
        return primary_variable_from_delta
    if action_type:
        at = action_type.strip()
        if at.startswith("increase_"):
            var = at[len("increase_"):].strip()
            if var and var in numeric_updates:
                return var
        elif at.startswith("decrease_"):
            var = at[len("decrease_"):].strip()
            if var and var in numeric_updates:
                return var
    if numeric_updates:
        return max(numeric_updates.items(), key=lambda x: abs(x[1]))[0]
    return None


def _extract_numeric_updates(delta: Any) -> dict[str, float]:
    """Extract numeric_updates from Delta or dict; return float-only dict."""
    if Delta is not None and isinstance(delta, Delta):
        raw = delta.numeric_updates or {}
    elif isinstance(delta, dict):
        raw = delta.get("numeric_updates") or {}
    else:
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out


class _MinimalWorld:
    """Minimal object with .variables and .causal_links for propagation."""

    def __init__(self, variables: dict[str, float], causal_links: list[dict[str, Any]]) -> None:
        self.variables = variables
        self.causal_links = causal_links


def apply_delta_deterministic(
    state: dict[str, Any],
    delta: Any,
    causal_links: list[dict[str, Any]],
    *,
    variable_specs: dict[str, dict[str, Any]] | None = None,
    action_type: str | None = None,
    propagation_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Apply delta to state using deterministic physics only: numeric_updates + propagation.
    No noise, governance, narrative, ontology, or entity/relation updates.
    Pure function: returns new state dict (with optional propagation_trace); does not mutate input.
    Uses pre-update snapshot for propagation. For STOCK variables when ENABLE_STOCK_FLOW:
    Stock_(t+1) = Stock_t * (1 - decay) + NetFlow * (1 - inertia). FLOW: apply change directly.
    """
    # Pre-update snapshot (no mutation of input)
    variables = state.get("variables") or state.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}
    snapshot_vars = copy.deepcopy(variables)
    out = copy.deepcopy(state)
    out["variables"] = dict(snapshot_vars)
    if "global_state" in out:
        out["global_state"] = out["variables"]

    direct_changes = _extract_numeric_updates(delta)
    if not direct_changes:
        out["propagation_trace"] = []
        return out

    primary_from_delta = None
    if Delta is not None and isinstance(delta, Delta) and delta.primary_variable:
        primary_from_delta = delta.primary_variable
    elif isinstance(delta, dict) and delta.get("primary_variable"):
        primary_from_delta = delta.get("primary_variable")

    atype = action_type
    if atype is None and isinstance(delta, dict):
        atype = delta.get("action_type")
    if atype is None and Delta is not None and isinstance(delta, Delta):
        atype = getattr(delta, "action_type", None)

    primary_variable = _identify_primary_variable(atype, direct_changes, primary_from_delta)
    propagation_trace: list[dict[str, Any]] = []

    # Build net delta per variable: primary + secondary from propagation (using pre-update snapshot)
    primary_effects: dict[str, float] = {}
    secondary_effects: dict[str, float] = {}
    for var, d in direct_changes.items():
        if not isinstance(d, (int, float)):
            continue
        if var == primary_variable:
            primary_effects[var] = float(d)
        else:
            secondary_effects[var] = float(d)

    if causal_links and propagate_variable_changes is not None:
        params = propagation_params or {}
        decay_factor = params.get("decay_factor", _get_prop_decay())
        max_iter = params.get("max_hops", params.get("max_iterations", _get_max_iter()))
        minimal = _MinimalWorld(dict(snapshot_vars), list(causal_links))
        primary_effects, secondary_effects, propagation_trace = propagate_variable_changes(
            minimal,
            direct_changes,
            primary_variable=primary_variable,
            variable_specs=variable_specs,
            decay_factor=decay_factor,
            max_iterations=max_iter,
            significance_threshold=_get_prop_sig(),
        )

    # Net flow per variable (primary + secondary)
    net_delta: dict[str, float] = {}
    for var, d in primary_effects.items():
        net_delta[var] = net_delta.get(var, 0.0) + d
    for var, d in secondary_effects.items():
        net_delta[var] = net_delta.get(var, 0.0) + d

    use_stock_flow = _get_enable_stock_flow()
    specs = variable_specs or {}

    for var, net in net_delta.items():
        current = snapshot_vars.get(var, 0)
        if not isinstance(current, (int, float)):
            current = 0.0
        current = float(current)
        if use_stock_flow and _get_spec_behavior_type(var, variable_specs) == "STOCK":
            inertia = _get_spec_inertia(var, variable_specs)
            decay = _get_spec_decay(var, variable_specs, current)
            # Nonlinear saturation: marginal impact decreases near max_bound
            max_bound = None
            if _spec_min_max is not None:
                _, max_bound = _spec_min_max(specs.get(var))
            if max_bound is not None and max_bound > 0:
                normalized = min(1.0, current / max_bound)
                saturation_factor = 1.0 - normalized
                effective_delta = net * saturation_factor
            else:
                effective_delta = net
            # Stock_(t+1) = Stock_t * (1 - decay) + EffectiveFlow * (1 - inertia)
            new_val = current * (1.0 - decay) + effective_delta * (1.0 - inertia)
        else:
            # FLOW or stock/flow disabled: additive
            new_val = current + net

        if clamp_value is not None:
            spec = specs.get(var)
            new_val = clamp_value(var, new_val, spec, is_delta=False)
            if not isinstance(new_val, (int, float)):
                new_val = current + net
        out["variables"][var] = new_val

    # Mandatory post-propagation clamp: no variable may violate bounds
    if clamp_state_to_specs is not None and specs:
        out["variables"] = clamp_state_to_specs(out["variables"], specs)
    if "global_state" in out:
        out["global_state"] = out["variables"]
    out["propagation_trace"] = propagation_trace
    return out
