"""
Scenario schema: structure expected by SimulationLoop (config/scenarios/*.json).
Used to validate LLM-generated scenario JSON from free text.
"""

from __future__ import annotations

from typing import Any


# initial_agents is optional: when absent, agents are constructed dynamically from scenario description
REQUIRED_KEYS = {"description", "initial_state", "relations", "allowed_actions"}


def validate_scenario(data: dict[str, Any]) -> list[str]:
    """
    Validate scenario dict against expected schema.
    Returns list of error messages; empty list means valid.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Scenario must be a JSON object"]

    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        errors.append(f"Missing required keys: {sorted(missing)}")

    if "description" in data and not isinstance(data.get("description"), str):
        errors.append("'description' must be a string")

    agents = data.get("initial_agents")
    if agents is not None:
        if not isinstance(agents, list):
            errors.append("'initial_agents' must be an array")
        else:
            for i, a in enumerate(agents):
                if not isinstance(a, dict):
                    errors.append(f"initial_agents[{i}] must be an object")
                else:
                    if "name" not in a or not isinstance(a.get("name"), str):
                        errors.append(f"initial_agents[{i}] must have string 'name'")
                    if "role" not in a or not isinstance(a.get("role"), str):
                        errors.append(f"initial_agents[{i}] must have string 'role'")
                    obj = a.get("objectives")
                    if obj is not None and not isinstance(obj, dict):
                        errors.append(f"initial_agents[{i}].objectives must be an object")
                    elif isinstance(obj, dict):
                        for k, v in obj.items():
                            if not isinstance(v, (int, float)):
                                errors.append(
                                    f"initial_agents[{i}].objectives['{k}'] must be a number"
                                )
                    lt = a.get("long_term_goals")
                    if lt is not None and not isinstance(lt, list):
                        errors.append(f"initial_agents[{i}].long_term_goals must be an array")
                    elif isinstance(lt, list):
                        for j, g in enumerate(lt):
                            if not isinstance(g, str):
                                errors.append(f"initial_agents[{i}].long_term_goals[{j}] must be a string")
                    # LLM Integration: optional personality and initial_variables (scenario-to-simulation pipeline)
                    if "personality" in a and a.get("personality") is not None and not isinstance(a.get("personality"), str):
                        errors.append(f"initial_agents[{i}].personality must be a string")
                    if "initial_variables" in a and a.get("initial_variables") is not None:
                        iv = a.get("initial_variables")
                        if not isinstance(iv, dict):
                            errors.append(f"initial_agents[{i}].initial_variables must be an object")
                    # Multi-stage compiler: optional system_prompt_override, risk_tolerance, aggressiveness
                    if "system_prompt_override" in a and a.get("system_prompt_override") is not None and not isinstance(a.get("system_prompt_override"), str):
                        errors.append(f"initial_agents[{i}].system_prompt_override must be a string")
                    if "risk_tolerance" in a and a.get("risk_tolerance") is not None and not isinstance(a.get("risk_tolerance"), (int, float)):
                        errors.append(f"initial_agents[{i}].risk_tolerance must be a number")
                    if "aggressiveness" in a and a.get("aggressiveness") is not None and not isinstance(a.get("aggressiveness"), (int, float)):
                        errors.append(f"initial_agents[{i}].aggressiveness must be a number")
                    if "allowed_actions" in a and a.get("allowed_actions") is not None:
                        la = a.get("allowed_actions")
                        if not isinstance(la, list):
                            errors.append(f"initial_agents[{i}].allowed_actions must be an array")
                        else:
                            for j, x in enumerate(la):
                                if not isinstance(x, str):
                                    errors.append(f"initial_agents[{i}].allowed_actions[{j}] must be a string")
                    if "capabilities" in a and a.get("capabilities") is not None:
                        caps = a.get("capabilities")
                        if not isinstance(caps, list):
                            errors.append(f"initial_agents[{i}].capabilities must be an array")

    state = data.get("initial_state")
    if state is not None and not isinstance(state, dict):
        errors.append("'initial_state' must be an object")

    relations = data.get("relations")
    if relations is not None:
        if not isinstance(relations, list):
            errors.append("'relations' must be an array")
        else:
            for i, r in enumerate(relations):
                if not isinstance(r, dict):
                    errors.append(f"relations[{i}] must be an object")
                else:
                    for key in ("from", "to", "type"):
                        if key not in r or not isinstance(r.get(key), str):
                            errors.append(f"relations[{i}] must have string '{key}'")

    actions = data.get("allowed_actions")
    if actions is not None:
        if not isinstance(actions, list):
            errors.append("'allowed_actions' must be an array")
        else:
            for i, x in enumerate(actions):
                if not isinstance(x, str):
                    errors.append(f"allowed_actions[{i}] must be a string")

    gov = data.get("governance")
    if gov is not None and not isinstance(gov, dict):
        errors.append("'governance' must be an object")

    causal_links = data.get("causal_links")
    if causal_links is not None and not isinstance(causal_links, list):
        errors.append("'causal_links' must be an array")

    rules = data.get("rules")
    if rules is not None and not isinstance(rules, list):
        errors.append("'rules' must be an array")

    events = data.get("events")
    if events is not None and not isinstance(events, list):
        errors.append("'events' must be an array")

    action_tradeoffs = data.get("action_tradeoffs")
    if action_tradeoffs is not None and not isinstance(action_tradeoffs, dict):
        errors.append("'action_tradeoffs' must be an object")

    variable_tradeoffs = data.get("variable_tradeoffs")
    if variable_tradeoffs is not None and not isinstance(variable_tradeoffs, dict):
        errors.append("'variable_tradeoffs' must be an object")

    strategy_classes = data.get("strategy_classes")
    if strategy_classes is not None and not isinstance(strategy_classes, dict):
        errors.append("'strategy_classes' must be an object")

    return errors


def normalize_scenario(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure required keys exist with defaults; return a copy safe for SimulationLoop.
    Preserves pipeline-provided fields (uses setdefault only when key is absent).
    Causal links may have from, to, polarity, strength, weight; propagation derives weight from polarity+strength when absent.
    initial_agents optional: when missing or empty, engine constructs agents dynamically."""
    out = dict(data)
    out.setdefault("description", "User-defined scenario")
    if "initial_agents" not in out:
        out["initial_agents"] = []
    out.setdefault("initial_state", {})
    out.setdefault("relations", [])
    # allowed_actions: default to empty so engine can derive variable-driven actions when no list provided
    if "allowed_actions" not in out:
        out["allowed_actions"] = []
    out.setdefault("governance", {})
    if not isinstance(out["governance"], dict):
        out["governance"] = {}
    out["governance"].setdefault("strictness_level", 1)
    out.setdefault("causal_links", [])
    out.setdefault("rules", [])
    out.setdefault("events", [])
    out.setdefault("action_tradeoffs", {})
    out.setdefault("variable_tradeoffs", {})
    out.setdefault("strategy_classes", {})
    out.setdefault("variable_specs", {})
    out.setdefault("enable_meta_actions", False)
    # Optional: "strategic" uses chosen_action/expected_effect/primary_variable schema
    # "option_set" uses OptionSet with 3 options + selector
    if "agent_response_format" not in out:
        out["agent_response_format"] = "legacy"
    return out
