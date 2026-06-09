"""
RoleAgent: propose(world_snapshot) -> Proposal using goals + planning (and optional LLM); reflect(history, world_snapshot).
Domain-agnostic: agents are built from scenario initial_agents or dynamically constructed from scenario description.

Text-first cognitive format: propose(world_input) returns a single string with ### REASONING and ### ACTION_JSON.
When world_input is str (summary), LLM produces both; when dict (snapshot), rule-based output is formatted the same way.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from schemas.proposal_schema import Proposal

from agents.base_agent import BaseAgent, rule_based_deltas_for_snapshot
from agents.memory import AgentMemory
from core.agent_constructor import (
    allowed_actions_from_variables,
    construct_agents_from_scenario,
)
from core.llm_service import call_llm as llm_service_call
from core.prompt_builder import build_decision_prompt  # LLM Integration: scenario-to-simulation pipeline
from core.strategic_prompt import build_strategic_prompt

# Strict response format: reasoning (free text) then exactly one JSON block. No trailing commas, no comments.
# Braces in the JSON example are escaped for str.format() ({{ and }} become literal { and }).
RESPONSE_FORMAT_SPEC = """You MUST respond with exactly two sections in this order:

### REASONING
<your free natural language reasoning here>

### ACTION_JSON
{{ "action": "<action_type>", "actor": "<your agent name>", "deltas": [ {{ "variable": "<name>", "change": <number> }}, ... ] }}

Rules: ACTION_JSON must be valid JSON; no trailing commas; no comments; only one JSON block. action must be one of the allowed list; deltas list variable names and numeric changes."""

# Text-first: agent receives world summary (text), outputs reasoning + ACTION_JSON
TEXT_FIRST_SYSTEM_TEMPLATE = """You are the agent "{name}" in role "{role}". Your objectives (importance): {objectives}.
Your current goals: {goals}.
Allowed actions: {allowed_actions}.

""" + RESPONSE_FORMAT_SPEC

TEXT_FIRST_USER_TEMPLATE = """Relevant context from your memory:
{memory_context}

Current world summary:
{world_summary}

Respond with ### REASONING then ### ACTION_JSON as specified. action MUST be one of: {allowed_actions}."""

# RoleAgent propose prompt when using LLM for candidates (legacy)
PROPOSAL_SYSTEM_TEMPLATE = """You are the agent "{name}" in role "{role}". Your objectives (importance): {objectives}.
Your current goals: {goals}.
You MUST respond with a single JSON object only (no markdown, no explanation outside JSON).
Schema: {{ "agent_name": "{name}", "action_type": "<one of: {allowed_actions}>", "parameters": {{}}, "rationale": "short reason", "confidence": 0.0 to 1.0 }}
Output EXACTLY ONE such JSON object. action_type MUST be one of the allowed list."""

PROPOSAL_USER_TEMPLATE = """Relevant context from your memory:
{memory_context}

Current world snapshot (compact):
{world_snapshot}

Choose one action and output your single JSON proposal:"""

CANDIDATES_SYSTEM = """You are agent "{name}". Pick 2-3 action types from this list that best match your goals: {allowed_actions}.
Return a JSON array of strings only, e.g. ["action_a", "action_b"]."""


