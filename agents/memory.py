"""
AgentMemory: episodic and semantic memory, belief state (variables + confidence); serializable.
Agents observe world through noisy filter and update beliefs over time; decisions use beliefs.

Canonical memory shapes are defined in schemas/memory_schema.py (LLM Integration / scenario-to-simulation pipeline).
"""

from __future__ import annotations

import copy
from typing import Any

try:
    from core.observation import observe
except ImportError:
    def observe(snapshot: dict[str, Any], noise_scale: float = 0.0, rng: Any = None) -> dict[str, float]:
        gs = snapshot.get("variables") or snapshot.get("global_state") or {}
        return {k: float(v) for k, v in (gs if isinstance(gs, dict) else {}).items() if isinstance(v, (int, float))}


DEFAULT_EPISODIC_CAP = 50
DEFAULT_BELIEF_EMA_ALPHA = 0.7  # exponential moving average for belief update


class AgentMemory:
    """Per-agent memory: episodic events, semantic beliefs, belief state (variables, confidence), last observation. Serializable."""

    def __init__(
        self,
        *,
        episodic_memory: list[dict[str, Any]] | None = None,
        semantic_memory: dict[str, Any] | None = None,
        last_observation: dict[str, Any] | None = None,
        episodic_cap: int = DEFAULT_EPISODIC_CAP,
        beliefs: dict[str, Any] | None = None,
        observation_noise_scale: float = 0.0,
        initial_variables: dict[str, float] | None = None,
    ) -> None:
        self.episodic_memory = list(episodic_memory or [])
        self.semantic_memory = dict(semantic_memory or {})
        self.last_observation = copy.deepcopy(last_observation) if last_observation else None
        self.episodic_cap = episodic_cap
        self.beliefs = dict(beliefs or {})
        self.beliefs.setdefault("variables", {})
        self.beliefs.setdefault("confidence", {})
        # LLM Integration: seed beliefs from agent initial_variables when provided (scenario-to-simulation pipeline)
        if isinstance(initial_variables, dict) and initial_variables:
            for var, val in initial_variables.items():
                if isinstance(val, (int, float)):
                    self.beliefs["variables"][var] = float(val)
                    self.beliefs["confidence"].setdefault(var, 0.6)
        self.observation_noise_scale = observation_noise_scale
        # Last 3 actions with perceived outcome effectiveness (for memory reinforcement)
        self.last_action_outcomes: list[dict[str, Any]] = []
        # Track previous state for comparison (to detect unchanged world)
        self.previous_state: dict[str, Any] | None = None

    def add_event(
        self,
        turn: int,
        action: Any,
        outcome: Any,
        world_delta: Any,
        *,
        self_effect: dict[str, float] | None = None,
        global_world_delta: dict[str, float] | None = None,
    ) -> None:
        """Append one episodic event. Stores self_effect (agent-attributed) and global_world_delta for no false causation."""
        action_dict = action.to_dict() if hasattr(action, "to_dict") else (action if isinstance(action, dict) else {"action": str(action)})
        outcome_dict = outcome.to_dict() if hasattr(outcome, "to_dict") else (outcome if isinstance(outcome, dict) else {"outcome": str(outcome)})
        delta_dict = world_delta.to_dict() if hasattr(world_delta, "to_dict") else (world_delta if isinstance(world_delta, dict) else {})
        entry: dict[str, Any] = {
            "turn": turn,
            "action": action_dict,
            "outcome": outcome_dict,
            "world_delta": delta_dict,
        }
        if self_effect is not None:
            entry["self_effect"] = dict(self_effect)
        if global_world_delta is not None:
            entry["global_world_delta"] = dict(global_world_delta)
        self.episodic_memory.append(entry)
        if len(self.episodic_memory) > self.episodic_cap:
            self.episodic_memory = self.episodic_memory[-self.episodic_cap:]

    def update_beliefs(
        self,
        world_state: dict[str, Any],
        *,
        expected_delta: dict[str, float] | None = None,
        actual_delta: dict[str, float] | None = None,
        primary_variable: str | None = None,
    ) -> None:
        """
        Observe world through noisy filter; update belief variables and confidence.
        Confidence updates based on expected_delta vs actual_delta of primary variable ONLY.
        Ignores secondary ripple effects for confidence calculation.
        """
        current_gs = (world_state.get("global_state") or world_state.get("variables") or {}) if isinstance(world_state, dict) else {}
        
        self.last_observation = copy.deepcopy(world_state)
        gs = current_gs
        if isinstance(gs, dict):
            self.semantic_memory["global_state_summary"] = dict(gs)
        self.semantic_memory["last_turn"] = world_state.get("turn") if isinstance(world_state, dict) else None
        self.semantic_memory["last_version"] = world_state.get("version") if isinstance(world_state, dict) else None
        observed = observe(world_state, noise_scale=self.observation_noise_scale)
        if not observed:
            # Store current state as previous for next comparison
            self.previous_state = copy.deepcopy(world_state)
            return
        
        alpha = DEFAULT_BELIEF_EMA_ALPHA
        for var, val in observed.items():
            prev = self.beliefs["variables"].get(var)
            if prev is not None and isinstance(prev, (int, float)):
                self.beliefs["variables"][var] = alpha * float(prev) + (1 - alpha) * val
            else:
                self.beliefs["variables"][var] = val
        
        # Update confidence based on expected vs actual delta of primary variable ONLY
        if primary_variable and expected_delta is not None and actual_delta is not None:
            expected_primary_delta = expected_delta.get(primary_variable, 0.0)
            actual_primary_delta = actual_delta.get(primary_variable, 0.0)
            
            if isinstance(expected_primary_delta, (int, float)) and isinstance(actual_primary_delta, (int, float)):
                conf = self.beliefs["confidence"].get(primary_variable, 0.5)
                
                # Calculate accuracy: how close was actual to expected?
                if abs(expected_primary_delta) > 1e-6:
                    accuracy = 1.0 - min(1.0, abs(actual_primary_delta - expected_primary_delta) / abs(expected_primary_delta))
                else:
                    # If expected delta is near zero, check if actual is also near zero
                    accuracy = 1.0 if abs(actual_primary_delta) < 1e-6 else 0.5
                
                # Update confidence based on accuracy
                if accuracy > 0.8:
                    # Very accurate: increase confidence
                    self.beliefs["confidence"][primary_variable] = min(1.0, conf + 0.1)
                elif accuracy > 0.5:
                    # Moderately accurate: slight increase
                    self.beliefs["confidence"][primary_variable] = min(1.0, conf + 0.05)
                elif accuracy > 0.2:
                    # Inaccurate: decrease confidence
                    self.beliefs["confidence"][primary_variable] = max(0.1, conf - 0.05)
                else:
                    # Very inaccurate: significant decrease
                    self.beliefs["confidence"][primary_variable] = max(0.1, conf - 0.15)
        
        # For non-primary variables, use simple observation-based confidence (no expected vs actual comparison)
        for var, val in observed.items():
            if var == primary_variable:
                continue  # Already handled above
            
            conf = self.beliefs["confidence"].get(var, 0.5)
            prev = self.beliefs["variables"].get(var)
            
            if prev is not None and abs(float(prev) - val) < 1e-6:
                # Variable didn't change: slight increase
                self.beliefs["confidence"][var] = min(1.0, conf + 0.02)
            else:
                # Variable changed: slight decrease (less certain about observations)
                self.beliefs["confidence"][var] = max(0.1, conf - 0.01)
        
        # Store current state as previous for next comparison
        self.previous_state = copy.deepcopy(world_state)

    def get_relevant_context(self, limit: int | None = None) -> str:
        """Return a summary string of recent episodes and beliefs for prompts."""
        parts: list[str] = []
        episodes = self.episodic_memory
        if limit is not None and limit > 0:
            episodes = episodes[-limit:]
        for e in episodes:
            turn = e.get("turn", "?")
            action = e.get("action") or {}
            act_type = action.get("action_type", action.get("action", "?"))
            rationale = (e.get("outcome") or {}).get("rationale", (e.get("world_delta") or {}).get("rationale", ""))
            parts.append(f"Turn {turn}: did {act_type}. {rationale}".strip())
        if parts:
            parts.append("")
        if self.semantic_memory:
            summary = self.semantic_memory.get("global_state_summary") or {}
            if summary:
                parts.append("Beliefs (world summary): " + ", ".join(f"{k}={v}" for k, v in list(summary.items())[:10]))
        return "\n".join(parts).strip() if parts else ""

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict for snapshot."""
        return {
            "episodic_memory": list(self.episodic_memory),
            "semantic_memory": dict(self.semantic_memory),
            "last_observation": copy.deepcopy(self.last_observation) if self.last_observation else None,
            "episodic_cap": self.episodic_cap,
            "beliefs": copy.deepcopy(self.beliefs),
            "observation_noise_scale": self.observation_noise_scale,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentMemory:
        """Restore from snapshot dict."""
        if not d:
            return cls()
        inst = cls(
            episodic_memory=d.get("episodic_memory") or [],
            semantic_memory=d.get("semantic_memory") or {},
            last_observation=d.get("last_observation"),
            episodic_cap=int(d.get("episodic_cap", DEFAULT_EPISODIC_CAP)),
            beliefs=d.get("beliefs"),
            observation_noise_scale=float(d.get("observation_noise_scale", 0.0)),
            initial_variables=d.get("initial_variables"),
        )
        if isinstance(d.get("last_action_outcomes"), list):
            inst.last_action_outcomes = d["last_action_outcomes"][-3:]
        return inst
