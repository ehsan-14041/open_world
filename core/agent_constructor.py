"""
Dynamic agent construction: when scenario has no initial_agents, build agents from
scenario description (LLM) or rule-based fallback. Domain-agnostic; no predefined roles.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

# LLM prompt to extract actors, goals, tensions, and variables from scenario description
AGENTS_FROM_DESCRIPTION_SYSTEM = """You are an analyst for a multi-agent simulation. Given a scenario description, output a single JSON object with this exact structure and nothing else (no markdown, no explanation):

{
  "agents": [
    {
      "role": "actor_identifier",
      "goals": ["goal1", "goal2"],
      "traits": [],
      "resources": {}
    }
  ]
}

Rules:
- Identify 2-5 distinct actors from the scenario. Use short snake_case identifiers for "role" (e.g. "coastal_faction", "federal_regulator", "community_leader").
- Do NOT use placeholder names like actor_1, agent_2, faction_a.
- For each actor list 1-4 primary goals as short strings (e.g. "increase_tensions", "reduce_costs", "maintain_stability").
- Goals should reference variables or outcomes that can be adjusted (increase_X, reduce_Y, maintain_Z).
- "traits" and "resources" may be empty objects/arrays.
- Output ONLY valid JSON."""

AGENTS_FROM_DESCRIPTION_USER = """Scenario description:

{description}

