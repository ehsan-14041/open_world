"""
Structured decision input schema for the Strategic Decision Intelligence layer.

A DecisionInput captures the *who, what, and when* of a business decision so
the engine can tailor drivers, effects, and kill criteria to that specific move
rather than to the generic scenario narrative.
"""

from __future__ import annotations

from typing import Any


VALID_HORIZONS = (3, 6, 12, 24)


def validate_decision_input(data: Any) -> list[str]:
    """Return a list of validation error messages; empty list means valid."""
    if not isinstance(data, dict):
        return ["decision_input must be a JSON object"]
    errors: list[str] = []

    move = (data.get("move") or "").strip()
    if not move:
        errors.append("'move' is required — describe the decision being analyzed")

    actors = data.get("actors")
    if actors is not None:
        if not isinstance(actors, list):
            errors.append("'actors' must be an array of strings")
        else:
            for i, a in enumerate(actors):
                if not isinstance(a, str) or not a.strip():
                    errors.append(f"actors[{i}] must be a non-empty string")

    constraints = data.get("constraints")
    if constraints is not None and not isinstance(constraints, dict):
        errors.append("'constraints' must be an object")

    horizon = data.get("horizon_months")
    if horizon is not None:
        if not isinstance(horizon, int) or horizon <= 0:
            errors.append("'horizon_months' must be a positive integer (e.g. 3, 6, 12)")
        elif horizon not in VALID_HORIZONS:
            errors.append(f"'horizon_months' must be one of {list(VALID_HORIZONS)}")

    context = data.get("context")
    if context is not None and not isinstance(context, str):
        errors.append("'context' must be a string")

    return errors


def decision_to_scenario_text(d: dict[str, Any]) -> str:
    """
    Render a DecisionInput dict into the free-text format that parse_scenario_text expects.
    This is the bridge that avoids rewriting the existing 5-stage parsing pipeline.
    """
    move = (d.get("move") or "").strip()
    actors = [str(a).strip() for a in (d.get("actors") or []) if str(a).strip()]
    constraints: dict = d.get("constraints") if isinstance(d.get("constraints"), dict) else {}
    horizon = d.get("horizon_months") or 6
    context = (d.get("context") or "").strip()

    parts: list[str] = []

    if context:
        parts.append(context)

    parts.append(f"Decision under analysis: {move}")

    if actors:
        parts.append(f"Key stakeholders involved: {', '.join(actors)}")

    constraint_parts: list[str] = []
    if constraints.get("budget"):
        constraint_parts.append(f"budget: {constraints['budget']}")
    if constraints.get("team_size"):
        constraint_parts.append(f"team size: {constraints['team_size']}")
    if constraints.get("runway_months"):
        constraint_parts.append(f"runway: {constraints['runway_months']} months")
    if constraints.get("regulatory"):
        constraint_parts.append(f"regulatory context: {constraints['regulatory']}")
    if constraints.get("other"):
        constraint_parts.append(str(constraints["other"]))
    if constraint_parts:
        parts.append(f"Operating constraints: {'; '.join(constraint_parts)}")

    parts.append(f"Decision horizon: {horizon} months")
    parts.append(
        "Analyze how this decision unfolds — which variables drive outcomes, "
        "what second-order effects appear, and when the decision would no longer be viable."
    )

    return "\n\n".join(parts)


def _normalize_constraints(raw: Any) -> dict[str, Any]:
    """Return a clean constraints dict with only known keys."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("budget", "team_size", "runway_months", "regulatory", "other"):
        val = raw.get(key)
        if val is None:
            continue
        if key in ("team_size", "runway_months"):
            try:
                out[key] = int(val)
            except (TypeError, ValueError):
                continue
        else:
            s = str(val).strip()
            if s:
                out[key] = s
    return out


def normalize_decision_input(d: dict[str, Any]) -> dict[str, Any]:
    """Return a clean, normalized copy of the decision input."""
    actors = [str(a).strip() for a in (d.get("actors") or []) if str(a).strip()]
    constraints = _normalize_constraints(d.get("constraints"))
    horizon = d.get("horizon_months")
    if not isinstance(horizon, int) or horizon <= 0:
        horizon = 6
    elif horizon not in VALID_HORIZONS:
        horizon = 6
    return {
        "move": (d.get("move") or "").strip(),
        "actors": actors,
        "constraints": constraints,
        "horizon_months": horizon,
        "context": (d.get("context") or "").strip(),
    }
