"""
ActionDiscoveryEngine: LLM-based dynamic action discovery from scenario text.
Actions emerge from scenario context; no pre-defined action list.
Produces action_tradeoffs, per_agent_actions (capability-based).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from pipeline._llm_utils import run_llm_stage
from pipeline.errors import PipelineError
from pipeline.action_space_deriver import ActionSpaceDeriver


ACTION_DISCOVERY_SYSTEM = """You are a strategic simulation analyst.
From the scenario text, extract all plausible strategic actions that agents could take.

For each action provide:
- name: short snake_case identifier (e.g. deescalate, propose_ceasefire, activate_hotline)
- effect: object mapping variable names to numeric deltas (e.g. {"tension": -5, "stability": 2})
- capability_tags: list of role tags that can perform this action (e.g. ["diplomatic", "military", "mediator"])
- strategy_class: optional string (e.g. "diplomatic", "escalatory", "neutral")
- strategy_domain_tags: optional list for scenario analysis: any of "regional_tension", "security_risk", "diplomatic_progress" when the action clearly affects that dimension
- availability_condition: optional string (e.g. "when tension > 50" or null)

Do NOT use generic actions like increase_X or decrease_X. Actions must be scenario-specific.
Each action must affect at least one variable from the provided list.
Return 4-10 actions.

Output JSON object:
{
  "actions": [
    {
      "name": "action_name",
      "effect": {"variable": delta_number},
      "capability_tags": ["tag1", "tag2"],
      "strategy_class": "class_name",
      "strategy_domain_tags": ["regional_tension", "diplomatic_progress"] or null,
      "availability_condition": "optional condition or null"
    }
  ]
}

Output JSON only."""

ACTION_DISCOVERY_USER = """Scenario:
{scenario_text}

Variables (must be referenced in effect):
{variables_json}

Actors and their roles:
{actors_json}"""


def _validate_action_discovery(data: Any, variable_names: set[str]) -> str | None:
    if not isinstance(data, dict):
        return "Must return a JSON object"
    if "actions" not in data:
        return "Must have 'actions' key"
    actions = data.get("actions")
    if not isinstance(actions, list):
        return "'actions' must be an array"
    if len(actions) == 0:
        return "Must have at least one action"
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            return f"actions[{i}] must be an object"
        if "name" not in a or not isinstance(a.get("name"), str):
            return f"actions[{i}] must have string 'name'"
        if "effect" not in a:
            return f"actions[{i}] must have 'effect'"
        eff = a.get("effect")
        if not isinstance(eff, dict):
            return f"actions[{i}].effect must be an object"
        for var in eff:
            if var not in variable_names:
                return f"actions[{i}].effect references unknown variable '{var}'"
            if not isinstance(eff[var], (int, float)):
                return f"actions[{i}].effect['{var}'] must be numeric"
    return None


def _map_entities_to_capabilities(entities: list[dict[str, Any]], incentives: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """Map entity names to capability tags from incentives."""
    entity_caps: dict[str, list[str]] = {}
    for e in entities:
        name = e.get("name")
        if not name:
            continue
        inc = incentives.get(name) or {}
        caps = inc.get("capabilities") or []
        if isinstance(caps, list):
            entity_caps[name] = [str(c) for c in caps if c]
        else:
            entity_caps[name] = []
    return entity_caps


def _match_actions_to_agents(
    actions: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    entity_capabilities: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Assign actions to agents by capability_tags matching entity capabilities or role."""
    per_agent: dict[str, list[str]] = {}
    action_names = [a.get("name") for a in actions if a.get("name")]

    for e in entities:
        name = e.get("name")
        if not name:
            continue
        role = (e.get("role") or "").lower()
        caps = set(entity_capabilities.get(name) or [])
        role_words = set(role.replace("_", " ").split())

        allowed: list[str] = []
        for a in actions:
            aname = a.get("name")
            if not aname:
                continue
            tags = a.get("capability_tags") or []
            if not isinstance(tags, list):
                tags = []
            tag_set = {str(t).lower() for t in tags}

            if not tag_set:
                allowed.append(aname)
                continue
            if caps & tag_set:
                allowed.append(aname)
                continue
            if role_words & tag_set:
                allowed.append(aname)
                continue
            if "all" in tag_set or "any" in tag_set:
                allowed.append(aname)
                continue

        if not allowed:
            allowed = list(action_names)
        per_agent[name] = allowed

    return per_agent


