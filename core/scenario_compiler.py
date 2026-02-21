"""
Multi-stage scenario compiler: compile free-text scenario through structured LLM stages
into engine-compatible scenario JSON (roles → world model → agent objectives → action space → prompts).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Callable

from schemas.scenario_schema import normalize_scenario

logger = logging.getLogger("open_world_engine.scenario_compiler")

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_MAX = 50

RETRY_PROMPT = "Your previous output was invalid JSON. Return ONLY valid JSON."


class ScenarioCompilationError(Exception):
    """Raised when a compilation stage fails after retry."""

    def __init__(self, stage_name: str, message: str) -> None:
        self.stage_name = stage_name
        self.message = message
        super().__init__(f"[{stage_name}] {message}")


def _strip_markdown_json(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _parse_json_response(raw: str | dict, stage_name: str) -> dict[str, Any] | list[Any]:
    """Parse LLM response to JSON; raise ScenarioCompilationError on failure."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return raw
    s = _strip_markdown_json(str(raw))
    try:
        out = json.loads(s)
    except json.JSONDecodeError as e:
        raise ScenarioCompilationError(stage_name, f"Invalid JSON: {e}") from e
    return out


# --- Stage prompts ---

STAGE1_SYSTEM = """You are a geopolitical and multi-agent systems analyst.
Extract the key actors implied by the scenario.
Return a JSON array with:
- name (short identifier, snake_case)
- role (descriptive string)
- power_level (float 0-1)
- alignment (string, optional)

Max 4 actors.
Output JSON only."""

STAGE1_USER = """Scenario:
{scenario_text}"""

STAGE2_SYSTEM = """You are a systems modeler.
Based on the scenario and actors, define the system state.

Return JSON object:
{
  "variables": { "variable_name": numeric_value_0_100 },
  "causal_links": [
     { "from": "variable", "to": "variable", "polarity": "positive|negative" }
  ]
}

Variables must represent system-level quantities.
Do not use agent names as variables.
Use 4-8 variables.
Output JSON only."""

STAGE2_USER = """Scenario:
{scenario_text}

Actors:
{actors_json}"""

STAGE3_SYSTEM = """You are designing autonomous strategic agents.
For each actor, define objectives referencing world variables.

Return JSON object:
{
  "actor_name": {
    "objectives": {
       "increase_variable": weight_0_to_1,
       "decrease_variable": weight_0_to_1
    },
    "risk_tolerance": float_0_to_1,
    "aggressiveness": float_0_to_1
  }
}

Each objective must reference an existing world variable.
Output JSON only."""

STAGE3_USER = """Actors:
{actors_json}

World Variables:
{variables_json}"""

STAGE4_SYSTEM = """Generate allowed actions for this system.

Rules:
- For each world variable X, include:
  - increase_X
  - decrease_X
- Also include 2-4 high-level strategic actions that may affect multiple variables.

Return JSON array of strings.
Output JSON only."""

STAGE4_USER = """World Variables:
{variables_json}

Actors:
{actors_json}"""

# --- Response format for build_agent_prompt (engine-compatible) ---
RESPONSE_FORMAT_BLOCK = """
Respond with exactly two sections in this order:

### REASONING
<your free natural language reasoning here>

### ACTION_JSON
{{ "action": "<action_type>", "actor": "<your agent name>", "deltas": [ {{ "variable": "<name>", "change": <number> }}, ... ] }}

Rules: ACTION_JSON must be valid JSON; action must be one of the allowed list; deltas list variable names and numeric changes."""


def build_agent_prompt(
    actor: dict[str, Any],
    profile: dict[str, Any],
    world_model: dict[str, Any],
    allowed_actions: list[str],
) -> str:
    """
    Generate dynamic system prompt for an agent (Stage 5, no LLM).
    Uses engine-compatible response format (### REASONING + ### ACTION_JSON with action, actor, deltas).
    """
    name = actor.get("name") or "agent"
    role = actor.get("role") or name
    objectives = profile.get("objectives") or {}
    risk_tolerance = profile.get("risk_tolerance", 0.5)
    aggressiveness = profile.get("aggressiveness", 0.5)
    variables = world_model.get("variables") or {}
    causal_links = world_model.get("causal_links") or []

    objectives_str = json.dumps(objectives, indent=2)
    variables_str = json.dumps(variables, indent=2)
    causal_str = json.dumps(causal_links, indent=2)
    actions_str = json.dumps(allowed_actions)

    return f"""You are {role} in a strategic multi-agent simulation.

Your objectives:
{objectives_str}

Risk tolerance: {risk_tolerance}
Aggressiveness: {aggressiveness}

Current world state:
{variables_str}

Causal structure:
{causal_str}

Each turn you must choose ONE action from:
{actions_str}
{RESPONSE_FORMAT_BLOCK}"""