class RoleAgent(BaseAgent):
    """Agent that proposes actions via goal-driven planning; can use LLM for candidate generation or single proposal."""

    def __init__(
        self,
        name: str,
        role: str,
        objectives: dict[str, float],
        llm_client: Callable[..., Any],
        *,
        allowed_actions: list[str] | None = None,
        long_term_goals: list[str] | None = None,
        memory: AgentMemory | None = None,
        strategy_classes: dict[str, str] | None = None,
        personality: str | None = None,
        display_name: str | None = None,
        initial_variables: dict[str, float] | None = None,
        system_prompt_override: str | None = None,
        risk_tolerance: float = 0.5,
        aggressiveness: float = 0.5,
        allowed_actions_hint: list[str] | None = None,
        personality_modifiers: dict[str, float] | None = None,
    ) -> None:
        super().__init__(
            name, objectives,
            long_term_goals=long_term_goals,
            memory=memory,
            strategy_classes=strategy_classes,
            personality_modifiers=personality_modifiers,
        )
        self.role = role
        self.llm_client = llm_client
        self.allowed_actions = list(allowed_actions or [])
        self.allowed_actions_hint = list(allowed_actions_hint or []) or list(allowed_actions or [])
        # LLM Integration: optional personality and initial_variables for personalized decision prompt
        self.personality = personality if isinstance(personality, str) else None
        self.display_name = display_name if isinstance(display_name, str) else (role or name)
        self.initial_variables = dict(initial_variables) if isinstance(initial_variables, dict) else {}
        # Multi-stage compiler: optional full system prompt override
        self.system_prompt_override = system_prompt_override if isinstance(system_prompt_override, str) and system_prompt_override.strip() else None
        # Strategic agent: profile for prompt (risk_tolerance, aggressiveness)
        self.risk_tolerance = float(risk_tolerance) if isinstance(risk_tolerance, (int, float)) else 0.5
        self.aggressiveness = float(aggressiveness) if isinstance(aggressiveness, (int, float)) else 0.5

    def generate_candidate_actions(self, world_snapshot: dict[str, Any]) -> list[str]:
        """
        Return 2-4 candidate action types. LLM-driven when LLM available; dry-run uses deterministic fallback.
        allowed_actions_hint: hints only, not hard blocks; accept freeform when no hint.
        """
        # Dry-run: deterministic variable-driven or allowed_actions[:4]
        if not self.llm_client:
            turn = int(world_snapshot.get("turn", 0) or 0)
            product_action = world_snapshot.get("product_decision_action")
            if product_action and turn == 0 and self.name == "ops_director":
                return [str(product_action)]
            if self.allowed_actions:
                return self.allowed_actions[:4]
            variables = world_snapshot.get("variables") or world_snapshot.get("global_state") or {}
            if isinstance(variables, dict) and variables:
                first_var = list(variables.keys())[0]
                return [f"increase_{first_var}", f"decrease_{first_var}"]
            return ["adjust_variable"]

        # LLM-driven: propose 2-4 candidates with action_type, brief_rationale, etc.
        prompt = self._build_candidate_prompt(world_snapshot)
        schema = {"required": [], "types": {}}
        client_fn = lambda p, s, **kw: self.llm_client(p, system=s, as_json=True)
        out = llm_service_call(
            prompt,
            system=self._candidate_system_prompt(),
            schema={"required": [], "types": {}},
            temperature=0.6,
            retry=1,
            client_fn=client_fn,
        )
        if isinstance(out, list):
            # Direct array of action_type strings
            cand = [str(a) for a in out[:4] if a]
        elif isinstance(out, dict):
            if "candidates" in out:
                cand = [str(c.get("action_type", "")) for c in out["candidates"] if c.get("action_type")]
            elif "actions" in out:
                cand = [str(a) for a in out["actions"][:4]]
            else:
                cand = []
        else:
            cand = []

        if cand:
            # Validate against allowed_actions_hint if provided; otherwise accept freeform
            hint = self.allowed_actions_hint or self.allowed_actions
            if hint:
                valid = [a for a in cand if a in hint]
                if valid:
                    return valid[:4]
            return cand[:4]

        # Fallback
        if self.allowed_actions:
            return self.allowed_actions[:4]
        variables = world_snapshot.get("variables") or world_snapshot.get("global_state") or {}
        if isinstance(variables, dict) and variables:
            first_var = list(variables.keys())[0]
            return [f"increase_{first_var}", f"decrease_{first_var}"]
        return ["adjust_variable"]

    def _candidate_system_prompt(self) -> str:
        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "candidate_actions.txt"
        if prompt_path.is_file():
            tpl = prompt_path.read_text(encoding="utf-8").strip()
        else:
            tpl = CANDIDATES_SYSTEM + "\n\nReturn JSON array of action_type strings: [\"action_a\", \"action_b\"]"
        return tpl.format(
            name=self.name,
            role=self.role,
            objectives=json.dumps(self.objectives)[:300],
            persona=self.personality or "No specific persona.",
            goals=json.dumps(self.short_term_goals or self.long_term_goals)[:200],
            allowed_actions_hint=json.dumps(self.allowed_actions_hint or self.allowed_actions),
        )

    def _build_candidate_prompt(self, world_snapshot: dict[str, Any]) -> str:
        variables = world_snapshot.get("variables") or world_snapshot.get("global_state") or {}
        return f"""World snapshot: {json.dumps(variables)[:600]}

Propose 2-4 candidate action types as JSON array of objects with action_type, brief_rationale, parameter_hints, estimated_numeric_effects_hint.
Or return simple array of action_type strings: [\"action_a\", \"action_b\"]."""

    def propose(self, world_input: str | dict[str, Any]) -> str:
        """
        Text-first: return a single string with ### REASONING and ### ACTION_JSON.
        - If world_input is dict with "strategic" key: use strategic prompt and LLM.
        - If world_input is dict (snapshot): run rule-based planning and format output.
        - If world_input is str (world summary): call LLM and return raw response.
        """
        if isinstance(world_input, dict) and world_input.get("strategic"):
            snapshot = world_input.get("snapshot") or {}
            scenario = world_input.get("scenario") or {}
            max_delta = world_input.get("max_delta", 10.0)
            obs_noise_scale = world_input.get("obs_noise_scale", 0.0)
            agent_def = {
                "name": self.name,
                "role": self.role,
                "risk_tolerance": getattr(self, "risk_tolerance", 0.5),
                "aggressiveness": getattr(self, "aggressiveness", 0.5),
            }
            system, user = build_strategic_prompt(
                agent_def, snapshot, scenario,
                max_delta=max_delta,
                obs_noise_scale=obs_noise_scale,
            )
            out = self.llm_client(user, system=system, as_json=False)
            if isinstance(out, str):
                return out
            return json.dumps(out) if out is not None else ""
        if isinstance(world_input, dict):
            proposal = self._propose_proposal(world_input)
            if getattr(self, "_last_planning_delta", None) and isinstance(self._last_planning_delta, dict):
                numeric = self._last_planning_delta.get("numeric_updates") or {}
            else:
                rule_deltas = rule_based_deltas_for_snapshot(world_input)
                numeric = rule_deltas.get(proposal.action_type, {})
            return _proposal_to_reasoning_action_string(proposal, numeric)
        # world_input is summary text — LLM Integration: use personalized prompt from prompt_builder
        agent_def = {
            "name": self.name,
            "role": self.role,
            "objectives": self.objectives,
            "long_term_goals": self.long_term_goals,
            "allowed_actions": self.allowed_actions,
            "personality": self.personality,
            "initial_variables": self.initial_variables,
            "system_prompt_override": self.system_prompt_override,
        }
        scenario_context = {"allowed_actions": self.allowed_actions}
        system, user_tpl = build_decision_prompt(agent_def, scenario_context)
        memory_str = (self.memory.get_relevant_context(limit=5) if hasattr(self.memory, "get_relevant_context") else "") or "None"
        memory_str = memory_str[:500] if memory_str else "None"
        user = user_tpl.format(
            memory_context=memory_str,
            world_summary=world_input,
            allowed_actions=json.dumps(self.allowed_actions),
        )
        out = self.llm_client(user, system=system, as_json=False)  # prompt_builder system used
        if isinstance(out, str):
            return out
        return json.dumps(out) if out is not None else ""

    def _propose_proposal(self, world_snapshot: dict[str, Any]) -> Proposal:
        """Internal: run BaseAgent propose flow and return Proposal (for dry-run formatting)."""
        return super().propose(world_snapshot)