class ActionDiscoveryEngine:
    """Discover actions dynamically from scenario text via LLM."""

    @staticmethod
    def discover(
        scenario_text: str,
        entities: list[dict[str, Any]],
        variables: dict[str, float],
        causal_graph: list[dict[str, Any]],
        incentives: dict[str, dict[str, Any]],
        llm_client: Callable[..., Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Discover actions from scenario. Returns:
        - allowed_actions: list of action names
        - action_specs: dict[action_name, {effect, capability_tags, strategy_class, availability_condition}]
        - action_tradeoffs: dict[action_name, {var: delta}] for governance
        - per_agent_actions: dict[agent_name, list[str]]
        - strategy_classes: dict[action_name, strategy_class]
        """
        variable_names = set(variables.keys())
        if not variable_names:
            return _fallback_action_model(variables, causal_graph, incentives, entities)

        actors_json = json.dumps(
            [{"name": e.get("name"), "role": e.get("role")} for e in entities],
            ensure_ascii=False,
        )
        variables_json = json.dumps(variables, ensure_ascii=False)
        user = ACTION_DISCOVERY_USER.format(
            scenario_text=(scenario_text or "")[:3000],
            variables_json=variables_json,
            actors_json=actors_json,
        )

        def validator(data: Any) -> str | None:
            return _validate_action_discovery(data, variable_names)

        try:
            result = run_llm_stage(
                "Action Discovery",
                user,
                ACTION_DISCOVERY_SYSTEM,
                llm_client,
                config,
                validator,
            )
        except ValueError as e:
            return _fallback_action_model(variables, causal_graph, incentives, entities, str(e))

        actions_list = result.get("actions") or []
        allowed_actions: list[str] = []
        action_specs: dict[str, dict[str, Any]] = {}
        action_tradeoffs: dict[str, dict[str, float]] = {}
        strategy_classes: dict[str, str] = {}

        for a in actions_list:
            if not isinstance(a, dict):
                continue
            aname = (a.get("name") or "").strip()
            if not aname:
                continue
            effect = a.get("effect") or {}
            if not isinstance(effect, dict):
                effect = {}
            effect_clean = {k: float(v) for k, v in effect.items() if k in variable_names and isinstance(v, (int, float))}
            if not effect_clean:
                continue

            allowed_actions.append(aname)
            action_tradeoffs[aname] = dict(effect_clean)
            domain_tags = a.get("strategy_domain_tags")
            if not isinstance(domain_tags, list):
                domain_tags = []
            domain_tags = [str(t) for t in domain_tags if t in ("regional_tension", "security_risk", "diplomatic_progress")]

            action_specs[aname] = {
                "effect": effect_clean,
                "capability_tags": a.get("capability_tags") if isinstance(a.get("capability_tags"), list) else [],
                "strategy_class": (a.get("strategy_class") or "general").strip() or "general",
                "strategy_domain_tags": domain_tags,
                "availability_condition": a.get("availability_condition") if isinstance(a.get("availability_condition"), str) else None,
                "source": "discovered",
            }
            strategy_classes[aname] = action_specs[aname]["strategy_class"]

        if not allowed_actions:
            return _fallback_action_model(variables, causal_graph, incentives, entities)

        entity_caps = _map_entities_to_capabilities(entities, incentives)
        per_agent_actions = _match_actions_to_agents(actions_list, entities, entity_caps)

        return {
            "allowed_actions": allowed_actions,
            "action_specs": action_specs,
            "action_tradeoffs": action_tradeoffs,
            "per_agent_actions": per_agent_actions,
            "strategy_classes": strategy_classes,
        }


def _fallback_action_model(
    variables: dict[str, float],
    causal_graph: list[dict[str, Any]],
    incentives: dict[str, dict[str, Any]],
    entities: list[dict[str, Any]],
    _reason: str = "",
) -> dict[str, Any]:
    """Fallback when LLM fails: use ActionSpaceDeriver."""
    actions = ActionSpaceDeriver.derive(variables, causal_graph, incentives, entities)
    action_tradeoffs: dict[str, dict[str, float]] = {}
    for a in actions:
        if a.startswith("increase_"):
            var = a[9:]
            if var in variables:
                action_tradeoffs[a] = {var: 5.0}
        elif a.startswith("decrease_"):
            var = a[9:]
            if var in variables:
                action_tradeoffs[a] = {var: -5.0}
    per_agent: dict[str, list[str]] = {e.get("name"): list(actions) for e in entities if e.get("name")}
    strategy_classes = {a: "general" for a in actions}
    return {
        "allowed_actions": actions,
        "action_specs": {
            a: {
                "effect": action_tradeoffs.get(a, {}),
                "strategy_class": "general",
                "strategy_domain_tags": [],
                "source": "fallback",
            }
            for a in actions
        },
        "action_tradeoffs": action_tradeoffs,
        "per_agent_actions": per_agent,
        "strategy_classes": strategy_classes,
    }
