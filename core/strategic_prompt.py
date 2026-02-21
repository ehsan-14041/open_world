"""
Strategic agent prompt: numeric multi-agent simulation format.
Builds SYSTEM and USER prompts for the chosen_action/expected_effect/primary_variable schema.
"""

from __future__ import annotations

import json
from typing import Any

STRATEGIC_SYSTEM = """You are an autonomous strategic agent participating in a numeric multi-agent simulation.
Respond with ### ACTION_JSON on one line, then a single JSON object (no markdown, no extra text). The JSON must strictly follow the schema below and be valid JSON.

Schema (required fields):
{
  "chosen_action": "string",
  "primary_variable": "string",
  "probability": 0.0,
  "justification": "string",
  "causal_chain": "string",
  "expected_effect": {
      "<variable_name>": -5.0
  },
  "relation_updates": [
      {"from": "actor_name", "to": "actor_name", "type": "string", "rationale": "short"}
  ]
}

CONSTRAINTS:
1. primary_variable cannot be null and must be one of the world variables.
2. probability must be a real between 0 and 1.
3. Each expected_effect delta must be within allowed per-turn bounds: ABS(delta) <= MAX_DELTA, where MAX_DELTA is provided in the prompt. If you want a larger effect, propose it but it will be clipped by the WorldModelAgent.
4. justification max length: 60 words. Keep it concise.
5. causal_chain must map to existing causal_links or be a plausible single-step causal inference.
6. If you cannot produce a valid response, return JSON with field "error": "short explanation", not other keys."""

STRATEGIC_USER = """You are: {actor_role} (name: {actor_name})
Actor profile: {agent_profile_json}
World variables (0-100): {variables_json}
Causal links: {causal_links_json}
Allowed actions: {allowed_actions_json}
Config:
  MAX_DELTA: {max_delta}
  INSTABILITY_MODE: {instability_mode}
  OBS_NOISE_SCALE: {observation_noise_scale}

Task:
Choose ONE action this turn from Allowed actions that best advances your objectives while respecting risk_tolerance and INSTABILITY_MODE. Produce the JSON object described in SYSTEM. Focus on realistic, conservative moves if INSTABILITY_MODE is true and avoid actions that would increase 'tension' above current value unless probability > 0.8 and risk_tolerance > 0.7.

Remember: Output ### ACTION_JSON then valid JSON matching the schema exactly. No other text."""

# Option set format: 3 options (safe, bold, creative)
OPTION_SET_SYSTEM = """You are an autonomous strategic agent. Output JSON only. No markdown, no extra text.

You MUST produce exactly 3 options with styles: "safe", "bold", "creative".
- safe: conservative, low variance, preserves resources
- bold: higher leverage, higher risk
- creative: unusual but plausible mechanism-based move (must still be strategic)

Schema:
{
  "agent_id": "your_name",
  "options": [
    {"agent_id": "...", "option_id": "opt_1", "style": "safe", "action_name": "...", "parameters": {}, "intent": "...", "expected_tradeoff": "must mention downside", "uncertainty": 0.0-1.0},
    {"agent_id": "...", "option_id": "opt_2", "style": "bold", ...},
    {"agent_id": "...", "option_id": "opt_3", "style": "creative", ...}
  ]
}

CONSTRAINTS:
1. action_name must be in allowed_actions or propose_new_action/propose_new_variable/propose_new_causal_link/propose_new_event.
2. Each expected_tradeoff MUST mention at least one downside.
3. Base choices on beliefs/observations, not omniscience.
4. Avoid repeating last 2 actions unless justified.
5. Mechanism-based moves, not pure number twiddling.
6. Output ### ACTION_JSON then valid JSON. No other text."""

OPTION_SET_USER = """Role Card: {actor_role} (name: {actor_name})
Goals: {goals_json}
Constraints: risk_tolerance={risk_tolerance}, INSTABILITY_MODE={instability_mode}

Current Beliefs/Observations (noisy view): {variables_json}

Allowed Actions (including meta if enabled): {allowed_actions_json}

Decision Rubric: alignment with goals, plausibility, tradeoff quality, novelty (avoid repetition), risk budget (penalize bold when unstable).

Produce exactly 3 options (safe, bold, creative). Output ### ACTION_JSON then valid JSON."""

