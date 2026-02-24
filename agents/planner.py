"""
Lightweight world clone and depth-2 planning: simulate candidate actions on a copy, score with utility.
Supports get_delta callback (WorldModelAgent) and optional LLM expected environment events.
"""

from __future__ import annotations

import copy
import random
from typing import Any, Callable

from agents.utility import utility_function
from core.world_state import WorldState
from world.world_state import clone_world_state as _clone_world_state

try:
    from config.settings import LIGHT_PROP_HOPS, PLANNER_DECAY_FACTOR, PROPAGATION_DECAY_FACTOR
except ImportError:
    LIGHT_PROP_HOPS = 1
    PLANNER_DECAY_FACTOR = None
    PROPAGATION_DECAY_FACTOR = 1.0

# Type for mapping action_type -> strategy class name
StrategyClassFn = Callable[[str], str]


def _apply_delta_for_planning(
    clone: dict[str, Any],
    delta: dict[str, Any],
    causal_links: list[dict[str, Any]] | None,
    variable_specs: dict[str, dict[str, Any]] | None,
    max_hops: int,
    decay_factor: float | None,
) -> None:
    """Apply delta to clone: use run_mental_simulation when causal_links given, else apply_delta_to_state."""
    if causal_links and len(causal_links) > 0:
        from core.mental_simulation import run_mental_simulation
        decay = decay_factor if decay_factor is not None else PROPAGATION_DECAY_FACTOR
        result = run_mental_simulation(
            clone, delta, causal_links, variable_specs or {},
            max_hops=max_hops, decay_factor=decay,
        )
        clone["variables"] = result.get("variables", result.get("global_state", {}))
        clone["global_state"] = clone["variables"]
    else:
        apply_delta_to_state(clone, delta)


def clone_world_state(snapshot: dict[str, Any], *, include_causal_links: bool = False) -> dict[str, Any]:
    """Canonical clone: delegates to world.world_state.clone_world_state. Planning uses include_causal_links=False."""
    return _clone_world_state(snapshot, include_causal_links=include_causal_links)


def apply_delta_to_state(state: dict[str, Any], delta: dict[str, Any]) -> None:
    """Apply delta (numeric_updates, entity_updates, new_entities, relation_updates) to state in place."""
    gs = state.get("global_state") or {}
    state["global_state"] = dict(gs)
    for key, value in (delta.get("numeric_updates") or {}).items():
        if isinstance(value, (int, float)):
            current = state["global_state"].get(key, 0)
            if isinstance(current, (int, float)):
                state["global_state"][key] = current + value
            else:
                state["global_state"][key] = value
        else:
            state["global_state"][key] = value

    entities = state.get("entities") or {}
    state["entities"] = dict(entities)
    for eid, attrs in (delta.get("entity_updates") or {}).items():
        if eid in state["entities"]:
            state["entities"][eid] = dict(state["entities"][eid])
            state["entities"][eid].update(attrs)
        else:
            state["entities"][eid] = dict(attrs)
    for eid, entity in (delta.get("new_entities") or {}).items():
        state["entities"][eid] = dict(entity)

    state["relations"] = list(state.get("relations") or [])
    for rel in (delta.get("relation_updates") or []):
        state["relations"].append(dict(rel))


