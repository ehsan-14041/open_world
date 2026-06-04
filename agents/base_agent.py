"""
BaseAgent: memory, goals, utility, planning flow.

Class diagram:
  BaseAgent
    - memory: AgentMemory
    - long_term_goals: list[str]
    - short_term_goals: list[str]
    - objectives: dict[str, float]
    - propose(snapshot) -> Proposal  [observe -> update_beliefs -> evaluate_goals -> plan -> select]
    - reflect(history, snapshot) -> None
  RoleAgent(BaseAgent): + role, llm_client, allowed_actions
"""

from __future__ import annotations

import logging
from typing import Any

from schemas.proposal_schema import Proposal

from agents.memory import AgentMemory
from agents.planner import plan_depth2, plan_depth2_with_callback, delta_from_rule_based
from agents.utility import evaluate_short_term_goals, goals_from_objectives, utility_function, DEFAULT_NORM_RANGES
from core.legacy_semantics import legacy_strategy_class_from_action_type, legacy_fallback_action_for_variables

# Default magnitude for variable-driven actions (increase_X / decrease_X)
DEFAULT_VARIABLE_ACTION_MAGNITUDE = 5.0

# Rule-based deltas for planning. Domain-agnostic: only variable-driven actions (increase_X, decrease_X) are supported.
# Legacy domain-specific actions removed; use adjust_variable or variable-driven actions instead.
RULE_BASED_DELTAS: dict[str, dict[str, float]] = {}


def rule_based_deltas_for_snapshot(snapshot: dict[str, Any], magnitude: float = DEFAULT_VARIABLE_ACTION_MAGNITUDE) -> dict[str, dict[str, float]]:
    """Build variable-driven deltas from snapshot variables (increase_X, decrease_X) and merge with action_tradeoffs and legacy RULE_BASED_DELTAS."""
    out = dict(RULE_BASED_DELTAS)
    variables = snapshot.get("variables") or snapshot.get("global_state") or {}
    if isinstance(variables, dict):
        for var in variables.keys():
            if var and isinstance(var, str):
                out[f"increase_{var}"] = {var: magnitude}
                out[f"decrease_{var}"] = {var: -magnitude}
    # Merge scenario action_tradeoffs (enables demo_scenario, gulf_standoff, etc.)
    action_tradeoffs = snapshot.get("action_tradeoffs")
    if isinstance(action_tradeoffs, dict):
        for action_name, tradeoff in action_tradeoffs.items():
            if isinstance(tradeoff, dict):
                out[action_name] = {k: float(v) for k, v in tradeoff.items() if isinstance(v, (int, float))}
    return out


def prune_candidate_actions(
    actions: list[str],
    snapshot: dict[str, Any],
    max_actions: int = 5,
    *,
    get_delta: Any = None,
    rule_based_deltas: dict[str, dict[str, float]] | None = None,
    objectives: dict[str, float] | None = None,
    beliefs: dict[str, Any] | None = None,
) -> list[str]:
    """
    Lightweight pruning before heavy evaluation: score each action with direct delta only
    (no propagation, no noise), return top max_actions. Deterministic; no LLM calls.
    Fallback to original list if pruning fails or would remove all actions.
    Applies ONLY numeric_updates directly to snapshot copy; no physics_core/propagation.

    Safety: Does not mutate input `actions` or `snapshot`; always returns a new list.
    Always returns at least one action (fallback to list(actions) if pruning would yield empty).
    Complexity: O(N log N) — single pass over actions, one sort.
    """
    if not actions or max_actions <= 0:
        return list(actions)
    if len(actions) <= max_actions:
        return list(actions)
    try:
        from world.world_state import clone_world_state
    except ImportError:
        return list(actions)

    try:
        objectives = objectives or {}
        beliefs = beliefs or {}
        scored: list[tuple[str, float]] = []
        for action_type in actions:
            try:
                clone = clone_world_state(snapshot)
                if get_delta and callable(get_delta):
                    d = get_delta(action_type)
                    if d is None:
                        scored.append((action_type, float("-inf")))
                        continue
                    delta = d.to_dict() if hasattr(d, "to_dict") else d
                else:
                    delta = {"numeric_updates": (rule_based_deltas or {}).get(action_type, {})}
                numeric_updates = delta.get("numeric_updates") if isinstance(delta, dict) else {}
                if not isinstance(numeric_updates, dict):
                    numeric_updates = {}
                # Apply ONLY numeric_updates directly (no propagation, no physics_core)
                vars_dict = clone.get("variables") or clone.get("global_state") or {}
                if isinstance(vars_dict, dict):
                    vars_dict = dict(vars_dict)
                else:
                    vars_dict = {}
                for var, delta_val in numeric_updates.items():
                    if isinstance(delta_val, (int, float)):
                        vars_dict[var] = vars_dict.get(var, 0) + float(delta_val)
                clone["variables"] = vars_dict
                clone["global_state"] = vars_dict
                score = utility_function(clone, beliefs, objectives)
                scored.append((action_type, score))
            except Exception:
                scored.append((action_type, float("-inf")))
        scored.sort(key=lambda x: x[1], reverse=True)
        top = [a for a, _ in scored[:max_actions]]
        if not top:
            return list(actions)
        return top
    except Exception:
        logging.getLogger(__name__).warning(
            "prune_candidate_actions: utility_function or pruning failed, falling back to original action list",
            exc_info=True,
        )
        return list(actions)


