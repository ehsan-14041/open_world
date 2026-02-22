"""
SimulationLoop: load scenario, build world/agents/WMA/governance/ontology.
step(): collect proposals -> normalize (or action_spec interpreter) -> validate -> apply -> propagation -> delayed_events/event_queue -> rules -> reflect.
run(steps): print snapshot each turn; optional save final snapshot; optional return trace for narrative.
Architecture: causal variable graph, agent beliefs, rule engine, event queue, action contract, trace — see docs/ARCHITECTURE.md.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

from config.settings import (
    SCENARIO_PATH,
    DRY_RUN,
    MAX_LLM_CALLS_PER_TURN,
    SNAPSHOT_PATH,
    META_PROPOSAL_AUTO_APPROVE_MAX_AGENTS,
    MAX_DELTA,
    OBS_NOISE_SCALE,
    ENABLE_ENVIRONMENT_AGENT,
    CHANGE_BUDGET,
    get_settings,
    ALLOW_NUMBERS,
    ENABLE_SHOCKS,
    LANG,
    RANDOM_SEED,
)
from core.llm_client import call_llm
from core.world_model import WorldModel
from core.ontology_manager import OntologyManager
from core.rule_engine import run_rules
from core.action_interpreter import interpret_action_spec_with_world
from core.governance import Governance
from core.world_summarizer import summarize as world_summarize, detect_language
from core.llm_action_guard import LLMActionGuard
from core.soft_constraints import apply_all_constraints
from core.action_definitions_store import build_action_definitions_from_scenario, get_delta_vector
from core.delta_attribution import compute_self_effect_per_agent, merge_delta_raw
from schemas.delta_schema import Delta
from schemas.proposal_schema import Proposal
from schemas.scenario_schema import normalize_scenario
from agents.agents import get_agents_from_scenario
from agents.world_model_agent import WorldModelAgent
from agents.environment_agent import EnvironmentAgent

# Max attempts per agent when extraction/validation fails (retry with correction prompt once)
MAX_ACTION_JSON_ATTEMPTS = 2


def _make_json_safe(obj: object) -> object:
    """Replace float('nan')/inf with None so saved JSON is valid (no NaN/Infinity literals)."""
    if obj is None:
        return None
    if isinstance(obj, float):
        if obj != obj or obj == float("inf") or obj == float("-inf"):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    return obj


def load_scenario(path: str | Path) -> dict[str, Any]:
    """Load scenario JSON from path."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Scenario not found: {path}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _scenario_from_path_or_data(
    scenario_path: str | Path | None,
    scenario_data: dict[str, Any] | None,
    default_path: str,
) -> dict[str, Any]:
    """Resolve scenario: use scenario_data if provided, else load from scenario_path or default_path."""
    if scenario_data is not None:
        return scenario_data
    path = scenario_path or default_path
    return load_scenario(path)


def _parse_reasoning_from_output(agent_output: str) -> str:
    """Extract the reasoning text (between start and ### ACTION_JSON). Engine never sees this."""
    if not agent_output or not isinstance(agent_output, str):
        return ""
    marker = "### REASONING"
    end_marker = "### ACTION_JSON"
    idx = agent_output.find(marker)
    if idx < 0:
        return ""
    start = idx + len(marker)
    end_idx = agent_output.find(end_marker, start)
    if end_idx < 0:
        return agent_output[start:].strip()
    return agent_output[start:end_idx].strip()


def _compute_stability_and_dissatisfaction(
    snapshot: dict[str, Any],
    scenario: dict[str, Any],
) -> tuple[float, float]:
    """Return (system_stability, dissatisfaction). Use scenario vars or compute from state."""
    variables = snapshot.get("variables") or snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        return 70.0, 30.0
    gov = scenario.get("governance") or {}
    stability_var = (gov if isinstance(gov, dict) else {}).get("stability_variable") or "system_stability"
    diss_var = (gov if isinstance(gov, dict) else {}).get("dissatisfaction_variable") or "public_dissatisfaction"
    if diss_var not in variables:
        diss_var = "dissatisfaction"
    stability = 70.0
    if stability_var in variables and isinstance(variables[stability_var], (int, float)):
        stability = float(variables[stability_var])
    else:
        # Compute from variance of key variables (inverse scale)
        vals = [float(v) for v in variables.values() if isinstance(v, (int, float))]
        if len(vals) >= 2:
            mean = sum(vals) / len(vals)
            variance = sum((x - mean) ** 2 for x in vals) / len(vals)
            stability = max(0, min(100, 100 - min(100, variance * 0.5)))
    dissatisfaction = 30.0
    if diss_var in variables and isinstance(variables[diss_var], (int, float)):
        dissatisfaction = float(variables[diss_var])
    else:
        # Invert a "satisfaction" variable if present
        for k, v in variables.items():
            if "satisfaction" in k.lower() and isinstance(v, (int, float)):
                dissatisfaction = 100 - float(v)
                break
    return stability, dissatisfaction