def _run_stage(
    stage_name: str,
    user_prompt: str,
    system_prompt: str,
    llm_client: Callable[..., Any],
    config: dict[str, Any],
    validator: Callable[[Any], str | None],
) -> Any:
    """Run one LLM stage with optional retry. Returns parsed result; raises on second failure."""
    debug = config.get("debug_llm", False)
    if debug:
        logger.debug("Stage %s: start", stage_name)

    last_error: Exception | None = None
    prompt = user_prompt
    for attempt in range(2):
        try:
            out = llm_client(prompt, system=system_prompt, as_json=True)
            parsed = _parse_json_response(out, stage_name)
            err = validator(parsed)
            if err:
                last_error = ScenarioCompilationError(stage_name, err)
                if attempt == 0:
                    prompt = prompt + "\n\n" + RETRY_PROMPT
                    if debug:
                        logger.debug("Stage %s: retry after validation error", stage_name)
                    continue
                raise last_error
            if debug:
                logger.debug("Stage %s: ok", stage_name)
            return parsed
        except ScenarioCompilationError as e:
            last_error = e
            if attempt == 0:
                prompt = prompt + "\n\n" + RETRY_PROMPT
                if debug:
                    logger.debug("Stage %s: retry after %s", stage_name, e)
                continue
            raise
        except Exception as e:
            last_error = e
            if attempt == 0:
                prompt = prompt + "\n\n" + RETRY_PROMPT
                if debug:
                    logger.debug("Stage %s: retry after %s", stage_name, e)
                continue
            if debug:
                logger.debug("Stage %s: fail", stage_name)
            raise ScenarioCompilationError(stage_name, str(e)) from e
    if last_error:
        raise last_error
    raise ScenarioCompilationError(stage_name, "Validation failed after retry")


def _validate_stage1(data: Any) -> str | None:
    if not isinstance(data, list):
        return "Stage 1 must return a JSON array"
    for i, el in enumerate(data):
        if not isinstance(el, dict):
            return f"Stage 1 element {i} must be an object"
        if "name" not in el or not isinstance(el.get("name"), str):
            return f"Stage 1 element {i} must have string 'name'"
        if "role" not in el or not isinstance(el.get("role"), str):
            return f"Stage 1 element {i} must have string 'role'"
    if len(data) == 0:
        return "Stage 1 must return at least one actor"
    return None


