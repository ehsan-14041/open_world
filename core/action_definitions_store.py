"""
Action definitions store: unified deterministic action definitions with source.
All numeric deltas come from this store; the model never provides numeric delta_vector.
"""

from __future__ import annotations

from typing import Any


def build_action_definitions_from_scenario(
    scenario: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """
    Build unified action_definitions from scenario (action_tradeoffs, action_specs, strategy_classes).
    Returns dict keyed by action_id with:
      id, capability_tags, strategy_class, availability_conditions, delta_vector, source
    """
    action_tradeoffs = scenario.get("action_tradeoffs") or {}
    action_specs = scenario.get("action_specs") or {}
    strategy_classes = scenario.get("strategy_classes") or {}
    allowed_actions = scenario.get("allowed_actions") or []

    definitions: dict[str, dict[str, Any]] = {}

    for action_id in allowed_actions:
        tradeoff = action_tradeoffs.get(action_id) or {}
        spec = action_specs.get(action_id) or {}

        # delta_vector: from action_tradeoffs (effect) or spec.effect
        delta_vector: dict[str, float] = {}
        if isinstance(tradeoff, dict):
            delta_vector = {k: float(v) for k, v in tradeoff.items() if isinstance(v, (int, float))}
        if not delta_vector and isinstance(spec.get("effect"), dict):
            delta_vector = {k: float(v) for k, v in spec["effect"].items() if isinstance(v, (int, float))}

        # capability_tags
        caps = spec.get("capability_tags")
        if not isinstance(caps, list):
            caps = []
        capability_tags = [str(c) for c in caps if c]

        # strategy_class
        strategy_class = strategy_classes.get(action_id) or spec.get("strategy_class") or "general"
        if not isinstance(strategy_class, str):
            strategy_class = "general"

        # availability_conditions: predicate form
        avail = spec.get("availability_condition")
        availability_conditions: list[dict[str, Any]] = []
        if isinstance(avail, str) and avail.strip():
            availability_conditions = [{"raw": avail.strip()}]
        elif isinstance(avail, list):
            availability_conditions = [a for a in avail if isinstance(a, dict)]

        # source: discovered if from pipeline, fallback if from deriver
        source = spec.get("source") or "discovered"

        definitions[action_id] = {
            "id": action_id,
            "capability_tags": capability_tags,
            "strategy_class": strategy_class,
            "availability_conditions": availability_conditions,
            "delta_vector": delta_vector,
            "source": source,
        }

    return definitions


def add_proposed_action(
    definitions: dict[str, dict[str, Any]],
    action_id: str,
    capability_tags: list[str],
    strategy_class: str,
    delta_vector: dict[str, float],
    availability_conditions: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Add a proposed action (from creative proposal normalization) to definitions."""
    out = dict(definitions)
    out[action_id] = {
        "id": action_id,
        "capability_tags": capability_tags or [],
        "strategy_class": strategy_class or "general",
        "availability_conditions": availability_conditions or [],
        "delta_vector": dict(delta_vector),
        "source": "proposed",
    }
    return out


def get_delta_vector(
    definitions: dict[str, dict[str, Any]],
    action_id: str,
) -> dict[str, float]:
    """Return delta_vector for action_id, or empty dict if not found."""
    ad = definitions.get(action_id)
    if not ad:
        return {}
    dv = ad.get("delta_vector")
    return dict(dv) if isinstance(dv, dict) else {}