def _proposal_to_reasoning_action_string(proposal: Proposal, numeric_updates: dict[str, float]) -> str:
    """Format a Proposal and numeric deltas as ### REASONING and ### ACTION_JSON string."""
    reasoning = getattr(proposal, "rationale", "") or ""
    if isinstance(reasoning, list):
        reasoning = " ".join(str(x) for x in reasoning)
    actor = getattr(proposal, "agent_name", "") or ""
    action = getattr(proposal, "action_type", "") or ""
    deltas = [{"variable": k, "change": v} for k, v in numeric_updates.items()]
    action_json = json.dumps({"action": action, "actor": actor, "deltas": deltas}, ensure_ascii=False)
    return f"### REASONING\n{reasoning}\n\n### ACTION_JSON\n{action_json}"


def _are_agents_fully_qualified(initial: list[dict[str, Any]]) -> bool:
    """True if all agents have non-placeholder names (not actor_1, agent_2, etc.)."""
    import re
    if not initial:
        return False
    placeholder_patterns = (r"^actor_\d+$", r"^agent_\d+$", r"^faction_[a-z]$")
    for cfg in initial:
        if not isinstance(cfg, dict):
            return False
        name = (cfg.get("name") or "").strip().lower()
        for pat in placeholder_patterns:
            if re.match(pat, name):
                return False
    return True


