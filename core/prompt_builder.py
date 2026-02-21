"""
LLM Integration: Personalized decision-making prompt per agent (scenario-to-simulation pipeline).
Builds system (and user) prompt for turn-based LLM simulation from agent definition and scenario context.
"""

from __future__ import annotations

import json
from typing import Any

# Same response format as agents.RESPONSE_FORMAT_SPEC (single source for prompt builder)
RESPONSE_FORMAT_SPEC = """You MUST respond with exactly two sections in this order:

### REASONING
<your free natural language reasoning here>

### ACTION_JSON
{{ "action": "<action_type>", "actor": "<your agent name>", "deltas": [ {{ "variable": "<name>", "change": <number> }}, ... ] }}

Rules: ACTION_JSON must be valid JSON; no trailing commas; no comments; only one JSON block. action must be one of the allowed list; deltas list variable names and numeric changes."""

# Base system template: name, role, objectives, goals, allowed_actions (personality and initial_variables optional)
SYSTEM_BASE = """You are the agent "{name}" in role "{role}". Your objectives (importance): {objectives}.
Your current goals: {goals}.
Allowed actions: {allowed_actions}.
"""

PERSONALITY_LINE = """Your personality and style: {personality}
"""

INITIAL_VARIABLES_LINE = """Your initial view of key variables (for context): {initial_variables}
"""

USER_TEMPLATE = """Relevant context from your memory:
{memory_context}

Current world summary:
{world_summary}

Respond with ### REASONING then ### ACTION_JSON as specified. action MUST be one of: {allowed_actions}."""


def build_decision_prompt(
    agent_def: dict[str, Any],
    scenario_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """
    LLM Integration: Build personalized system prompt and user template for an agent.
    agent_def: name, role, objectives, long_term_goals (or goals), allowed_actions; optional personality, initial_variables.
    scenario_context: optional description, allowed_actions (overrides agent_def allowed_actions if provided).
    Returns (system_prompt, user_template).
    When agent_def has a non-empty system_prompt_override (e.g. from multi-stage compiler), that is used as system prompt.
    """
    scenario_context = scenario_context or {}
    override = agent_def.get("system_prompt_override")
    if isinstance(override, str) and override.strip():
        return override.strip(), USER_TEMPLATE
    name = agent_def.get("name") or "agent"
    role = agent_def.get("role") or name
    objectives = agent_def.get("objectives") or {}
    goals = agent_def.get("long_term_goals") or agent_def.get("goals") or list(objectives.keys())[:4]
    if not isinstance(goals, list):
        goals = [goals] if goals else []
    goals_str = json.dumps(goals)
    allowed = scenario_context.get("allowed_actions") or agent_def.get("allowed_actions") or []
    if not isinstance(allowed, list):
        allowed = list(allowed) if allowed else []
    allowed_str = json.dumps(allowed)

    system_parts = [SYSTEM_BASE.format(
        name=name,
        role=role,
        objectives=json.dumps(objectives),
        goals=goals_str,
        allowed_actions=allowed_str,
    )]
    personality = agent_def.get("personality")
    if isinstance(personality, str) and personality.strip():
        system_parts.append(PERSONALITY_LINE.format(personality=personality.strip()))
    initial_variables = agent_def.get("initial_variables")
    if isinstance(initial_variables, dict) and initial_variables:
        # Format as readable key: value
        iv_str = ", ".join(f"{k}: {v}" for k, v in initial_variables.items() if v is not None)
        if iv_str:
            system_parts.append(INITIAL_VARIABLES_LINE.format(initial_variables=iv_str))
    system_parts.append("\n" + RESPONSE_FORMAT_SPEC)
    system_prompt = "".join(system_parts)
    user_template = USER_TEMPLATE
    return system_prompt, user_template