def _validate_stage2(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "Stage 2 must return a JSON object"
    if "variables" not in data:
        return "Stage 2 must have 'variables'"
    if not isinstance(data["variables"], dict):
        return "Stage 2 'variables' must be an object"
    if "causal_links" not in data:
        return "Stage 2 must have 'causal_links'"
    if not isinstance(data["causal_links"], list):
        return "Stage 2 'causal_links' must be an array"
    for i, link in enumerate(data["causal_links"]):
        if not isinstance(link, dict) or "from" not in link or "to" not in link or "polarity" not in link:
            return f"Stage 2 causal_links[{i}] must have from, to, polarity"
    return None


def _validate_stage3(data: Any, actor_names: list[str], variable_names: set[str]) -> str | None:
    if not isinstance(data, dict):
        return "Stage 3 must return a JSON object"
    for name in actor_names:
        if name not in data:
            return f"Stage 3 must include actor '{name}'"
        prof = data[name]
        if not isinstance(prof, dict):
            return f"Stage 3 profile for '{name}' must be an object"
        if "objectives" not in prof:
            return f"Stage 3 profile for '{name}' must have 'objectives'"
        obj = prof["objectives"]
        if not isinstance(obj, dict):
            return f"Stage 3 objectives for '{name}' must be an object"
        for key in obj:
            # increase_X or decrease_X -> X must be in variable_names
            if key.startswith("increase_"):
                var = key[9:]
                if var and var not in variable_names:
                    return f"Stage 3 objective '{key}' references unknown variable '{var}'"
            elif key.startswith("decrease_"):
                var = key[9:]
                if var and var not in variable_names:
                    return f"Stage 3 objective '{key}' references unknown variable '{var}'"
    return None


def _validate_stage4(data: Any) -> str | None:
    if not isinstance(data, list):
        return "Stage 4 must return a JSON array"
    for i, x in enumerate(data):
        if not isinstance(x, str):
            return f"Stage 4 element {i} must be a string"
    return None


def _derive_relations(actors: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Derive relations from actor alignments (opposing alignment -> conflicts_with)."""
    relations: list[dict[str, str]] = []
    names = [a.get("name") for a in actors if isinstance(a.get("name"), str)]
    alignments = {a.get("name"): (a.get("alignment") or "").strip().lower() for a in actors if isinstance(a, dict)}
    for i, n1 in enumerate(names):
        for n2 in names[i + 1 :]:
            if not n1 or not n2:
                continue
            a1, a2 = alignments.get(n1, ""), alignments.get(n2, "")
            if a1 and a2 and a1 != a2:
                if any(x in a1 for x in ("adversar", "oppos", "hostile", "conflict")) or any(
                    x in a2 for x in ("adversar", "oppos", "hostile", "conflict")
                ):
                    relations.append({"from": n1, "to": n2, "type": "conflicts_with"})
    return relations


def compile_scenario(text: str, llm_client: Callable[..., Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    Run multi-stage LLM compilation pipeline.
    Returns fully structured scenario JSON compatible with the simulation engine.
    Uses in-memory cache keyed by hash(text). On any stage failure after retry, raises ScenarioCompilationError.
    """
    text = (text or "").strip()
    if not text:
        raise ScenarioCompilationError("compile", "Scenario text is empty")

    cache_key = hashlib.sha256(text.encode()).hexdigest()
    if cache_key in _CACHE:
        return dict(_CACHE[cache_key])

    debug = config.get("debug_llm", False)
    if debug:
        logger.debug("Compile start (stages 1-5)")

    # Stage 1: Role extraction
    user1 = STAGE1_USER.format(scenario_text=text)
    actors_list = _run_stage("Role Extraction", user1, STAGE1_SYSTEM, llm_client, config, _validate_stage1)
    actors_json = json.dumps(actors_list, ensure_ascii=False)

    # Stage 2: World model
    user2 = STAGE2_USER.format(scenario_text=text, actors_json=actors_json)
    world_model = _run_stage("World Modeling", user2, STAGE2_SYSTEM, llm_client, config, _validate_stage2)
    variables = world_model.get("variables") or {}
    variables_json = json.dumps(variables, ensure_ascii=False)
    variable_names = set(variables.keys())

    # Stage 3: Agent objectives
    user3 = STAGE3_USER.format(actors_json=actors_json, variables_json=variables_json)
    actor_names = [a.get("name") for a in actors_list if isinstance(a, dict) and a.get("name")]

    def validate3(data: Any) -> str | None:
        return _validate_stage3(data, actor_names, variable_names)

    agent_profiles = _run_stage("Agent Objective Modeling", user3, STAGE3_SYSTEM, llm_client, config, validate3)

    # Stage 4: Action space
    user4 = STAGE4_USER.format(variables_json=variables_json, actors_json=actors_json)
    allowed_actions = _run_stage("Action Space", user4, STAGE4_SYSTEM, llm_client, config, _validate_stage4)

    # Stage 5: Agent prompt construction (no LLM) + assembly
    initial_agents: list[dict[str, Any]] = []
    for a in actors_list:
        if not isinstance(a, dict):
            continue
        name = a.get("name")
        if not name or name not in agent_profiles:
            continue
        profile = agent_profiles[name]
        objectives = profile.get("objectives") or {}
        risk_tolerance = profile.get("risk_tolerance", 0.5)
        aggressiveness = profile.get("aggressiveness", 0.5)
        agent_entry: dict[str, Any] = {
            "name": name,
            "role": a.get("role") or name,
            "objectives": objectives,
        }
        agent_entry["risk_tolerance"] = risk_tolerance
        agent_entry["aggressiveness"] = aggressiveness
        system_prompt_override = build_agent_prompt(a, profile, world_model, allowed_actions)
        agent_entry["system_prompt_override"] = system_prompt_override
        initial_agents.append(agent_entry)

    relations = _derive_relations(actors_list)
    scenario = {
        "description": text,
        "initial_agents": initial_agents,
        "initial_state": dict(variables),
        "relations": relations,
        "allowed_actions": list(allowed_actions),
        "causal_links": list(world_model.get("causal_links") or []),
    }
    scenario = normalize_scenario(scenario)

    if len(_CACHE) >= _CACHE_MAX:
        # Drop oldest half by keys (arbitrary eviction)
        for k in list(_CACHE.keys())[: _CACHE_MAX // 2]:
            del _CACHE[k]
    _CACHE[cache_key] = scenario

    if debug:
        logger.debug("Compile done")

    return dict(scenario)
