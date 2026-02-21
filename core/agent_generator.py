"""
LLM Integration: Agent generator layer for the scenario-to-simulation pipeline.
Consumes scenario (description + initial_state, optionally existing initial_agents)
and returns enriched agent definitions: name, role, objectives, personality,
initial_variables, long_term_goals. Output shape matches initial_agents for
get_agents_from_scenario().
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

# LLM Integration: single LLM call to generate full agent definitions from scenario
AGENT_GENERATOR_SYSTEM = """You are an analyst for a multi-agent simulation. Given a scenario (description and initial world state variables), output a single JSON object with this exact structure:

{
  "agents": [
    {
      "name": "short_snake_case_id",
      "role": "Human-readable role name",
      "objectives": { "increase_X": 0.5, "decrease_Y": 0.3 },
      "personality": "One short sentence describing how this agent tends to behave or decide.",
      "initial_variables": { "variable_name": number or null },
      "long_term_goals": ["goal1", "goal2"]
    }
  ]
}

Rules:
- Identify 2-5 distinct agents from the scenario. Use snake_case for "name".
- "objectives": keys must be action-like (e.g. increase_X, decrease_Y) matching the scenario variables; values are weights 0-1.
- "personality": one concise sentence (e.g. "Risk-averse, prefers stable outcomes.").
- "initial_variables": optional; for each world variable you may set an initial belief value (number) or null to use world default. Can be empty {}.
- "long_term_goals": 1-4 short strings (e.g. "increase_growth", "conserve_cash").
- Output ONLY valid JSON. No markdown, no explanation."""

AGENT_GENERATOR_USER = """Scenario description:
{description}

Initial world state variables (variable names and example scale):
{variables_json}

Allowed actions (use these or variable-driven actions like increase_X, decrease_X):
{allowed_actions_json}

Generate the agents JSON object only."""


def _strip_markdown_json(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def generate_agents_from_scenario(
    scenario: dict[str, Any],
    llm_client: Callable[..., Any],
) -> list[dict[str, Any]]:
    """
    LLM Integration: Produce agent definitions (name, role, objectives, personality,
    initial_variables, long_term_goals) from scenario. Returns list in initial_agents
    shape; merge into scenario["initial_agents"] before building SimulationLoop.
    """
    description = (scenario.get("description") or "Generic scenario.").strip()
    initial_state = scenario.get("initial_state") or {}
    variables = list(initial_state.keys()) if isinstance(initial_state, dict) else []
    allowed = scenario.get("allowed_actions")
    if not isinstance(allowed, list):
        from core.agent_constructor import allowed_actions_from_variables
        allowed = allowed_actions_from_variables(variables, include_adjust=True)
    variables_json = json.dumps(initial_state) if initial_state else "{}"
    allowed_actions_json = json.dumps(allowed)

    user = AGENT_GENERATOR_USER.format(
        description=description,
        variables_json=variables_json,
        allowed_actions_json=allowed_actions_json,
    )
    try:
        out = llm_client(user, system=AGENT_GENERATOR_SYSTEM, as_json=True)
    except Exception as e:
        return _fallback_agents(scenario, str(e))

    if not isinstance(out, dict):
        raw = _strip_markdown_json(str(out))
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            return _fallback_agents(scenario, "LLM did not return valid JSON")

    agents = out.get("agents")
    if not isinstance(agents, list) or len(agents) == 0:
        return _fallback_agents(scenario, "No agents in LLM response")

    result: list[dict[str, Any]] = []
    for i, a in enumerate(agents):
        if not isinstance(a, dict):
            continue
        name = (a.get("name") or a.get("role") or f"agent_{i+1}")
        if not isinstance(name, str):
            name = str(name)
        name = name.replace(" ", "_").lower()[:64] or f"agent_{i+1}"
        role = (a.get("role") or name).strip() if isinstance(a.get("role"), str) else name.replace("_", " ").title()
        objectives = a.get("objectives")
        if not isinstance(objectives, dict):
            objectives = _objectives_from_variables(variables)
        personality = a.get("personality")
        if personality is not None and not isinstance(personality, str):
            personality = None
        initial_variables = a.get("initial_variables")
        if initial_variables is not None and not isinstance(initial_variables, dict):
            initial_variables = {}
        if isinstance(initial_variables, dict):
            initial_variables = {k: v for k, v in initial_variables.items() if v is None or isinstance(v, (int, float))}
        long_term_goals = a.get("long_term_goals")
        if not isinstance(long_term_goals, list):
            long_term_goals = list(objectives.keys())[:4] if objectives else [f"adjust_{v}" for v in variables[:2]]
        long_term_goals = [str(g) for g in long_term_goals if g][:4]

        entry: dict[str, Any] = {
            "name": name,
            "role": role,
            "objectives": objectives,
            "long_term_goals": long_term_goals,
        }
        if personality is not None:
            entry["personality"] = personality
        if initial_variables is not None:
            entry["initial_variables"] = initial_variables
        result.append(entry)

    if not result:
        return _fallback_agents(scenario, "No valid agents after normalization")
    return result


def _objectives_from_variables(variables: list[str]) -> dict[str, float]:
    if not variables:
        return {"steady": 0.5}
    obj: dict[str, float] = {}
    for v in variables[:5]:
        obj[f"increase_{v}"] = 0.3
        obj[f"decrease_{v}"] = 0.2
    return obj


def _fallback_agents(scenario: dict[str, Any], _reason: str = "") -> list[dict[str, Any]]:
    """Fallback when LLM fails or returns invalid data: use agent_constructor."""
    from core.agent_constructor import construct_agents_from_scenario
    # Pass a no-op llm so we get rule-based fallback
    def noop_llm(*args: Any, **kwargs: Any) -> Any:
        return {}
    return construct_agents_from_scenario(scenario, noop_llm, dry_run=True)
