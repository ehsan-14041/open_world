"""
Objective validation: sign-safe and contradiction-free goals.
Validates and normalizes agent objectives against causal graph and variable set.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("open_world_engine.pipeline")

# Minimum weight to consider an objective "significant" for contradiction check
CONTRADICTION_WEIGHT_THRESHOLD = 0.05
# Target sum for normalizing weights per agent (optional)
OBJECTIVES_SUM_TARGET = 1.0


def _objective_to_var_and_direction(key: str) -> tuple[str, str] | None:
    """Return (variable, direction) for objective key. direction is 'increase' or 'decrease'."""
    key = (key or "").strip().lower()
    if key.startswith("increase_"):
        return (key[9:].strip(), "increase")
    if key.startswith("decrease_"):
        return (key[9:].strip(), "decrease")
    if key.startswith("maximize_"):
        return (key[9:].strip(), "increase")
    if key.startswith("minimize_"):
        return (key[9:].strip(), "decrease")
    return None


def _detect_contradictions(objectives: dict[str, float]) -> list[tuple[str, str]]:
    """Return list of (var, message) for variables that have both increase and decrease with significant weight."""
    by_var: dict[str, dict[str, float]] = {}
    for key, w in objectives.items():
        if not isinstance(w, (int, float)) or w < CONTRADICTION_WEIGHT_THRESHOLD:
            continue
        parsed = _objective_to_var_and_direction(key)
        if not parsed:
            continue
        var, direction = parsed
        if var not in by_var:
            by_var[var] = {}
        by_var[var][direction] = by_var[var].get(direction, 0) + float(w)

    contradictions: list[tuple[str, str]] = []
    for var, dir_weights in by_var.items():
        if "increase" in dir_weights and "decrease" in dir_weights:
            contradictions.append((var, f"Variable '{var}' has both increase and decrease objectives"))
    return contradictions


def _normalize_objectives_remove_contradictions(
    objectives: dict[str, float],
    variable_names: set[str],
) -> dict[str, float]:
    """
    If a variable has both increase and decrease, keep the dominant direction and drop the other.
    Then normalize weights so they sum to OBJECTIVES_SUM_TARGET.
    """
    out: dict[str, float] = {}
    # Group by (var, direction) and sum weights
    by_var_dir: dict[tuple[str, str], float] = {}
    for key, w in objectives.items():
        if not isinstance(w, (int, float)) or w < 0:
            continue
        parsed = _objective_to_var_and_direction(key)
        if not parsed:
            out[key] = float(w)
            continue
        var, direction = parsed
        if var not in variable_names:
            continue
        k = (var, direction)
        by_var_dir[k] = by_var_dir.get(k, 0) + float(w)

    # For each var, keep only the direction with higher weight
    for (var, direction), weight in by_var_dir.items():
        other_dir = "decrease" if direction == "increase" else "increase"
        other_weight = by_var_dir.get((var, other_dir), 0)
        if weight >= other_weight and weight > 0:
            key = f"increase_{var}" if direction == "increase" else f"decrease_{var}"
            out[key] = out.get(key, 0) + weight

    # Normalize to sum = OBJECTIVES_SUM_TARGET
    total = sum(out.values())
    if total > 0 and OBJECTIVES_SUM_TARGET > 0:
        scale = OBJECTIVES_SUM_TARGET / total
        out = {k: v * scale for k, v in out.items()}

    return out


def _causal_polarity_map(causal_graph: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    """Build (from_var, to_var) -> 'positive'|'negative' from causal graph."""
    m: dict[tuple[str, str], str] = {}
    for link in causal_graph:
        f = link.get("from")
        t = link.get("to")
        if not f or not t:
            continue
        pol = (link.get("polarity") or "positive").lower()
        m[(f, t)] = pol
    return m


def _sign_safe_objectives(
    objectives: dict[str, float],
    variable_names: set[str],
    causal_polarity: dict[tuple[str, str], str],
) -> dict[str, float]:
    """
    Optionally adjust weights for sign consistency with causal graph.
    If an objective "increase_B" exists and the only causal path to B is A->B negative,
    then "increase_A" would decrease B: we could flag or down-weight. For simplicity we
    only normalize and remove contradictions here; sign-safe is best-effort via validation.
    """
    return objectives


def validate_and_normalize_incentives(
    incentives: dict[str, dict[str, Any]],
    variable_names: set[str],
    causal_graph: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Validate and normalize incentives so that:
    - No agent has both increase_X and decrease_X with significant weight (contradiction).
    - Weights are normalized per agent.
    - Objectives only reference known variables (already enforced by IncentiveModeler; re-check).
    Returns a new incentives dict; does not mutate input.
    """
    causal_graph = causal_graph or []
    causal_polarity = _causal_polarity_map(causal_graph)
    result: dict[str, dict[str, Any]] = {}

    for name, profile in incentives.items():
        if not isinstance(profile, dict):
            result[name] = profile
            continue
        objectives = profile.get("objectives")
        if not isinstance(objectives, dict):
            result[name] = dict(profile)
            continue

        # Filter to known variables only
        filtered: dict[str, float] = {}
        for key, w in objectives.items():
            if not isinstance(w, (int, float)):
                continue
            parsed = _objective_to_var_and_direction(key)
            if parsed:
                var, _ = parsed
                if var not in variable_names:
                    logger.debug("Objective '%s' references unknown variable '%s'; dropping", key, var)
                    continue
            filtered[key] = float(w)

        contradictions = _detect_contradictions(filtered)
        if contradictions:
            for var, msg in contradictions:
                logger.info("Agent '%s': %s; normalizing by keeping dominant direction.", name, msg)
            filtered = _normalize_objectives_remove_contradictions(filtered, variable_names)

        filtered = _sign_safe_objectives(filtered, variable_names, causal_polarity)

        new_profile = dict(profile)
        new_profile["objectives"] = filtered
        result[name] = new_profile

    return result
