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

from typing import Any

from schemas.proposal_schema import Proposal

from agents.memory import AgentMemory
from agents.planner import plan_depth2, plan_depth2_with_callback
from agents.utility import evaluate_short_term_goals, goals_from_objectives, DEFAULT_NORM_RANGES

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

    @property
    def beliefs(self) -> dict[str, Any]:
        """Belief state: variables (agent view of world) and confidence per variable."""
        return self.memory.beliefs

    def _get_strategy_class(self, action_type: str) -> str:
        """Map action_type to strategy class from scenario or infer from name."""
        if not action_type or not isinstance(action_type, str):
            return "default"
        if action_type in self.strategy_classes:
            return self.strategy_classes[action_type]
        at = action_type.lower()
        if at.startswith("launch_") or at.startswith("increase_") and "growth" in at or "growth" in at:
            return "growth"
        if at.startswith("steady_") or "conserve" in at or "finance" in at:
            return "conservation"
        if at.startswith("propose_") or at.startswith("form_") or "regulation" in at or "governance" in at:
            return "governance"
        if at.startswith("request_") or "investment" in at:
            return "investment"
        return "default"

    def propose(self, world_snapshot: dict[str, Any]) -> Proposal:
        """Observe real world -> update_beliefs; then evaluate_goals, plan, select using belief snapshot (not real state)."""
        self.memory.update_beliefs(world_snapshot)
        belief_vars = self.memory.beliefs.get("variables") or {}
        belief_snapshot = _belief_snapshot_from_world(world_snapshot, belief_vars) if belief_vars else world_snapshot
        self.short_term_goals = evaluate_short_term_goals(self.long_term_goals, belief_snapshot)
        candidates = self.generate_candidate_actions(belief_snapshot)
        if not candidates:
            # Fallback: use first available variable-driven action if variables exist
            variables = belief_snapshot.get("variables") or belief_snapshot.get("global_state") or {}
            if isinstance(variables, dict) and variables:
                first_var = list(variables.keys())[0]
                fallback_action = f"increase_{first_var}"
            else:
                fallback_action = "adjust_variable"
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
        if get_delta is not None:
            best_action = plan_depth2_with_callback(
                belief_snapshot,
                candidates,
                self.objectives,
                get_delta,
                beliefs=self.memory.semantic_memory,
            )
            delta_result = get_delta(best_action)
            self._last_planning_delta = (
                delta_result.to_dict() if hasattr(delta_result, "to_dict") else (delta_result if isinstance(delta_result, dict) else None)
            )
        else:
            self._last_planning_delta = None
            rule_deltas = rule_based_deltas_for_snapshot(belief_snapshot)
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
            )
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
        """For snapshot: memory (includes beliefs), goals, long_term_memory, last_actions."""
        return {
            "memory": self.memory.to_dict(),
            "beliefs": self.memory.beliefs,
            "long_term_goals": list(self.long_term_goals),
            "short_term_goals": list(self.short_term_goals),
            "long_term_memory": list(self.long_term_memory),
            "last_actions": list(self.last_actions),
            "strategy_class_weights": dict(self.strategy_class_weights),
        }

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
        if d.get("long_term_memory") and isinstance(d["long_term_memory"], list):
            agent.long_term_memory = list(d["long_term_memory"])
        if d.get("last_actions") and isinstance(d["last_actions"], list):
            agent.last_actions = list(d["last_actions"])[-2:]
        if d.get("strategy_class_weights") and isinstance(d["strategy_class_weights"], dict):
            agent.strategy_class_weights = dict(d["strategy_class_weights"])