If the scenario mentions initial state or variables, consider them when defining actor goals. Output the JSON object only."""


def _strip_markdown_json(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _llm_extract_agents(description: str, variables: list[str], llm_client: Callable[..., Any]) -> list[dict[str, Any]] | None:
    """Use LLM to extract agents from scenario description. Returns list of agent configs or None on failure."""
    try:
        user = AGENTS_FROM_DESCRIPTION_USER.format(description=description)
        if variables:
            user += f"\n\nRelevant variable names in this scenario: {', '.join(variables)}"
        out = llm_client(user, system=AGENTS_FROM_DESCRIPTION_SYSTEM, as_json=True)
        if not isinstance(out, dict):
            raw = _strip_markdown_json(str(out))
            out = json.loads(raw)
        agents = out.get("agents")
        if not isinstance(agents, list) or len(agents) == 0:
            return None
        return list(agents)
    except Exception:
        return None


def _agent_config_from_extracted(raw: dict[str, Any], variables: list[str], default_magnitude: float = 5.0) -> dict[str, Any]:
    """Convert LLM-extracted agent (role, goals, traits, resources) to scenario initial_agents format (name, role, objectives, long_term_goals).
    Automatically binds goals to variables from world_state by matching goal descriptions to variable names and directions."""
    role = (raw.get("role") or "actor").strip()
    if not role:
        role = "actor"
    name = role.replace(" ", "_").lower()[:64]
    goals = raw.get("goals") or []
    if not isinstance(goals, list):
        goals = [str(goals)] if goals else []
    goals = [str(g).strip() for g in goals if g]

    # Build objectives: automatically bind goals to variables
    # For each goal, try to match it to a variable and direction
    objectives: dict[str, float] = {}
    goal_to_var_map: dict[str, str] = {}  # Map goal text to variable name
    
    # First pass: match explicit variable references (e.g. "increase_tensions", "reduce_resources")
    for g in goals:
        g_lower = g.lower()
        matched = False
        for v in variables:
            v_lower = v.lower()
            # Check for explicit variable references in goal
            if v_lower in g_lower or v in g:
                matched = True
                goal_to_var_map[g] = v
                # Determine direction from goal text
                if any(word in g_lower for word in ["increase", "maximize", "raise", "boost", "grow", "expand"]):
                    key = f"increase_{v}"
                    objectives[key] = objectives.get(key, 0) + 0.5
                elif any(word in g_lower for word in ["decrease", "reduce", "minimize", "lower", "diminish", "cut"]):
                    key = f"decrease_{v}"
                    objectives[key] = objectives.get(key, 0) + 0.5
                else:
                    # Neutral goal: default to increase
                    key = f"increase_{v}"
                    objectives[key] = objectives.get(key, 0) + 0.4
                break
        
        # If no explicit variable match, try semantic matching
        if not matched and variables:
            # Match goal keywords to variable names (e.g. "tension" -> "tensions", "resource" -> "resources")
            for v in variables:
                v_words = set(v.lower().split("_"))
                g_words = set(g_lower.split())
                if v_words & g_words:  # Any word overlap
                    goal_to_var_map[g] = v
                    matched = True
                    if any(word in g_lower for word in ["increase", "maximize", "raise", "boost", "grow"]):
                        objectives[f"increase_{v}"] = objectives.get(f"increase_{v}", 0) + 0.4
                    elif any(word in g_lower for word in ["decrease", "reduce", "minimize", "lower"]):
                        objectives[f"decrease_{v}"] = objectives.get(f"decrease_{v}", 0) + 0.4
                    else:
                        objectives[f"increase_{v}"] = objectives.get(f"increase_{v}", 0) + 0.3
                    break

    # Second pass: assign unmatched goals to variables based on distribution
    unmatched_goals = [g for g in goals if g not in goal_to_var_map]
    if unmatched_goals and variables:
        # Distribute unmatched goals across variables
        for i, g in enumerate(unmatched_goals):
            v_idx = i % len(variables)
            v = variables[v_idx]
            goal_to_var_map[g] = v
            # Infer direction from goal text or default to increase
            g_lower = g.lower()
            if any(word in g_lower for word in ["increase", "maximize", "raise", "boost"]):
                objectives[f"increase_{v}"] = objectives.get(f"increase_{v}", 0) + 0.3
            elif any(word in g_lower for word in ["decrease", "reduce", "minimize", "lower"]):
                objectives[f"decrease_{v}"] = objectives.get(f"decrease_{v}", 0) + 0.3
            else:
                # Default: alternate between increase and decrease
                if i % 2 == 0:
                    objectives[f"increase_{v}"] = objectives.get(f"increase_{v}", 0) + 0.3
                else:
                    objectives[f"decrease_{v}"] = objectives.get(f"decrease_{v}", 0) + 0.3

    # Normalize objectives to sum to reasonable total (0.5-1.0 range)
    total_weight = sum(objectives.values())
    if total_weight > 1.0:
        for k in objectives:
            objectives[k] = objectives[k] / total_weight
    elif total_weight < 0.3 and variables:
        # If too few objectives, add default variable-driven ones
        for i, v in enumerate(variables[:3]):
            if i % 2 == 0:
                objectives[f"increase_{v}"] = objectives.get(f"increase_{v}", 0) + 0.3
            else:
                objectives[f"decrease_{v}"] = objectives.get(f"decrease_{v}", 0) + 0.3

    # Generate long_term_goals: use original goals if they reference variables, else create variable-driven goals
    long_term_goals: list[str] = []
    for g in goals:
        if g in goal_to_var_map:
            v = goal_to_var_map[g]
            g_lower = g.lower()
            if any(word in g_lower for word in ["increase", "maximize", "raise"]):
                long_term_goals.append(f"increase_{v}")
            elif any(word in g_lower for word in ["decrease", "reduce", "minimize"]):
                long_term_goals.append(f"decrease_{v}")
            else:
                long_term_goals.append(f"adjust_{v}")
        else:
            long_term_goals.append(g)
    
    if not long_term_goals and variables:
        # Fallback: create variable-driven goals from objectives
        long_term_goals = list(objectives.keys())[:4] if objectives else [f"adjust_{v}" for v in variables[:2]]

    return {
        "name": name,
        "role": role,
        "objectives": objectives,
        "long_term_goals": long_term_goals,
    }


def _fallback_agents_from_variables(variables: list[str], num_agents: int = 3) -> list[dict[str, Any]]:
    """Build 2-3 generic agents with neutral goals derived from variables. Deterministic, no LLM. No placeholder names."""
    if num_agents < 2:
        num_agents = 2
    if num_agents > 5:
        num_agents = 5
    if not variables:
        variables = ["primary_metric"]

    PARTICIPANT_NAMES = ["participant_a", "participant_b", "participant_c", "participant_d", "participant_e"]
    agents = []
    for i in range(num_agents):
        name = PARTICIPANT_NAMES[i] if i < len(PARTICIPANT_NAMES) else f"participant_{chr(ord('a') + i)}"
        # Spread goals: agent_i prefers increase for some vars, decrease for others (neutral mix)
        objectives: dict[str, float] = {}
        for j, v in enumerate(variables[:5]):
            if (i + j) % 2 == 0:
                objectives[f"increase_{v}"] = 0.4
            else:
                objectives[f"decrease_{v}"] = 0.4
        if not objectives and variables:
            # Fallback: create variable-driven objectives
            first_var = variables[0]
            objectives[f"increase_{first_var}"] = 0.5
        goals = list(objectives.keys())[:4] if objectives else [f"adjust_{v}" for v in variables[:2]]
        agents.append({
            "name": name,
            "role": name.replace("_", " ").replace("participant", "Participant").title(),
            "objectives": objectives,
            "long_term_goals": goals,
        })
    return agents


def construct_agents_from_scenario(
    scenario: dict[str, Any],
    llm_client: Callable[..., Any] | None,
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    When scenario has no initial_agents (or empty list), construct agent configs.
    If LLM available and not dry_run: extract actors/goals from description.
    Else: fallback to 2-3 generic agents with variable-derived goals.
    Returns list of dicts in initial_agents format: name, role, objectives, long_term_goals.
    """
    initial = scenario.get("initial_agents")
    if initial and isinstance(initial, list) and len(initial) > 0:
        return []  # Caller should use scenario initial_agents

    variables = list((scenario.get("initial_state") or {}).keys())
    if not isinstance(variables, list):
        variables = list(variables) if isinstance(variables, (dict, set)) else []

    description = (scenario.get("description") or "Generic scenario.").strip()

    if not dry_run and llm_client:
        extracted = _llm_extract_agents(description, variables, llm_client)
        if extracted:
            return [_agent_config_from_extracted(a, variables) for a in extracted]

    return _fallback_agents_from_variables(variables, num_agents=3)


def allowed_actions_from_variables(variables: list[str], *, include_adjust: bool = True) -> list[str]:
    """Build action list from variable names: increase_X, decrease_X for each variable. Domain-agnostic."""
    actions: list[str] = []
    for v in variables:
        actions.append(f"increase_{v}")
        actions.append(f"decrease_{v}")
    if include_adjust:
        actions.append("adjust_variable")
    return actions