class SimulationLoop:
    """Wires world, agents, WorldModelAgent, governance, ontology; runs steps with optional snapshot."""

    def __init__(
        self,
        scenario_path: str | None = None,
        *,
        scenario_data: dict[str, Any] | None = None,
        dry_run: bool = False,
        max_llm_per_turn: int = 20,
        snapshot_path: str | None = None,
        meta_auto_approve_agents: int = 1,
        enable_environment_agent: bool | None = None,
    ) -> None:
        self.scenario_path = scenario_path or SCENARIO_PATH
        self.scenario_data = scenario_data
        self.dry_run = dry_run or DRY_RUN
        self.max_llm_per_turn = max_llm_per_turn or MAX_LLM_CALLS_PER_TURN
        self.snapshot_path = snapshot_path or SNAPSHOT_PATH
        self.meta_auto_approve = meta_auto_approve_agents if meta_auto_approve_agents is not None else META_PROPOSAL_AUTO_APPROVE_MAX_AGENTS

        scenario = _scenario_from_path_or_data(
            self.scenario_path, self.scenario_data, SCENARIO_PATH
        )
        scenario = normalize_scenario(scenario)
        initial_state = scenario.get("initial_state") or {}
        relations = scenario.get("relations") or []
        causal_links = scenario.get("causal_links") or []
        scenario_events = scenario.get("events") or []

        self.world = WorldModel(
            global_state=dict(initial_state),
            variables=None,
            causal_links=list(causal_links),
            relations=list(relations),
            entities={},
            narrative=[],
            ontology={},
            version=0,
            turn=0,
            events=list(scenario_events),
        )
        self.ontology_manager = OntologyManager()
        self._scenario = scenario
        governance_config = scenario.get("governance") or {}
        if not isinstance(governance_config, dict):
            governance_config = {}
        self.governance = Governance(
            auto_approve_max_agents=self.meta_auto_approve,
            strictness_level=int(governance_config.get("strictness_level", 1)),
            require_tradeoffs=bool(governance_config.get("require_tradeoffs", True)),
        )

        def llm_wrapper(prompt: str, system: str | None = None, *, as_json: bool = False) -> Any:
            if self.dry_run:
                if as_json:
                    return {}
                return ""
            return call_llm(prompt, system=system, as_json=as_json)

        self.agents = get_agents_from_scenario(scenario, llm_wrapper, dry_run=self.dry_run)
        self.world_model_agent = WorldModelAgent(llm_wrapper)
        allowed_actions = scenario.get("allowed_actions")
        if not isinstance(allowed_actions, list) or len(allowed_actions) == 0:
            from pipeline.action_space_deriver import ActionSpaceDeriver
            variables_dict = dict(initial_state)
            causal_links = scenario.get("causal_links") or []
            incentives = {a.get("name"): {"objectives": a.get("objectives", {})} for a in (scenario.get("initial_agents") or []) if isinstance(a, dict) and a.get("name")}
            entities = scenario.get("initial_agents") or []
            allowed_actions = ActionSpaceDeriver.derive(variables_dict, causal_links, incentives, entities)
        if scenario.get("enable_meta_actions"):
            meta_actions = ["propose_new_action", "propose_new_variable", "propose_new_causal_link", "propose_new_event"]
            allowed_actions = list(allowed_actions) + [a for a in meta_actions if a not in allowed_actions]
        self._strategic_format = (scenario.get("agent_response_format") or "legacy") == "strategic"
        self._option_set_format = (scenario.get("agent_response_format") or "") == "option_set"
        self._max_delta = float(MAX_DELTA)
        self._obs_noise_scale = float(OBS_NOISE_SCALE)
        # Dry-run agents always output legacy format (action, actor, deltas)
        self._guard = LLMActionGuard(
            allowed_actions=allowed_actions,
            strategic_format=(self._strategic_format or self._option_set_format) and not self.dry_run,
            max_delta=self._max_delta,
        )
        self._environment_agent: EnvironmentAgent | None = None
        use_env_agent = enable_environment_agent if enable_environment_agent is not None else ENABLE_ENVIRONMENT_AGENT
        if use_env_agent:
            self._environment_agent = EnvironmentAgent(llm_wrapper, dry_run=self.dry_run)
        self._variable_specs = scenario.get("variable_specs") or {}
        self._change_budget = scenario.get("change_budget") or CHANGE_BUDGET
        self._action_definitions = build_action_definitions_from_scenario(scenario)
        self._llm_calls_this_turn = 0
        self._provenance: list[dict[str, Any]] = []
        self._action_trace: list[dict[str, Any]] = []
        self._scenario_rules: list[dict[str, Any]] = list(scenario.get("rules") or [])
        # Instability: track dissatisfaction for "rises 2 turns consecutively"
        self._dissatisfaction_history: list[float] = []
        # Track rule-based fallback count for governance escalation
        self._rule_based_fallback_count = 0
        # Track turn degradation status
        self._turn_degraded = False
        # Track agent action history for oscillation detection (per agent: last 2 actions)
        self._agent_action_history: dict[str, list[str]] = {}
        # Track world entropy history (last 2 turns) for instability detection
        self._entropy_history: list[float] = []

    def _consume_llm_capacity(self) -> bool:
        """Return True if we can make another LLM call (rate limit)."""
        if self.dry_run:
            return False
        if self._llm_calls_this_turn >= self.max_llm_per_turn:
            return False
        self._llm_calls_this_turn += 1
        return True
    
    def _compute_world_entropy(self) -> float:
        """
        Compute world entropy as variance of all variables.
        Returns variance of all numeric variables in the world.
        """
        variables = self.world.variables
        if not variables:
            return 0.0
        values = [v for v in variables.values() if isinstance(v, (int, float))]
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance
    
    def _ensure_minimum_delta(self, merged_numeric: dict[str, float]) -> dict[str, float]:
        """
        Ensure at least one variable changes each turn.
        If no variables changed, inject systemic drift.
        """
        # Check if any variable actually changed (non-zero delta)
        has_changes = any(
            isinstance(v, (int, float)) and abs(v) > 1e-6 
            for v in merged_numeric.values()
        )
        
        if not has_changes and self.world.variables:
            # No changes detected - inject systemic drift
            variables = list(self.world.variables.keys())
            if variables:
                # Select random variable
                var = random.choice(variables)
                # Compute volatility (standard deviation of recent values)
                # For now, use a simple volatility estimate based on current value
                current_value = self.world.variables.get(var, 0.0)
                if isinstance(current_value, (int, float)):
                    # Scale drift by current value magnitude (10% of value as std dev)
                    volatility_scale = abs(current_value) * 0.1 if abs(current_value) > 0 else 1.0
                else:
                    volatility_scale = 1.0
                
                # Generate gaussian noise scaled by volatility
                drift = random.gauss(0, volatility_scale)
                merged_numeric[var] = drift
                
                import logging
                logging.getLogger(__name__).info(
                    f"Minimum delta guarantee: injected systemic drift {drift:.3f} to variable '{var}' "
                    f"(volatility_scale={volatility_scale:.3f})"
                )
        
        return merged_numeric
    
    def _apply_oscillation_penalty(self, agent_name: str, current_action: str) -> None:
        """
        Anti-oscillation logic: If agent alternates between opposite actions (increase_X → decrease_X within 2 turns),
        reduce utility weight of that dimension by 40%.
        """
        if agent_name not in self._agent_action_history:
            return
        
        history = self._agent_action_history[agent_name]
        if len(history) < 2:
            return
        
        # Check if last two actions are opposites (increase_X vs decrease_X)
        last_action = history[-1] if history else ""
        prev_action = history[-2] if len(history) >= 2 else ""
        
        # Detect opposite pattern
        is_opposite = False
        var_name = None
        
        if last_action.startswith("increase_") and prev_action.startswith("decrease_"):
            var_last = last_action[len("increase_"):]
            var_prev = prev_action[len("decrease_"):]
            if var_last == var_prev:
                is_opposite = True
                var_name = var_last
        elif last_action.startswith("decrease_") and prev_action.startswith("increase_"):
            var_last = last_action[len("decrease_"):]
            var_prev = prev_action[len("increase_"):]
            if var_last == var_prev:
                is_opposite = True
                var_name = var_last
        
        if is_opposite and var_name:
            # Find agent and reduce utility weight
            for agent in self.agents:
                if agent.name == agent_name:
                    # Reduce weight for this variable dimension by 40%
                    goal_keys_to_reduce = [
                        f"increase_{var_name}",
                        f"decrease_{var_name}",
                        var_name,
                    ]
                    for key in goal_keys_to_reduce:
                        if key in agent.objectives:
                            agent.objectives[key] = max(0.0, agent.objectives[key] * 0.6)  # Reduce by 40%
                    import logging
                    logging.getLogger(__name__).info(
                        f"Anti-oscillation: Reduced utility weight for '{var_name}' by 40% for agent '{agent_name}' "
                        f"due to oscillation pattern ({prev_action} → {last_action})"
                    )
                    break

    def step(self) -> None:
        """One step: collect proposals -> normalize -> validate -> apply -> meta approval -> reflect."""
        self._llm_calls_this_turn = 0
        
        # Decay memory for all agents at start of step
        for agent in self.agents:
            if hasattr(agent, "decay_memory"):
                agent.decay_memory()

        snapshot = self.world.snapshot()
        # Environment agent runs BEFORE role agents (events can influence same turn)
        env_events_this_turn: list[dict[str, Any]] = []
        if self._environment_agent:
            proposed = self._environment_agent.propose(snapshot)
            for ev in proposed:
                ev["trigger_turn"] = self.world.turn + 1
                self.world.events.append(ev)
                env_events_this_turn.append(ev)
        # Instability and threshold dynamics: compute and expose to agents
        stability, dissatisfaction = _compute_stability_and_dissatisfaction(snapshot, self._scenario)
        dissatisfaction_rose_two_turns = (
            len(self._dissatisfaction_history) >= 2
            and dissatisfaction > self._dissatisfaction_history[-1]
            and self._dissatisfaction_history[-1] > self._dissatisfaction_history[-2]
        )
        instability_mode = stability < 50 or dissatisfaction_rose_two_turns
        self._dissatisfaction_history.append(dissatisfaction)
        self._dissatisfaction_history = self._dissatisfaction_history[-3:]
        snapshot = dict(snapshot)
        snapshot.setdefault("derived", {})
        snapshot["derived"]["instability_mode"] = instability_mode
        snapshot["derived"]["system_stability"] = stability
        snapshot["derived"]["dissatisfaction"] = dissatisfaction
        # Merge action_tradeoffs for rule-based planning (agents.base_agent.rule_based_deltas_for_snapshot)
        if action_tradeoffs := self._scenario.get("action_tradeoffs"):
            snapshot["action_tradeoffs"] = action_tradeoffs

        # Text-first: agents receive summary (or snapshot in dry-run) and return reasoning + ACTION_JSON string
        # Dry-run: rule-based path (snapshot). Strategic: LLM with strategic prompt. Else: planning with get_delta.
        state_spec = self._scenario.get("variable_specs") if self._scenario else None
        # Language auto-detected from scenario (fa/en), not hardcoded
        lang = "en"
        if self._scenario:
            if self._scenario.get("language") in ("fa", "en"):
                lang = self._scenario["language"]
            else:
                text = (self._scenario.get("description") or "") + (self._scenario.get("name") or "") + (self._scenario.get("text") or "")
                lang = "fa" if detect_language(text) == "fa" else "en"
        summary_text = world_summarize(snapshot, state_spec=state_spec, lang=lang)
        if self.dry_run:
            base_agent_input = snapshot
        elif self._strategic_format:
            base_agent_input = {
                "strategic": True,
                "snapshot": snapshot,
                "scenario": self._scenario,
                "max_delta": self._max_delta,
                "obs_noise_scale": self._obs_noise_scale,
            }
        else:
            # LLM planning path: use snapshot with get_delta (injected per-agent below)
            base_agent_input = dict(snapshot)

        merged_numeric: dict[str, float] = {}
        merged_entity_updates: dict[str, dict[str, Any]] = {}
        merged_new_entities: dict[str, dict[str, Any]] = {}
        merged_relation_updates: list[dict[str, Any]] = []
        merged_meta_proposals: list[dict[str, Any]] = []
        merged_rationale: list[str] = []
        proposal_results: list[tuple[Proposal, Any, bool]] = []  # (proposal, delta, was_accepted)
        turn_log_entries: list[dict[str, Any]] = []  # reasoning, raw_json, validated_json, applied_delta per agent
        delta_raw_per_agent: dict[str, dict[str, float]] = {}  # agent -> var -> delta (for attribution)

        action_tradeoffs = self._scenario.get("action_tradeoffs") if isinstance(self._scenario.get("action_tradeoffs"), dict) else None
        variable_tradeoffs = self._scenario.get("variable_tradeoffs") if isinstance(self._scenario.get("variable_tradeoffs"), dict) else None
        next_turn = self.world.turn + 1
        action_provenance_this_step: list[dict[str, Any]] = []  # action trace (NOT appended to causal_links)
        self._turn_degraded = False
        guard = self._guard

        for idx, agent in enumerate(self.agents):
            # تاخیر کوچک بین درخواست‌های agent ها برای جلوگیری از rate limit
            if idx > 0 and not self.dry_run:
                time.sleep(0.5)  # 0.5 ثانیه تاخیر بین agent ها
            # Build agent_input: add get_delta for LLM planning path (non-dry-run, non-strategic)
            if (
                isinstance(base_agent_input, dict)
                and not self.dry_run
                and self.world_model_agent
            ):
                agent_input = dict(base_agent_input)
                def _make_get_delta(a: Any) -> Any:
                    def get_delta(action: str) -> Any:
                        p = Proposal(
                            agent_name=a.name,
                            action_type=action,
                            parameters={},
                            rationale="",
                            confidence=0.7,
                        )
                        return self.world_model_agent.normalize_proposal(p, snapshot, temperature=0.1)
                    return get_delta
                agent_input["get_delta"] = _make_get_delta(agent)
            else:
                agent_input = base_agent_input
            # LLM Integration: agent output (text reasoning + ### ACTION_JSON) is connected to the
            # engine's JSON-based simulation loop here: propose() → parse reasoning → extract/validate/sanitize → Delta/Proposal.
            agent_output = agent.propose(agent_input)
            reasoning = _parse_reasoning_from_output(agent_output)
            raw_json: dict[str, Any] | None = None
            validated_json: dict[str, Any] | None = None
            sanitized: dict[str, Any] | None = None
            delta = None
            proposal: Proposal | None = None
            for attempt in range(MAX_ACTION_JSON_ATTEMPTS):
                raw_json = guard.extract_json(agent_output)
                if raw_json.get("error"):
                    if attempt + 1 < MAX_ACTION_JSON_ATTEMPTS:
                        err = raw_json.get("error", "unknown")
                        # تاخیر قبل از retry برای جلوگیری از rate limit
                        if not self.dry_run:
                            time.sleep(0.3)
                        agent_output = agent.propose(
                            f"The JSON block you produced was invalid: {err} Please regenerate only the JSON block in the same ### ACTION_JSON format."
                        )
                        continue
                    break
                agent_allowed = getattr(agent, "allowed_actions", None)
                validated_json = guard.validate(
                    raw_json,
                    world_state=snapshot if self._strategic_format else None,
                    agent_allowed_actions=agent_allowed if agent_allowed else None,
                )
                if validated_json.get("valid") is False:
                    if attempt + 1 < MAX_ACTION_JSON_ATTEMPTS:
                        errs = "; ".join(validated_json.get("errors", []))
                        # تاخیر قبل از retry برای جلوگیری از rate limit
                        if not self.dry_run:
                            time.sleep(0.3)
                        agent_output = agent.propose(
                            f"The JSON block you produced was invalid: {errs} Please regenerate only the JSON block in the same ### ACTION_JSON format."
                        )
                        continue
                    break
                sanitized = guard.sanitize(validated_json, snapshot, agent_name=agent.name)
                numeric_updates = {d["variable"]: d["change"] for d in sanitized.get("deltas", [])}
                rationale_str = (sanitized.get("justification") or reasoning) if sanitized.get("justification") else reasoning
                confidence_val = sanitized.get("probability") if sanitized.get("probability") is not None else 0.7
                delta = Delta(
                    numeric_updates=numeric_updates,
                    entity_updates={},
                    new_entities={},
                    relation_updates=list(sanitized.get("relation_updates") or []),
                    meta_proposals=[],
                    rationale=rationale_str,
                    effects_duration=None,
                    mitigation=None,
                    action_type=sanitized.get("action"),
                    primary_variable=sanitized.get("primary_variable") or None,
                )
                proposal = Proposal(
                    agent_name=sanitized.get("actor", agent.name),
                    action_type=sanitized.get("action", ""),
                    parameters={},
                    rationale=rationale_str,
                    confidence=float(confidence_val) if isinstance(confidence_val, (int, float)) else 0.7,
                )
                break

            log_entry: dict[str, Any] = {
                "reasoning": reasoning,
                "raw_json": raw_json,
                "validated_json": validated_json,
                "applied_delta": delta.to_dict() if delta and hasattr(delta, "to_dict") else None,
            }
            if self._strategic_format and sanitized:
                log_entry["justification"] = sanitized.get("justification") or ""
                log_entry["causal_chain"] = sanitized.get("causal_chain") or ""
            turn_log_entries.append(log_entry)

            # CRITICAL: If delta is None (extraction/validation failed after retries), mark turn as degraded and skip
            agent_name = proposal.agent_name if proposal else agent.name
            proposal_action_type = proposal.action_type if proposal else ""
            if delta is None:
                self._turn_degraded = True
                self._rule_based_fallback_count += 1
                import logging
                logging.getLogger(__name__).critical(
                    f"CRITICAL_WARNING: Turn {next_turn} degraded - NULL action returned for proposal by {agent_name}. "
                    f"Rule-based fallback count: {self._rule_based_fallback_count}"
                )
                if agent_name:
                    if agent_name not in self._agent_action_history:
                        self._agent_action_history[agent_name] = []
                    self._agent_action_history[agent_name].append(proposal_action_type or "")
                    self._agent_action_history[agent_name] = self._agent_action_history[agent_name][-2:]
                proposal_results.append((proposal or Proposal(agent_name=agent.name, action_type="", parameters={}, rationale="", confidence=0.0), None, False))
                continue
            _delay = getattr(delta, "delay_turns", None)
            if _delay is not None and _delay > 0:
                try:
                    from world.delayed_events import DelayedEvent
                    self.world.delayed_events.append(DelayedEvent(
                        trigger_turn=self.world.turn + delta.delay_turns,
                        delta=delta,
                        source_action=proposal_action_type,
                        probability=getattr(delta, "probability", None),
                    ))
                except Exception:
                    pass
                proposal_results.append((proposal, delta, False))  # Delayed events not "accepted" yet
                continue
            # Governance validates and auto-repairs deltas (never rejects completely)
            ok, warnings, modified_delta = self.governance.validate_delta(delta, self.world)
            was_accepted = ok  # Should always be True now
            was_repaired = modified_delta is not None and modified_delta != delta
            original_delta_dict = delta.to_dict() if hasattr(delta, "to_dict") else {}
            injected_cost = {}
            if was_repaired and modified_delta:
                original_numeric = delta.numeric_updates or {}
                repaired_numeric = modified_delta.numeric_updates or {}
                injected_cost = {k: v for k, v in repaired_numeric.items() if k not in original_numeric}
            proposal_results.append((proposal, modified_delta if modified_delta else delta, was_accepted))
            to_apply = modified_delta if modified_delta is not None else delta
            numeric_updates = to_apply.numeric_updates or {}
            # Prefer delta from action_definitions when available (deterministic); else use sanitized
            raw_delta = get_delta_vector(self._action_definitions, proposal_action_type or "")
            if not raw_delta and numeric_updates:
                raw_delta = dict(numeric_updates)
            if raw_delta:
                delta_raw_per_agent[agent_name or ""] = raw_delta
                # Use action_definitions delta for merge when available (hardened path)
                for k, v in raw_delta.items():
                    if isinstance(v, (int, float)):
                        merged_numeric[k] = merged_numeric.get(k, 0) + v
                        action_provenance_this_step.append({
                            "from_action": proposal_action_type or "unknown",
                            "agent": agent_name or "unknown",
                            "variable": k,
                            "delta": float(v),
                            "turn": next_turn,
                            "repaired": was_repaired,
                        })
            elif numeric_updates:
                for k, v in numeric_updates.items():
                    merged_numeric[k] = merged_numeric.get(k, 0) + v
                    if isinstance(v, (int, float)):
                        action_provenance_this_step.append({
                            "from_action": proposal_action_type or "unknown",
                            "agent": agent_name or "unknown",
                            "variable": k,
                            "delta": float(v),
                            "turn": next_turn,
                            "repaired": was_repaired,
                        })
            merged_entity_updates.update(to_apply.entity_updates or {})
            merged_new_entities.update(to_apply.new_entities or {})
            merged_relation_updates.extend(to_apply.relation_updates or [])
            merged_meta_proposals.extend(to_apply.meta_proposals or [])
            if to_apply.rationale:
                merged_rationale.append(to_apply.rationale)
            # Update turn log with applied_delta (may have been repaired)
            if turn_log_entries:
                turn_log_entries[-1]["applied_delta"] = to_apply.to_dict() if hasattr(to_apply, "to_dict") else None

        # Delta lifecycle: delta_after_merge, apply constraints -> delta_applied, attribution
        delta_after_merge = merge_delta_raw(delta_raw_per_agent) if delta_raw_per_agent else dict(merged_numeric)
        if not delta_after_merge and merged_numeric:
            delta_after_merge = dict(merged_numeric)

        # Ensure minimum delta guarantee: at least one variable must change
        merged_numeric = self._ensure_minimum_delta(merged_numeric)

        # Soft constraints: rate_limit, change_budget, diminishing returns, hard clip -> delta_applied
        delta_applied = merged_numeric
        if self._variable_specs or self._change_budget is not None:
            delta_applied = apply_all_constraints(
                dict(self.world.variables),
                self._variable_specs,
                merged_numeric,
                change_budget=self._change_budget,
            )

        # Attribution: self_effect_per_agent
        self_effect_per_agent = compute_self_effect_per_agent(
            delta_raw_per_agent, delta_after_merge, delta_applied
        ) if delta_raw_per_agent else {}

        # If we injected drift, add to action provenance (NOT to causal_links)
        if merged_numeric and not action_provenance_this_step:
            for k, v in merged_numeric.items():
                if isinstance(v, (int, float)) and abs(v) > 1e-6:
                    action_provenance_this_step.append({
                        "from_action": "systemic_drift",
                        "agent": "system",
                        "variable": k,
                        "delta": float(v),
                        "turn": next_turn,
                        "repaired": False,
                    })
                    break

        # Store previous state before applying delta (for memory updates)
        previous_state = self.world.snapshot()

        combined_delta = Delta(
            numeric_updates=delta_applied,
            entity_updates=merged_entity_updates,
            new_entities=merged_new_entities,
            relation_updates=merged_relation_updates,
            meta_proposals=merged_meta_proposals,
            rationale=" ".join(merged_rationale),
            effects_duration=None,
            mitigation=None,
        )

        # STRICT GRAPH PURITY: Never append action provenance to causal_links.
        # causal_links remain structural-only (from, to, weight).

        # Extract action_type from first proposal for apply_delta (or use combined action type)
        combined_action_type = None
        if proposal_results:
            first_proposal = proposal_results[0][0]
            combined_action_type = getattr(first_proposal, "action_type", None) or (
                first_proposal.to_dict() if hasattr(first_proposal, "to_dict") else {}
            ).get("action_type")

        # Apply delta and get structured outcome (pass variable_specs for propagation hardening)
        outcome = self.world.apply_delta(
            combined_delta,
            action_type=combined_action_type,
            variable_specs=self._variable_specs,
        )
        # Handle both old format (list) and new format (dict)
        if isinstance(outcome, dict):
            variable_changes = outcome.get("variable_changes", [])
        else:
            variable_changes = outcome
        self.world.turn += 1
        
        # Compute and track world entropy
        current_entropy = self._compute_world_entropy()
        self._entropy_history.append(current_entropy)
        self._entropy_history = self._entropy_history[-2:]  # Keep last 2 turns
        
        # Check for static world (entropy == 0 for 2 consecutive turns)
        if len(self._entropy_history) >= 2 and all(e == 0.0 for e in self._entropy_history):
            # Trigger systemic instability event
            import logging
            logging.getLogger(__name__).warning(
                f"Systemic instability event triggered: world entropy == 0 for 2 consecutive turns "
                f"(turns {self.world.turn - 1} and {self.world.turn})"
            )
            # Inject larger drift to break static state
            if self.world.variables:
                variables = list(self.world.variables.keys())
                if variables:
                    var = random.choice(variables)
                    # Larger drift for instability event
                    instability_drift = random.gauss(0, 5.0)  # Larger magnitude
                    if var in self.world.variables:
                        self.world.variables[var] = self.world.variables[var] + instability_drift
                        # Add to merged_numeric for next turn's tracking
                        merged_numeric[var] = merged_numeric.get(var, 0) + instability_drift
        
        events_triggered: list[dict[str, Any]] = []
        if hasattr(self.world, "process_delayed_events"):
            events_triggered = self.world.process_delayed_events()
        rule_activations: list[dict[str, Any]] = []
        if self._scenario_rules:
            snap = self.world.snapshot()
            rule_activations = run_rules(snap, self.world, self._scenario_rules)
        # Update agent action history for oscillation detection (only for successful actions)
        for i, (proposal, delta, was_accepted) in enumerate(proposal_results):
            if was_accepted and delta is not None:
                agent_name = getattr(proposal, "agent_name", None) or (proposal.to_dict() if hasattr(proposal, "to_dict") else {}).get("agent_name", "")
                action_type = getattr(proposal, "action_type", None) or (proposal.to_dict() if hasattr(proposal, "to_dict") else {}).get("action_type")
                if agent_name:
                    if agent_name not in self._agent_action_history:
                        self._agent_action_history[agent_name] = []
                    self._agent_action_history[agent_name].append(action_type or "")
                    self._agent_action_history[agent_name] = self._agent_action_history[agent_name][-2:]
                    # Check for oscillation pattern
                    if len(self._agent_action_history[agent_name]) >= 2:
                        self._apply_oscillation_penalty(agent_name, action_type or "")
        
        # Governance strictness escalation: if rule-based fallback occurred >1 time
        if self._rule_based_fallback_count > 1:
            self.governance.strictness_level += 1
            import logging
            logging.getLogger(__name__).warning(
                f"Governance strictness escalated to {self.governance.strictness_level} due to {self._rule_based_fallback_count} rule-based fallbacks"
            )
        
        # Build action_trace: [{agent, action_id, strategy_class}, ...]
        strategy_classes = self._scenario.get("strategy_classes") or {}
        action_trace: list[dict[str, Any]] = []
        for p, _, _ in proposal_results:
            aname = getattr(p, "agent_name", None) or (p.to_dict() if hasattr(p, "to_dict") else {}).get("agent_name", "")
            aid = getattr(p, "action_type", None) or (p.to_dict() if hasattr(p, "to_dict") else {}).get("action_type", "")
            action_trace.append({
                "agent": aname,
                "action_id": aid,
                "strategy_class": strategy_classes.get(aid, "general"),
            })

        # Planned/predicted Deltas from depth-2 planning (for strategic analysis)
        predicted_deltas: list[dict[str, Any]] = []
        agents_by_name = {getattr(a, "name", None): a for a in self.agents if getattr(a, "name", None)}
        for p, _, _ in proposal_results:
            aname = getattr(p, "agent_name", None) or (p.to_dict() if hasattr(p, "to_dict") else {}).get("agent_name", "")
            aid = getattr(p, "action_type", None) or (p.to_dict() if hasattr(p, "to_dict") else {}).get("action_type", "")
            agent = agents_by_name.get(aname)
            planned = getattr(agent, "_last_planning_delta", None) if agent else None
            if planned is not None and isinstance(planned, dict):
                predicted_deltas.append({"agent": aname, "action_type": aid, "delta": planned})
            elif planned is not None and hasattr(planned, "to_dict"):
                predicted_deltas.append({"agent": aname, "action_type": aid, "delta": planned.to_dict()})

        # Build provenance with TurnRecord (delta lifecycle, attribution, action trace)
        proposals_for_provenance = [p for p, _, _ in proposal_results]
        provenance_entry = {
            "turn": self.world.turn,
            "actions": [p.to_dict() for p in proposals_for_provenance],
            "proposals": [p.to_dict() for p in proposals_for_provenance],
            "turn_log": turn_log_entries,
            "delta": combined_delta.to_dict(),
            "variable_changes": variable_changes,
            "causal_edges": action_provenance_this_step,
            "events_triggered": events_triggered,
            "environment_proposed": env_events_this_turn,
            "rule_activations": rule_activations,
            "instability_mode": instability_mode,
            "turn_degraded": self._turn_degraded,
            "world_entropy": current_entropy,
            "entropy_history": list(self._entropy_history),
            "derived": {"instability_mode": instability_mode, "system_stability": stability, "dissatisfaction": dissatisfaction},
            "predicted_deltas": predicted_deltas,
            "turn_record": {
                "turn": self.world.turn,
                "pre_state": previous_state,
                "option_sets": {},
                "chosen_actions": action_trace,
                "delta_raw_per_agent": delta_raw_per_agent,
                "delta_after_merge": delta_after_merge,
                "delta_applied": delta_applied,
                "self_effect_per_agent": self_effect_per_agent,
                "propagation_trace": outcome.get("propagation_trace", []) if isinstance(outcome, dict) else [],
                "events_fired": events_triggered,
                "rules_fired": rule_activations,
                "threshold_crossings": [],
                "post_state": None,
            },
        }
        if isinstance(outcome, dict):
            provenance_entry["outcome"] = {
                "primary_effect": outcome.get("primary_effect"),
                "secondary_effects": outcome.get("secondary_effects", []),
                "noise_component": outcome.get("noise_component", {}),
                "propagation_trace": outcome.get("propagation_trace", []),
            }
        self._provenance.append(provenance_entry)

        try:
            from trace_log.action_trace import append_action_trace_entry
            for p, _, _ in proposal_results:
                aname = getattr(p, "agent_name", None) or (p.to_dict() if hasattr(p, "to_dict") else {}).get("agent_name", "")
                aid = getattr(p, "action_type", None) or (p.to_dict() if hasattr(p, "to_dict") else {}).get("action_type", "")
                raw = delta_raw_per_agent.get(aname, {})
                append_action_trace_entry(
                    self._action_trace,
                    self.world.turn,
                    aname,
                    {"op": aid or "unknown", "args": {}},
                    raw,
                    delta_applied,
                )
        except Exception:
            pass

        for mp in combined_delta.meta_proposals or []:
            if self.governance.approve_meta_proposal(mp, [True]):
                name = mp.get("name") or mp.get("attr_name")
                entity_type = mp.get("entity_type", "global")
                if name:
                    self.ontology_manager.register_attribute(entity_type, name, mp.get("spec", {}))

        snap_after = self.world.snapshot()
        if self._provenance and self._provenance[-1].get("turn_record") is not None:
            self._provenance[-1]["turn_record"]["post_state"] = snap_after

        # Extract structured outcome components
        primary_effect = outcome.get("primary_effect") if isinstance(outcome, dict) else None
        primary_variable = primary_effect.get("var") if primary_effect else None
        
        # Build actual_delta from variable_changes
        actual_delta: dict[str, float] = {}
        if isinstance(outcome, dict):
            # Extract from structured outcome
            if primary_effect:
                actual_delta[primary_effect["var"]] = primary_effect["delta"]
            for sec_effect in outcome.get("secondary_effects", []):
                var = sec_effect.get("var")
                delta_val = sec_effect.get("delta", 0.0)
                if var:
                    actual_delta[var] = actual_delta.get(var, 0.0) + delta_val
            # Add noise component
            for var, noise_val in outcome.get("noise_component", {}).items():
                actual_delta[var] = actual_delta.get(var, 0.0) + noise_val
        else:
            # Fallback: extract from variable_changes list
            for change in variable_changes:
                var = change.get("var")
                delta_val = change.get("delta", 0.0)
                if var and isinstance(delta_val, (int, float)):
                    actual_delta[var] = actual_delta.get(var, 0.0) + float(delta_val)
        
        # LLM Integration: memory schema is updated per turn for each agent (schemas/memory_schema.py).
        # add_event stores self_effect (agent-attributed) and global_world_delta for no false causation.
        global_world_delta = dict(actual_delta) if actual_delta else dict(delta_applied)
        for i, agent in enumerate(self.agents):
            if hasattr(agent, "memory") and hasattr(agent.memory, "add_event"):
                aname = getattr(agent, "name", "") or (proposal_results[i][0].agent_name if i < len(proposal_results) else "")
                self_eff = self_effect_per_agent.get(aname) if aname else None
                agent.memory.add_event(
                    self.world.turn,
                    proposal_results[i][0] if i < len(proposal_results) else proposal_results[0][0],
                    combined_delta,
                    combined_delta,
                    self_effect=self_eff,
                    global_world_delta=global_world_delta,
                )
            
            # Extract expected_delta from this agent's proposal
            expected_delta: dict[str, float] | None = None
            agent_primary_variable = primary_variable
            if i < len(proposal_results):
                proposal, delta, was_accepted = proposal_results[i]
                if delta:
                    if hasattr(delta, "numeric_updates"):
                        expected_delta = delta.numeric_updates or {}
                    elif isinstance(delta, dict):
                        expected_delta = delta.get("numeric_updates", {})
                    
                    # Extract action_type for this agent
                    agent_action_type = getattr(proposal, "action_type", None) or (
                        proposal.to_dict() if hasattr(proposal, "to_dict") else {}
                    ).get("action_type")
                    
                    # Identify primary variable for this agent's action
                    if agent_action_type and expected_delta:
                        # Create a temporary Delta for identification
                        temp_delta = Delta(numeric_updates=expected_delta, action_type=agent_action_type)
                        if hasattr(delta, "primary_variable") and delta.primary_variable:
                            agent_primary_variable = delta.primary_variable
                        else:
                            # Use heuristic: largest magnitude variable or extract from action_type
                            if agent_action_type.startswith("increase_") or agent_action_type.startswith("decrease_"):
                                var_name = agent_action_type.replace("increase_", "").replace("decrease_", "")
                                if var_name in expected_delta:
                                    agent_primary_variable = var_name
                                else:
                                    agent_primary_variable = max(expected_delta.items(), key=lambda x: abs(x[1]))[0] if expected_delta else None
                            else:
                                agent_primary_variable = max(expected_delta.items(), key=lambda x: abs(x[1]))[0] if expected_delta else None
            
            # Update beliefs with expected vs actual delta for primary variable
            if hasattr(agent, "memory") and hasattr(agent.memory, "update_beliefs"):
                agent.memory.update_beliefs(
                    snap_after,
                    expected_delta=expected_delta,
                    actual_delta=actual_delta,
                    primary_variable=agent_primary_variable,
                )
            
            # Update long-term memory for each agent
            if hasattr(agent, "update_long_term_memory") and i < len(proposal_results):
                proposal, delta, was_accepted = proposal_results[i]
                agent.update_long_term_memory(
                    turn=self.world.turn,
                    proposal=proposal,
                    delta=delta,
                    was_accepted=was_accepted,
                    previous_state=previous_state,
                    current_state=snap_after,
                )
        
        # Also call reflect for backward compatibility (but update_beliefs already called above)
        for agent in self.agents:
            agent.reflect(self._provenance[-1:], snap_after)
        # Anti-repetition: update last 2 actions per agent
        for i, agent in enumerate(self.agents):
            if i < len(proposal_results):
                p = proposal_results[i][0]
                action_type = getattr(p, "action_type", None) or (p.to_dict() if hasattr(p, "to_dict") else {}).get("action_type")
                if action_type and isinstance(action_type, str):
                    agent.last_actions = (agent.last_actions + [action_type])[-2:]

        # [RL] Update per-agent RL weight from observed reward.
        try:
            from config.settings import MC_RL_BETA
            for i, agent in enumerate(self.agents):
                if i >= len(proposal_results):
                    continue
                proposal, delta, was_accepted = proposal_results[i]
                action_type = getattr(proposal, "action_type", None) or (proposal.to_dict() if hasattr(proposal, "to_dict") else {}).get("action_type")
                if not action_type or not hasattr(agent, "update_rl_weight"):
                    continue
                state_delta = dict(actual_delta) if actual_delta else {}
                observed_reward = agent._calculate_valence(proposal, delta, was_accepted, state_delta, agent.objectives)
                agent.update_rl_weight(action_type, observed_reward, baseline=agent._rl_baseline, beta=MC_RL_BETA)
        except (ImportError, AttributeError):
            pass

    def run(
        self,
        steps: int = 5,
        *,
        snapshot_out_path: str | None = None,
        return_turns: bool = False,
        return_provenance: bool = False,
        silent: bool = False,
        delay_between_rounds: float = 2.0,
    ) -> dict[str, Any]:
        """Run steps; print snapshot each turn (unless silent); save final snapshot to snapshot_out_path or self.snapshot_path.
        If return_turns is True, returns dict with keys 'final' and 'turns'; if return_provenance is True, adds 'provenance'.
        Otherwise returns final_snapshot only.
        
        Args:
            delay_between_rounds: Delay in seconds between simulation rounds to avoid rate limits (default: 2.0).
        """
        out_path = snapshot_out_path or self.snapshot_path
        turns: list[dict[str, Any]] = []
        for i in range(steps):
            if not silent:
                print(f"\n{'='*60}")
                print(f"🔄 شروع راند {i+1} از {steps}...")
                print(f"{'='*60}\n")
            
            self.step()
            snap = self.world.snapshot()
            
            if return_turns:
                snap_copy = dict(snap)
                if self.agents and hasattr(self.agents[0], "state_to_dict"):
                    snap_copy["agents_state"] = {a.name: a.state_to_dict() for a in self.agents}
                turns.append(snap_copy)
            
            if not silent:
                print(f"\n✅ راند {self.world.turn} تکمیل شد")
                print(f"--- Turn {self.world.turn} ---")
                print(json.dumps(snap, indent=2)[:1500])
                print("...")
                
                # نمایش خلاصه تغییرات
                variables = snap.get("variables") or snap.get("global_state") or {}
                if variables:
                    print(f"\n📊 وضعیت فعلی:")
                    for key, value in list(variables.items())[:5]:  # نمایش 5 متغیر اول
                        if isinstance(value, (int, float)):
                            print(f"  • {key}: {value:.2f}")
                
                # تاخیر بین راندها (به جز راند آخر)
                if i < steps - 1:
                    print(f"\n⏳ منتظر {delay_between_rounds} ثانیه قبل از راند بعدی...")
                    time.sleep(delay_between_rounds)
        
        final = self.world.snapshot()
        if self.agents and hasattr(self.agents[0], "state_to_dict"):
            final["agents_state"] = {a.name: a.state_to_dict() for a in self.agents}
        if hasattr(self.governance, "snapshot_state"):
            final["governance_state"] = self.governance.snapshot_state()
        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(_make_json_safe(final), f, indent=2)
            if not silent:
                print(f"Snapshot saved to {out_path}")
        if return_turns or return_provenance:
            result: dict[str, Any] = {"final": final}
            if return_turns:
                result["turns"] = turns
            if return_provenance:
                result["provenance"] = list(self._provenance)
                result["action_trace"] = list(self._action_trace)
            return result
        return final

    def run_streaming(
        self,
        steps: int = 5,
        *,
        snapshot_out_path: str | None = None,
        delay_between_rounds: float = 2.0,
    ):
        """Generator that yields each turn as it completes. Yields dicts: {type, turn_index, turn, ...}."""
        out_path = snapshot_out_path or self.snapshot_path
        for i in range(steps):
            self.step()
            snap = self.world.snapshot()
            snap_copy = dict(snap)
            if self.agents and hasattr(self.agents[0], "state_to_dict"):
                snap_copy["agents_state"] = {a.name: a.state_to_dict() for a in self.agents}
            provenance_entry = self._provenance[-1] if self._provenance else None
            yield {"type": "turn", "turn_index": i + 1, "steps_total": steps, "turn": snap_copy, "provenance_entry": provenance_entry}
            if i < steps - 1:
                time.sleep(delay_between_rounds)
        final = self.world.snapshot()
        if self.agents and hasattr(self.agents[0], "state_to_dict"):
            final["agents_state"] = {a.name: a.state_to_dict() for a in self.agents}
        if hasattr(self.governance, "snapshot_state"):
            final["governance_state"] = self.governance.snapshot_state()
        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(_make_json_safe(final), f, indent=2)
        yield {"type": "done", "final": final, "provenance": list(self._provenance)}