def delta_from_rule_based(action_type: str, rule_based_deltas: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Build a delta dict from rule-based numeric_updates for an action."""
    numeric = dict(rule_based_deltas.get(action_type, {}))
    return {
        "numeric_updates": numeric,
        "entity_updates": {},
        "new_entities": {},
        "relation_updates": [],
        "meta_proposals": [],
        "rationale": f"Rule-based: {action_type}",
        "effects_duration": None,
        "mitigation": None,
    }


# Default second-step action for depth-2 (steady state)
STEADY_ACTION = "steady_finance"


def plan_depth2(
    snapshot: dict[str, Any],
    candidate_actions: list[str],
    objectives: dict[str, float],
    rule_based_deltas: dict[str, dict[str, float]],
    *,
    beliefs: dict[str, Any] | None = None,
    second_step_action: str | None = STEADY_ACTION,
    long_term_memory: list[dict[str, Any]] | None = None,
    current_turn: int | None = None,
    last_actions: list[str] | None = None,
    strategy_class_weights: dict[str, float] | None = None,
    get_strategy_class: StrategyClassFn | None = None,
    instability_mode: bool = False,
    causal_links: list[dict[str, Any]] | None = None,
    variable_specs: dict[str, dict[str, Any]] | None = None,
    max_hops: int = LIGHT_PROP_HOPS,
    decay_factor: float | None = PLANNER_DECAY_FACTOR,
) -> str:
    """
    For each candidate action: clone world, apply action delta, optionally apply second step,
    compute utility of resulting state. Return action_type that maximizes expected utility.
    Penalizes actions that match recent negative memories and repeats in last 2 turns (anti-repetition).
    """
    if not candidate_actions:
        return STEADY_ACTION
    beliefs = beliefs or {}
    long_term_memory = long_term_memory or []
    current_turn = current_turn or snapshot.get("turn", 0)
    last_actions = last_actions or []
    last_actions_set = set(last_actions)
    strategy_class_weights = strategy_class_weights or {}
    get_strategy_class = get_strategy_class or (lambda _: "default")

    # Filter for recent negative memories (last 5 turns, valence < -0.3, importance > 0.1)
    recent_negative_memories = [
        m for m in long_term_memory
        if (current_turn - m.get("turn", 0) <= 5
            and m.get("emotional_valence", 0) < -0.3
            and m.get("importance", 0) > 0.1)
    ]

    # Extract action types from negative memories
    negative_action_patterns: set[str] = set()
    for memory in recent_negative_memories:
        event = memory.get("event", "")
        # Extract action type from event (format: "action_type accepted/rejected")
        parts = event.split()
        if parts:
            negative_action_patterns.add(parts[0])

    best_action = candidate_actions[0]
    best_score = float("-inf")

    links = causal_links if causal_links is not None else (snapshot.get("causal_links") or [])
    for action_type in candidate_actions:
        clone = clone_world_state(snapshot, include_causal_links=bool(links))
        delta1 = delta_from_rule_based(action_type, rule_based_deltas)
        _apply_delta_for_planning(clone, delta1, links, variable_specs, max_hops, decay_factor)
        if second_step_action and second_step_action in rule_based_deltas:
            delta2 = delta_from_rule_based(second_step_action, rule_based_deltas)
            _apply_delta_for_planning(clone, delta2, links, variable_specs, max_hops, decay_factor)
        score = utility_function(clone, beliefs, objectives)

        # Instability mode: risk-seeking bias (favor higher-magnitude deltas)
        if instability_mode and delta1.get("numeric_updates"):
            total_magnitude = sum(abs(v) for v in delta1["numeric_updates"].values() if isinstance(v, (int, float)))
            score *= 1.0 + min(0.3, total_magnitude / 100.0)

        # Apply penalty if action matches negative memory pattern
        if action_type in negative_action_patterns:
            score *= 0.5  # Reduce score by 50% for actions with negative memories
        # Anti-repetition: reduce utility by at least 30% if same action in last 2 turns
        if action_type in last_actions_set:
            score *= 0.7
        # Memory reinforcement: scale by strategy class weight (successful strategies favored)
        strategy_class = get_strategy_class(action_type)
        weight = strategy_class_weights.get(strategy_class, 1.0)
        score *= weight

        if score > best_score:
            best_score = score
            best_action = action_type

    # Instability mode: increased randomness — with probability 0.2 pick random action
    if instability_mode and len(candidate_actions) > 1 and random.random() < 0.2:
        best_action = random.choice(candidate_actions)

    return best_action


def plan_depth2_with_callback(
    snapshot: dict[str, Any],
    candidate_actions: list[str],
    objectives: dict[str, float],
    get_delta: Callable[[str], dict[str, Any] | Any],
    *,
    beliefs: dict[str, Any] | None = None,
    second_step_action: str | None = STEADY_ACTION,
    causal_links: list[dict[str, Any]] | None = None,
    variable_specs: dict[str, dict[str, Any]] | None = None,
    max_hops: int = LIGHT_PROP_HOPS,
    decay_factor: float | None = PLANNER_DECAY_FACTOR,
) -> str:
    """
    Same as plan_depth2 but use get_delta(action_type) instead of rule_based_deltas dict.
    get_delta may return Delta, dict, or None. If None, skip that candidate.
    """
    if not candidate_actions:
        return STEADY_ACTION
    beliefs = beliefs or {}
    links = causal_links if causal_links is not None else (snapshot.get("causal_links") or [])
    best_action = candidate_actions[0]
    best_score = float("-inf")

    for action_type in candidate_actions:
        delta1 = get_delta(action_type)
        if delta1 is None:
            continue
        if not isinstance(delta1, dict):
            delta1 = delta1.to_dict() if hasattr(delta1, "to_dict") else {}
        clone = clone_world_state(snapshot, include_causal_links=bool(links))
        _apply_delta_for_planning(clone, delta1, links, variable_specs, max_hops, decay_factor)
        if second_step_action:
            delta2 = get_delta(second_step_action)
            if delta2 is not None:
                if not isinstance(delta2, dict):
                    delta2 = delta2.to_dict() if hasattr(delta2, "to_dict") else {}
                _apply_delta_for_planning(clone, delta2, links, variable_specs, max_hops, decay_factor)
        score = utility_function(clone, beliefs, objectives)
        if score > best_score:
            best_score = score
            best_action = action_type

    return best_action


def plan_depth2_llm_aware(
    snapshot: dict[str, Any],
    candidate_actions: list[str],
    objectives: dict[str, float],
    get_delta: Callable[[str], dict[str, Any] | Any],
    *,
    beliefs: dict[str, Any] | None = None,
    get_expected_events: Callable[[dict[str, Any]], dict[str, float]] | None = None,
    causal_links: list[dict[str, Any]] | None = None,
    variable_specs: dict[str, dict[str, Any]] | None = None,
    max_hops: int = LIGHT_PROP_HOPS,
    decay_factor: float | None = PLANNER_DECAY_FACTOR,
) -> str:
    """
    Depth-2 planning with get_delta callback. Optionally apply expected environment events
    (probability-weighted) to clone before scoring. Uses mental sim when causal_links given.
    """
    if not candidate_actions:
        return STEADY_ACTION
    beliefs = beliefs or {}
    links = causal_links if causal_links is not None else (snapshot.get("causal_links") or [])
    best_action = candidate_actions[0]
    best_score = float("-inf")

    for action_type in candidate_actions:
        delta1 = get_delta(action_type)
        if delta1 is None:
            continue
        if not isinstance(delta1, dict):
            delta1 = delta1.to_dict() if hasattr(delta1, "to_dict") else {}
        if links:
            clone = clone_world_state(snapshot, include_causal_links=True)
            _apply_delta_for_planning(clone, delta1, links, variable_specs, max_hops, decay_factor)
            if get_expected_events:
                expected = get_expected_events(clone)
                if isinstance(expected, dict) and expected:
                    _apply_delta_for_planning(
                        clone, {"numeric_updates": expected, "rationale": "expected_events"},
                        links, variable_specs, max_hops, decay_factor,
                    )
        else:
            try:
                ws = WorldState.from_snapshot(snapshot)
                ws.apply_delta(delta1, enforce_policy=True)
                if get_expected_events:
                    expected = get_expected_events(ws.to_snapshot())
                    if isinstance(expected, dict) and expected:
                        ws.apply_delta({"numeric_updates": expected, "rationale": "expected_events"}, enforce_policy=False)
                clone = ws.to_snapshot()
            except Exception:
                clone = clone_world_state(snapshot)
                apply_delta_to_state(clone, delta1)
        score = utility_function(clone, beliefs, objectives)
        if score > best_score:
            best_score = score
            best_action = action_type

    return best_action