def _belief_snapshot_from_world(world_snapshot: dict[str, Any], belief_variables: dict[str, float]) -> dict[str, Any]:
    """Build a snapshot-shaped dict with variables/global_state replaced by agent beliefs (for decision-making)."""
    out = dict(world_snapshot)
    gs = dict(belief_variables)
    out["variables"] = gs
    out["global_state"] = gs
    return out


class BaseAgent:
    """Base agent with memory, belief state (variables, confidence), and goal-driven propose flow. Decisions use beliefs, not real world."""

    def __init__(
        self,
        name: str,
        objectives: dict[str, float],
        *,
        long_term_goals: list[str] | None = None,
        memory: AgentMemory | None = None,
        strategy_classes: dict[str, str] | None = None,
        personality_modifiers: dict[str, float] | None = None,
    ) -> None:
        self.name = name
        self.objectives = dict(objectives or {})
        self.long_term_goals = list(long_term_goals or goals_from_objectives(self.objectives))
        self.short_term_goals: list[str] = []
        self.memory = memory or AgentMemory()
        self.long_term_memory: list[dict[str, Any]] = []
        self.last_actions: list[str] = []
        self.strategy_classes = dict(strategy_classes or {})
        self.strategy_class_weights: dict[str, float] = {}
        self.personality_modifiers = dict(personality_modifiers or {})
        self._last_planning_delta: dict[str, Any] | None = None
        # [RL] Lightweight RL weight table (action_type -> weight) and baseline for update.
        self._rl_weights: dict[str, float] = {}
        self._rl_baseline: float = 0.0
        # [Belief] Optional structured belief state (when ENABLE_BELIEF_LAYER).
        self._belief_state: Any = None

    def get_rl_weight(self, action_type: str) -> float:
        """Return RL weight for action_type (default 0.0 for unseen)."""
        return self._rl_weights.get(action_type, 0.0)

    def update_rl_weight(
        self,
        action_type: str,
        observed_reward: float,
        baseline: float | None = None,
        *,
        beta: float = 0.1,
        alpha_baseline: float = 0.05,
    ) -> None:
        """Update RL weight: weight += beta * (observed_reward - baseline); then update baseline EMA. RL table capped to RL_TABLE_MAX_ENTRIES."""
        try:
            from config.settings import RL_TABLE_MAX_ENTRIES
            max_entries = RL_TABLE_MAX_ENTRIES
        except ImportError:
            max_entries = 50
        b = baseline if baseline is not None else self._rl_baseline
        if action_type not in self._rl_weights and len(self._rl_weights) >= max_entries:
            # Evict entry with lowest absolute weight (or oldest if tie)
            by_abs = sorted(self._rl_weights.items(), key=lambda x: (abs(x[1]), list(self._rl_weights.keys()).index(x[0])))
            if by_abs:
                self._rl_weights.pop(by_abs[0][0], None)
        self._rl_weights[action_type] = self._rl_weights.get(action_type, 0.0) + beta * (observed_reward - b)
        self._rl_baseline = (1 - alpha_baseline) * self._rl_baseline + alpha_baseline * observed_reward

    @property
    def beliefs(self) -> dict[str, Any]:
        """Belief state: variables (agent view of world) and confidence per variable."""
        return self.memory.beliefs

    def _get_strategy_class(self, action_type: str) -> str:
        """Map action_type to strategy class from scenario or legacy inference from name."""
        if not action_type or not isinstance(action_type, str):
            return "default"
        if action_type in self.strategy_classes:
            return self.strategy_classes[action_type]
        return legacy_strategy_class_from_action_type(action_type)

    def propose(self, world_snapshot: dict[str, Any]) -> Proposal:
        """Observe real world -> update_beliefs; then evaluate_goals, plan, select using belief snapshot (not real state)."""
        self.memory.update_beliefs(world_snapshot)
        belief_vars = self.memory.beliefs.get("variables") or {}
        belief_snapshot = _belief_snapshot_from_world(world_snapshot, belief_vars) if belief_vars else world_snapshot
        self.short_term_goals = evaluate_short_term_goals(self.long_term_goals, belief_snapshot)
        candidates = self.generate_candidate_actions(belief_snapshot)
        if not candidates:
            # Fallback: use legacy_fallback_action_for_variables (increase_first_var or adjust_variable)
            variables = belief_snapshot.get("variables") or belief_snapshot.get("global_state") or {}
            fallback_action = legacy_fallback_action_for_variables(variables if isinstance(variables, dict) else {})
            return Proposal(
                agent_name=self.name,
                action_type=fallback_action,
                parameters={},
                rationale="No candidates available, using fallback",
                confidence=0.1,
            )
        get_delta = belief_snapshot.get("get_delta")
        if get_delta is not None and not callable(get_delta):
            get_delta = None
        rule_deltas = rule_based_deltas_for_snapshot(belief_snapshot) if get_delta is None else None

        # Prune candidates before heavy evaluation (top K by direct-delta utility).
        try:
            from config.settings import MAX_ACTIONS_PRUNE
            max_prune = MAX_ACTIONS_PRUNE
        except ImportError:
            max_prune = 5
        candidates = prune_candidate_actions(
            candidates,
            belief_snapshot,
            max_prune,
            get_delta=get_delta,
            rule_based_deltas=rule_deltas,
            objectives=self.objectives,
            beliefs=self.memory.semantic_memory,
        )

        # [MC + RL] Evaluate candidates and select probabilistically (planner score + MC value + RL weight + optional belief, softmax).
        try:
            from config.settings import MC_RL_ENABLED, MC_N_SIMS, MC_RL_TEMPERATURE, ENABLE_BELIEF_LAYER, BELIEF_WEIGHT
            from agents.action_evaluation import run_mc_evaluation, get_planner_scores, softmax_select
            from core.synthesizer import ensure_action_diversity
            if MC_RL_ENABLED:
                try:
                    from core.prediction_calibration import get_calibration_weight
                    calibration_weight = get_calibration_weight(self.name)
                except ImportError:
                    calibration_weight = 1.0
                llm_scores = get_planner_scores(
                    belief_snapshot, candidates, get_delta, rule_deltas,
                    self.objectives, self.memory.semantic_memory,
                    calibration_weight=calibration_weight,
                )
                mc_values = run_mc_evaluation(
                    belief_snapshot, candidates, get_delta, rule_deltas,
                    self.objectives, self.memory.semantic_memory,
                    n_sims=MC_N_SIMS,
                )
                rl_weights = {a: self.get_rl_weight(a) for a in candidates}
                belief_scores = None
                belief_weight = 0.0
                if ENABLE_BELIEF_LAYER and BELIEF_WEIGHT > 0:
                    from agents.belief_model import belief_state_from_memory_beliefs, belief_alignment
                    bs = self._belief_state
                    if bs is None:
                        bs = belief_state_from_memory_beliefs(self.memory.beliefs)
                        self._belief_state = bs
                    belief_scores = {
                        a: belief_alignment(a, bs, rule_based_deltas=rule_deltas, get_delta=get_delta)
                        for a in candidates
                    }
                    belief_weight = BELIEF_WEIGHT
                diverse_candidates = ensure_action_diversity(candidates, llm_scores, min_size=2)
                best_action = softmax_select(
                    diverse_candidates, llm_scores, mc_values, rl_weights,
                    temperature=MC_RL_TEMPERATURE,
                    belief_scores=belief_scores,
                    belief_weight=belief_weight,
                    calibration_weight=calibration_weight,
                )
            else:
                raise ImportError("MC_RL disabled")
        except (ImportError, AttributeError):
            # Fallback: original planner argmax (no MC/RL).
            causal_links = belief_snapshot.get("causal_links")
            variable_specs = belief_snapshot.get("variable_specs")
            if get_delta is not None:
                best_action = plan_depth2_with_callback(
                    belief_snapshot,
                    candidates,
                    self.objectives,
                    get_delta,
                    beliefs=self.memory.semantic_memory,
                    causal_links=causal_links,
                    variable_specs=variable_specs,
                )
            else:
                derived = (belief_snapshot.get("derived") or {}) if isinstance(belief_snapshot.get("derived"), dict) else {}
                instability_mode = bool(derived.get("instability_mode", False))
                best_action = plan_depth2(
                    belief_snapshot,
                    candidates,
                    self.objectives,
                    rule_deltas,
                    beliefs=self.memory.semantic_memory,
                    long_term_memory=self.long_term_memory,
                    current_turn=world_snapshot.get("turn", 0),
                    last_actions=self.last_actions,
                    strategy_class_weights=self.strategy_class_weights,
                    get_strategy_class=self._get_strategy_class,
                    instability_mode=instability_mode,
                    causal_links=causal_links,
                    variable_specs=variable_specs,
                )

        if get_delta is not None:
            delta_result = get_delta(best_action)
            self._last_planning_delta = (
                delta_result.to_dict() if hasattr(delta_result, "to_dict") else (delta_result if isinstance(delta_result, dict) else None)
            )
        else:
            self._last_planning_delta = delta_from_rule_based(best_action, rule_deltas)
        context = self.memory.get_relevant_context(limit=5)
        rationale = f"Goal-driven: {best_action} (goals: {self.short_term_goals[:2]})"
        if context:
            rationale = rationale + ". " + context[:200]
        return Proposal(
            agent_name=self.name,
            action_type=best_action,
            parameters={},
            rationale=rationale,
            confidence=0.7,
        )

    def generate_candidate_actions(self, world_snapshot: dict[str, Any]) -> list[str]:
        """Override in subclass. Default: return variable-driven actions from snapshot variables."""
        variables = world_snapshot.get("variables") or world_snapshot.get("global_state") or {}
        if isinstance(variables, dict) and variables:
            # Return first variable's increase/decrease actions as fallback
            first_var = list(variables.keys())[0]
            return [f"increase_{first_var}", f"decrease_{first_var}"]
        return []

    def reflect(self, history: list[dict[str, Any]], world_snapshot: dict[str, Any]) -> None:
        """Update memory from history and new snapshot. Call memory.add_event from loop after step."""
        self.memory.update_beliefs(world_snapshot)

    def decay_memory(self) -> None:
        """Decay importance of all memories and remove faded ones (importance < 0.05)."""
        for entry in self.long_term_memory:
            entry["importance"] *= 0.95
        self.long_term_memory = [e for e in self.long_term_memory if e["importance"] >= 0.05]

    def _calculate_importance(
        self,
        delta: Any,
        previous_state: dict[str, Any],
        current_state: dict[str, Any],
    ) -> float:
        """Calculate importance from normalized state delta. Returns max(abs(normalized_change)) across relevant variables."""
        if not delta:
            return 0.0
        
        # Get numeric updates from delta
        numeric_updates = {}
        if hasattr(delta, "numeric_updates"):
            numeric_updates = delta.numeric_updates or {}
        elif isinstance(delta, dict):
            numeric_updates = delta.get("numeric_updates", {})
        
        if not numeric_updates:
            return 0.0
        
        # Calculate normalized changes for variables relevant to agent objectives
        prev_gs = previous_state.get("global_state") or previous_state.get("variables") or {}
        curr_gs = current_state.get("global_state") or current_state.get("variables") or {}
        
        max_normalized_change = 0.0
        
        # Resolve objective key to state variable (variable-agnostic)
        from agents.utility import _objective_to_state_and_direction
        for obj_key in self.objectives.keys():
            mapped = _objective_to_state_and_direction(obj_key)
            state_key = mapped[0] if mapped else obj_key
            if state_key in numeric_updates:
                change = numeric_updates[state_key]
                if isinstance(change, (int, float)):
                    # Normalize the change
                    low, high = DEFAULT_NORM_RANGES.get(state_key, (0, 100))
                    if high > low:
                        normalized_change = abs(change) / (high - low)
                        max_normalized_change = max(max_normalized_change, normalized_change)
        
        # Also check direct state changes
        for state_key, change in numeric_updates.items():
            if isinstance(change, (int, float)):
                low, high = DEFAULT_NORM_RANGES.get(state_key, (0, 100))
                if high > low:
                    normalized_change = abs(change) / (high - low)
                    max_normalized_change = max(max_normalized_change, normalized_change)
        
        return min(1.0, max_normalized_change)

    def _calculate_valence(
        self,
        proposal: Any,
        delta: Any,
        was_accepted: bool,
        state_delta: dict[str, float],
        objectives: dict[str, float],
    ) -> float:
        """Calculate emotional valence: negative if rejected or worsens objectives, positive if accepted and helps."""
        if not was_accepted:
            return -0.7

        from agents.utility import _objective_to_state_and_direction
        positive_impact = 0.0
        negative_impact = 0.0
        total_weight = 0.0
        for obj_key, weight in objectives.items():
            if weight <= 0:
                continue
            mapped = _objective_to_state_and_direction(obj_key)
            if not mapped:
                continue
            state_key, direction = mapped
            change = state_delta.get(state_key, 0.0)
            if not isinstance(change, (int, float)):
                continue
            total_weight += weight
            # direction +1: higher state is better → positive change good; direction -1: lower state better → negative change good
            if (direction > 0 and change > 0) or (direction < 0 and change < 0):
                positive_impact += weight * abs(change)
            elif (direction > 0 and change < 0) or (direction < 0 and change > 0):
                negative_impact += weight * abs(change)

        if total_weight <= 0:
            return 0.0
        
        # Calculate net impact
        net_impact = (positive_impact - negative_impact) / total_weight
        
        # Map to valence range
        if net_impact > 0.1:
            return min(1.0, 0.5 + net_impact * 0.5)  # 0.5 to 1.0
        elif net_impact < -0.1:
            return max(-1.0, -0.3 + net_impact * 0.7)  # -1.0 to -0.3
        else:
            return 0.0

    def update_long_term_memory(
        self,
        turn: int,
        proposal: Any,
        delta: Any,
        was_accepted: bool,
        previous_state: dict[str, Any],
        current_state: dict[str, Any],
    ) -> None:
        """Append a summarized event to long_term_memory with importance and emotional valence."""
        # Create summarized event string
        action_type = ""
        if hasattr(proposal, "action_type"):
            action_type = proposal.action_type
        elif isinstance(proposal, dict):
            action_type = proposal.get("action_type", "")
        
        outcome = "accepted" if was_accepted else "rejected"
        event = f"{action_type} {outcome}"
        
        # Get state delta (numeric changes)
        state_delta: dict[str, float] = {}
        if hasattr(delta, "numeric_updates"):
            state_delta = delta.numeric_updates or {}
        elif isinstance(delta, dict):
            state_delta = delta.get("numeric_updates", {})
        
        # Calculate valence
        valence = self._calculate_valence(proposal, delta, was_accepted, state_delta, self.objectives)
        
        # Calculate importance based on outcome rules:
        # - If action rejected: importance = 0.5
        # - If action applied but backfires (negative valence): importance = 0.7
        # - If action aligns with goal (positive valence): importance = 1.0
        if not was_accepted:
            importance = 0.5
        elif valence < -0.1:  # Backfire: negative valence
            importance = 0.7
        elif valence > 0.1:  # Aligned: positive valence
            importance = 1.0
        else:
            # Neutral outcome: use calculated importance as fallback
            importance = self._calculate_importance(delta, previous_state, current_state)

        # Last 3 actions with perceived effectiveness (memory reinforcement)
        self.memory.last_action_outcomes.append({
            "action_type": action_type,
            "turn": turn,
            "effectiveness": valence,
        })
        self.memory.last_action_outcomes = self.memory.last_action_outcomes[-3:]

        # Update strategy class weight from outcome
        strategy_class = self._get_strategy_class(action_type)
        if strategy_class:
            w = self.strategy_class_weights.get(strategy_class, 1.0)
            if valence > 0.2:
                w = min(2.0, w + 0.2)
            elif valence < -0.2:
                w = max(0.2, w - 0.2)
            self.strategy_class_weights[strategy_class] = w

        # Append memory entry
        self.long_term_memory.append({
            "turn": turn,
            "event": event,
            "importance": importance,
            "emotional_valence": valence,
        })

    def state_to_dict(self) -> dict[str, Any]:
        """For snapshot: memory (includes beliefs), goals, long_term_memory, last_actions, [RL] weights."""
        out: dict[str, Any] = {
            "memory": self.memory.to_dict(),
            "beliefs": self.memory.beliefs,
            "long_term_goals": list(self.long_term_goals),
            "short_term_goals": list(self.short_term_goals),
            "long_term_memory": list(self.long_term_memory),
            "last_actions": list(self.last_actions),
            "strategy_class_weights": dict(self.strategy_class_weights),
            "rl_weights": dict(self._rl_weights),
            "rl_baseline": self._rl_baseline,
        }
        if self._belief_state is not None and hasattr(self._belief_state, "beliefs"):
            out["belief_state"] = {
                "beliefs": dict(self._belief_state.beliefs),
                "uncertainty": dict(self._belief_state.uncertainty),
                "confidence": self._belief_state.confidence,
            }
        return out

    @classmethod
    def restore_state(cls, agent: "BaseAgent", d: dict[str, Any]) -> None:
        """Restore agent memory/goals from snapshot dict."""
        if not d:
            return
        if d.get("memory"):
            agent.memory = AgentMemory.from_dict(d["memory"])
        if d.get("long_term_goals"):
            agent.long_term_goals = list(d["long_term_goals"])
        if d.get("short_term_goals"):
            agent.short_term_goals = list(d["short_term_goals"])
        if d.get("beliefs") and isinstance(d["beliefs"], dict):
            agent.memory.beliefs = dict(d["beliefs"])
            agent.memory.beliefs.setdefault("variables", {})
            agent.memory.beliefs.setdefault("confidence", {})
        if d.get("belief_state") and isinstance(d["belief_state"], dict):
            from agents.belief_model import BeliefState
            bs = d["belief_state"]
            agent._belief_state = BeliefState(
                beliefs=dict(bs.get("beliefs") or {}),
                uncertainty=dict(bs.get("uncertainty") or {}),
                confidence=float(bs.get("confidence", 0.5)),
            )
        if d.get("long_term_memory") and isinstance(d["long_term_memory"], list):
            agent.long_term_memory = list(d["long_term_memory"])
        if d.get("last_actions") and isinstance(d["last_actions"], list):
            agent.last_actions = list(d["last_actions"])[-2:]
        if d.get("strategy_class_weights") and isinstance(d["strategy_class_weights"], dict):
            agent.strategy_class_weights = dict(d["strategy_class_weights"])
        if d.get("rl_weights") and isinstance(d["rl_weights"], dict):
            agent._rl_weights = dict(d["rl_weights"])
        if d.get("rl_baseline") is not None and isinstance(d["rl_baseline"], (int, float)):
            agent._rl_baseline = float(d["rl_baseline"])