# Selector/Critic prompt: low-temp, outputs SelectedAction only
SELECTOR_SYSTEM = """You are a strategic critic. Pick ONE option from the 3 provided.
Output JSON only: {"chosen_option_id": "...", "action_name": "...", "parameters": {}, "short_reason": "<= 2 sentences", "uncertainty": 0.0-1.0}
Justify in <= 2 sentences. No other text."""


def build_option_set_prompt(
    agent_def: dict[str, Any],
    snapshot: dict[str, Any],
    scenario: dict[str, Any],
    *,
    max_delta: float = 10.0,
    obs_noise_scale: float = 0.0,
) -> tuple[str, str]:
    """Build prompt for option_set format: 3 options per turn."""
    actor_name = agent_def.get("name") or "agent"
    actor_role = agent_def.get("role") or actor_name
    risk_tolerance = agent_def.get("risk_tolerance", 0.5)
    goals = agent_def.get("long_term_goals") or agent_def.get("goals") or []
    goals_json = json.dumps(goals) if isinstance(goals, list) else json.dumps([goals])
    variables = snapshot.get("variables") or snapshot.get("global_state") or {}
    variables_json = json.dumps(variables) if isinstance(variables, dict) else "{}"
    allowed_actions = scenario.get("allowed_actions") or []
    if scenario.get("enable_meta_actions"):
        allowed_actions = list(allowed_actions) + [
            "propose_new_action", "propose_new_variable", "propose_new_causal_link", "propose_new_event"
        ]
    allowed_actions_json = json.dumps(allowed_actions)
    derived = snapshot.get("derived") or {}
    instability_mode = bool(derived.get("instability_mode", False))
    user = OPTION_SET_USER.format(
        actor_role=actor_role,
        actor_name=actor_name,
        goals_json=goals_json,
        risk_tolerance=risk_tolerance,
        instability_mode=instability_mode,
        variables_json=variables_json,
        allowed_actions_json=allowed_actions_json,
    )
    return OPTION_SET_SYSTEM, user


def build_strategic_prompt(
    agent_def: dict[str, Any],
    snapshot: dict[str, Any],
    scenario: dict[str, Any],
    *,
    max_delta: float = 10.0,
    obs_noise_scale: float = 0.0,
) -> tuple[str, str]:
    """
    Build (system_prompt, user_prompt) for the strategic agent format.
    agent_def: name, role; optional risk_tolerance, aggressiveness (for agent_profile_json).
    snapshot: variables or global_state; derived.instability_mode.
    scenario: causal_links, allowed_actions.
    """
    actor_name = agent_def.get("name") or "agent"
    actor_role = agent_def.get("role") or actor_name
    risk_tolerance = agent_def.get("risk_tolerance", 0.5)
    aggressiveness = agent_def.get("aggressiveness", 0.5)
    agent_profile_json = json.dumps({
        "risk_tolerance": risk_tolerance,
        "aggressiveness": aggressiveness,
    })

    variables = snapshot.get("variables") or snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}
    variables_json = json.dumps(variables)

    causal_links = scenario.get("causal_links") or snapshot.get("causal_links") or []
    causal_links_json = json.dumps(causal_links)

    allowed_actions = scenario.get("allowed_actions") or []
    if not isinstance(allowed_actions, list):
        allowed_actions = []
    if scenario.get("enable_meta_actions"):
        allowed_actions = list(allowed_actions) + [
            "propose_new_action", "propose_new_variable", "propose_new_causal_link", "propose_new_event"
        ]
    allowed_actions_json = json.dumps(allowed_actions)

    derived = snapshot.get("derived") or {}
    instability_mode = bool(derived.get("instability_mode", False))

    user = STRATEGIC_USER.format(
        actor_role=actor_role,
        actor_name=actor_name,
        agent_profile_json=agent_profile_json,
        variables_json=variables_json,
        causal_links_json=causal_links_json,
        allowed_actions_json=allowed_actions_json,
        max_delta=max_delta,
        instability_mode=json.dumps(instability_mode),
        observation_noise_scale=obs_noise_scale,
    )
    return STRATEGIC_SYSTEM, user
