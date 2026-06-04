"""
Goals and utility model: utility_function(world_state, beliefs), default goals from objectives.
Rule-based scoring for dry-run and planning. Domain-agnostic: goals and utility derive from
variable names and directional objectives (increase_X, decrease_X).
"""

from __future__ import annotations

from typing import Any

from core.legacy_semantics import legacy_goal_to_var_direction

# Default normalization range for any variable not in map
DEFAULT_RANGE = (0, 100)

# Backward compat: used by base_agent when variable_specs not available
DEFAULT_NORM_RANGES: dict[str, tuple[float, float]] = {
    "growth": (0, 100),
    "cash": (0, 500_000),
    "runway_months": (0, 36),
    "population": (0, 10_000),
    "engagement": (0, 100),
    "trust": (0, 100),
}


def ranges_from_variable_specs(variable_specs: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Build norm_ranges from variable_specs (min, max) when available."""
    out: dict[str, tuple[float, float]] = {}
    for var, spec in (variable_specs or {}).items():
        if not isinstance(spec, dict):
            continue
        min_v = spec.get("min")
        max_v = spec.get("max")
        if isinstance(min_v, (int, float)) and isinstance(max_v, (int, float)):
            out[var] = (float(min_v), float(max_v))
    return out


def _norm(value: float, low: float, high: float) -> float:
    """Clamp and normalize to [0, 1] for range [low, high]."""
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _get_range(key: str, norm_ranges: dict[str, tuple[float, float]]) -> tuple[float, float]:
    """Return (low, high) for variable key; use DEFAULT_RANGE if unknown."""
    return norm_ranges.get(key, DEFAULT_RANGE)


def goals_from_objectives(objectives: dict[str, float]) -> list[str]:
    """Auto-generate long_term_goals from objectives keys. Domain-agnostic: keys are goal names (e.g. increase_X, decrease_Y)."""
    return [k for k in objectives.keys() if k and objectives.get(k, 0) != 0]


def evaluate_short_term_goals(
    long_term_goals: list[str],
    world_state: dict[str, Any],
) -> list[str]:
    """Derive short_term_goals from long_term_goals and current state. Variable-agnostic: low value -> prioritize increase_X; high -> prioritize decrease_X."""
    gs = world_state.get("global_state", world_state.get("variables", world_state)) if isinstance(world_state, dict) else {}
    if not isinstance(gs, dict):
        return list(long_term_goals)
    short: list[str] = []
    for g in long_term_goals:
        if not isinstance(g, str):
            continue
        g_lower = g.lower()
        if g_lower.startswith("increase_") or g_lower.startswith("maximize_"):
            var = g_lower.replace("increase_", "").replace("maximize_", "").strip()
            val = gs.get(var)
            if isinstance(val, (int, float)):
                low, high = _get_range(var, {})
                mid = (low + high) / 2
                if val < mid:
                    short.append(g)
                else:
                    short.append(g)
            else:
                short.append(g)
        elif g_lower.startswith("decrease_") or g_lower.startswith("reduce_") or g_lower.startswith("minimize_"):
            var = g_lower.replace("decrease_", "").replace("reduce_", "").replace("minimize_", "").strip()
            val = gs.get(var)
            if isinstance(val, (int, float)):
                low, high = _get_range(var, {})
                mid = (low + high) / 2
                if val > mid:
                    short.append(g)
                else:
                    short.append(g)
            else:
                short.append(g)
        else:
            short.append(g)
    return short if short else list(long_term_goals)


def _objective_to_state_and_direction(obj_key: str) -> tuple[str, int] | None:
    """Map objective key to (state_variable, direction). Uses legacy_goal_to_var_direction."""
    return legacy_goal_to_var_direction(obj_key)


def utility_function(
    world_state: dict[str, Any],
    beliefs: dict[str, Any],
    objectives: dict[str, float],
    *,
    norm_ranges: dict[str, tuple[float, float]] | None = None,
    variable_specs: dict[str, Any] | None = None,
    personality_modifiers: dict[str, float] | None = None,
) -> float:
    """
    Numeric score from world_state and beliefs using objective weights. Domain-agnostic.
    When variable_specs is provided, uses ValueSpec adapters (to_scalar_for_utility) for ordinal/categorical/unknown.
    personality_modifiers: risk_aversion, loss_aversion, volatility_preference, bias_factor (0..1 scale).
    """
    ranges = norm_ranges or {}
    gs = world_state.get("global_state", world_state.get("variables", world_state)) if isinstance(world_state, dict) else {}
    if not isinstance(gs, dict):
        gs = {}
    use_valuespec = isinstance(variable_specs, dict) and variable_specs
    score = 0.0
    total_weight = 0.0
    for obj_key, weight in objectives.items():
        if weight <= 0:
            continue
        mapped = _objective_to_state_and_direction(obj_key)
        if not mapped:
            continue
        state_key, direction = mapped
        value = gs.get(state_key)
        if use_valuespec:
            try:
                from model.valuespec import to_scalar_for_utility
                scalar = to_scalar_for_utility(state_key, value, variable_specs.get(state_key))
                norm_val = _norm(scalar, 0.0, 100.0)
            except Exception:
                if isinstance(value, (int, float)):
                    low, high = _get_range(state_key, ranges)
                    norm_val = _norm(float(value), low, high)
                else:
                    continue
        else:
            if not isinstance(value, (int, float)):
                continue
            low, high = _get_range(state_key, ranges)
            norm_val = _norm(float(value), low, high)
        if direction < 0:
            norm_val = 1.0 - norm_val
        score += weight * norm_val
        total_weight += weight
    if total_weight <= 0:
        return 0.0
    raw = score / total_weight
    mods = personality_modifiers or {}
    risk = mods.get("risk_aversion", 0.0)
    loss = mods.get("loss_aversion", 0.0)
    if risk > 0 and raw < 0.5:
        raw = raw * (1.0 - risk) + 0.5 * risk
    if loss > 0 and raw < 0.5:
        raw = raw - loss * 0.1
    return max(0.0, min(1.0, raw))


def score_action_rule_based(
    action_type: str,
    world_state: dict[str, Any],
    objectives: dict[str, float],
    rule_based_deltas: dict[str, dict[str, float]],
) -> float:
    """
    Score a single action by applying its rule-based delta to a copy of global_state
    and returning utility of the resulting state. Used in dry-run and planner.
    Domain-agnostic: rule_based_deltas can be variable-driven (e.g. increase_X -> {X: 5}).
    """
    gs = (world_state.get("global_state") or world_state.get("variables") or {}) if isinstance(world_state, dict) else {}
    gs = dict(gs)
    delta = rule_based_deltas.get(action_type, {})
    for k, v in delta.items():
        if isinstance(v, (int, float)):
            gs[k] = gs.get(k, 0) + v
    return utility_function({"global_state": gs, "variables": gs}, {}, objectives)