def _get_agents_llm_first(scenario: dict[str, Any], llm_client: Callable[..., Any]) -> list[dict[str, Any]]:
    """LLM-first agent generation. On failure: fallback to 2 generic demo agents."""
    from pathlib import Path
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "agent_generator.txt"
    system = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.is_file() else ""
    if not system:
        return []

    variables = list((scenario.get("initial_state") or {}).keys())
    allowed = scenario.get("allowed_actions")
    if not isinstance(allowed, list):
        allowed = allowed_actions_from_variables(variables, include_adjust=True)
    description = (scenario.get("description") or "Generic scenario.").strip()
    variables_json = json.dumps(scenario.get("initial_state") or {})
    allowed_json = json.dumps(allowed)

    prompt = f"""Scenario description: {description}

Initial state variables: {variables_json}
Allowed actions hint: {allowed_json}

Generate the agents JSON object only."""

    schema = {"required": ["agents"], "types": {"agents": "list"}}
    client_fn = lambda p, s, **kw: llm_client(p, system=s, as_json=True)
    out = llm_service_call(
        prompt,
        system=system,
        schema=schema,
        temperature=0.7,
        retry=1,
        client_fn=client_fn,
    )
    if not isinstance(out, dict) or "agents" not in out:
        return _demo_fallback_agents(variables)
    agents = out.get("agents")
    if not isinstance(agents, list) or len(agents) == 0:
        return _demo_fallback_agents(variables)
    return _normalize_llm_agents(agents, variables)


def _demo_fallback_agents(variables: list[str]) -> list[dict[str, Any]]:
    """2 generic demo agents for continuity when LLM fails. No placeholder names."""
    if not variables:
        variables = ["primary_metric"]
    return [
        {"name": "participant_a", "role": "Participant A", "display_name": "Participant A", "objectives": {f"increase_{variables[0]}": 0.5}, "long_term_goals": [f"increase_{variables[0]}"], "personality": "Neutral."},
        {"name": "participant_b", "role": "Participant B", "display_name": "Participant B", "objectives": {f"decrease_{variables[0]}": 0.5}, "long_term_goals": [f"decrease_{variables[0]}"], "personality": "Neutral."},
    ]


def _normalize_llm_agents(agents: list[dict[str, Any]], variables: list[str]) -> list[dict[str, Any]]:
    """Normalize LLM agent output to initial_agents format."""
    result = []
    for i, a in enumerate(agents):
        if not isinstance(a, dict):
            continue
        name = (a.get("name") or a.get("role") or f"participant_{chr(ord('a') + i)}").replace(" ", "_").lower()[:64]
        role = (a.get("role") or name).strip() if isinstance(a.get("role"), str) else name.replace("_", " ").title()
        display_name = a.get("display_name") or role
        objectives = a.get("objectives")
        if not isinstance(objectives, dict):
            objectives = _objectives_from_variables(variables)
        personality = a.get("personality") if isinstance(a.get("personality"), str) else None
        initial_vars = a.get("initial_variables") if isinstance(a.get("initial_variables"), dict) else {}
        long_term_goals = a.get("long_term_goals")
        if not isinstance(long_term_goals, list):
            long_term_goals = list(objectives.keys())[:4] if objectives else [f"adjust_{v}" for v in variables[:2]]
        allowed_hint = a.get("allowed_actions_hint")
        if not isinstance(allowed_hint, list):
            allowed_hint = []
        result.append({
            "name": name,
            "role": role,
            "display_name": display_name,
            "objectives": objectives,
            "long_term_goals": [str(g) for g in long_term_goals if g][:4],
            "personality": personality,
            "initial_variables": initial_vars,
            "allowed_actions_hint": allowed_hint,
        })
    return result if result else _demo_fallback_agents(variables)


def get_agents_from_scenario(
    scenario: dict[str, Any],
    llm_client: Callable[..., Any],
    *,
    dry_run: bool = False,
) -> list[RoleAgent]:
    """
    Build RoleAgents from scenario. Domain-agnostic.
    - If initial_agents present and fully qualified (name != actor_1): use them.
    - Else: LLM-first agent generation (when not dry_run); fallback to 2 generic demo agents.
    allowed_actions: from scenario if non-empty, else derived from initial_state variables.
    """
    initial = scenario.get("initial_agents") or []
    if not isinstance(initial, list):
        initial = []
    if len(initial) > 0 and _are_agents_fully_qualified(initial):
        agent_configs = list(initial)
    elif not dry_run and llm_client:
        agent_configs = _get_agents_llm_first(scenario, llm_client)
        if not agent_configs:
            agent_configs = construct_agents_from_scenario(scenario, llm_client, dry_run=True)
    else:
        agent_configs = construct_agents_from_scenario(scenario, llm_client, dry_run=dry_run)
    variables = list((scenario.get("initial_state") or {}).keys())
    allowed_actions = scenario.get("allowed_actions")
    if not isinstance(allowed_actions, list) or len(allowed_actions) == 0:
        allowed_actions = allowed_actions_from_variables(variables, include_adjust=True)
    strategy_classes = scenario.get("strategy_classes")
    if not isinstance(strategy_classes, dict):
        strategy_classes = {}

    out: list[RoleAgent] = []
    for cfg in agent_configs:
        if not isinstance(cfg, dict):
            continue
        name = cfg.get("name") or "agent"
        role = cfg.get("role") or name
        display_name = cfg.get("display_name") or role
        objectives = cfg.get("objectives")
        if not isinstance(objectives, dict):
            objectives = _objectives_from_variables(variables)
        long_term_goals = cfg.get("long_term_goals")
        if not isinstance(long_term_goals, list):
            if objectives:
                long_term_goals = list(objectives.keys())[:4]
            elif variables:
                long_term_goals = [f"adjust_{v}" for v in variables[:4]]
            else:
                long_term_goals = ["adjust_variable"]
        personality = cfg.get("personality") if isinstance(cfg.get("personality"), str) else None
        initial_vars = cfg.get("initial_variables")
        if not isinstance(initial_vars, dict):
            initial_vars = {}
        allowed_hint = cfg.get("allowed_actions_hint")
        if not isinstance(allowed_hint, list):
            allowed_hint = []
        agent_allowed = cfg.get("allowed_actions")
        if not isinstance(agent_allowed, list) or not agent_allowed:
            agent_allowed = allowed_actions
        memory = AgentMemory(initial_variables=initial_vars if initial_vars else None)
        system_prompt_override = cfg.get("system_prompt_override") if isinstance(cfg.get("system_prompt_override"), str) else None
        risk_tolerance = float(cfg.get("risk_tolerance", 0.5)) if isinstance(cfg.get("risk_tolerance"), (int, float)) else 0.5
        aggressiveness = float(cfg.get("aggressiveness", 0.5)) if isinstance(cfg.get("aggressiveness"), (int, float)) else 0.5
        personality_modifiers = cfg.get("personality_modifiers") if isinstance(cfg.get("personality_modifiers"), dict) else None
        out.append(RoleAgent(
            name=str(name),
            role=str(role),
            objectives=dict(objectives),
            llm_client=llm_client,
            allowed_actions=agent_allowed,
            long_term_goals=long_term_goals,
            strategy_classes=strategy_classes,
            memory=memory,
            personality=personality,
            display_name=display_name,
            initial_variables=initial_vars,
            system_prompt_override=system_prompt_override,
            risk_tolerance=risk_tolerance,
            aggressiveness=aggressiveness,
            allowed_actions_hint=allowed_hint or agent_allowed,
            personality_modifiers=personality_modifiers,
        ))
    return out


def _objectives_from_variables(variables: list[str]) -> dict[str, float]:
    """Neutral objectives from variable names (e.g. increase_X, decrease_X with equal weight)."""
    if not variables:
        return {"steady": 0.5}
    obj: dict[str, float] = {}
    for v in variables[:5]:
        obj[f"increase_{v}"] = 0.3
        obj[f"decrease_{v}"] = 0.2
    return obj


def get_demo_agents(
    llm_client: Callable[..., Any],
    allowed_actions: list[str] | None = None,
    *,
    scenario: dict[str, Any] | None = None,
) -> list[RoleAgent]:
    """Backward-compatible: build agents from scenario via get_agents_from_scenario when scenario provided; else construct dynamically."""
    if scenario and (scenario.get("initial_agents") or list((scenario.get("initial_state") or {}).keys())):
        return get_agents_from_scenario(scenario, llm_client, dry_run=False)
    # Dynamic fallback: create generic scenario with variable-driven agents
    variables = list((scenario.get("initial_state") or {}).keys()) if scenario else []
    if not variables:
        variables = ["state"]  # Default fallback variable
    demo_scenario = {
        "description": scenario.get("description", "Demo scenario") if scenario else "Demo scenario",
        "initial_agents": [],  # Empty to trigger dynamic construction
        "initial_state": scenario.get("initial_state", {v: 50.0 for v in variables}) if scenario else {v: 50.0 for v in variables},
        "relations": scenario.get("relations", []) if scenario else [],
        "allowed_actions": allowed_actions or allowed_actions_from_variables(variables, include_adjust=True),
    }
    return get_agents_from_scenario(demo_scenario, llm_client, dry_run=False)
