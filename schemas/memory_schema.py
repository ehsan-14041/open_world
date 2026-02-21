"""
Memory schema: canonical shapes for agent memory used by the simulation loop.
LLM Integration: created at agent creation and updated per turn for each agent.
See agents/memory.py (AgentMemory) and agents/base_agent.py (long_term_memory).
"""

from __future__ import annotations

from typing import Any

# Episodic event: one entry per turn/action, appended by AgentMemory.add_event()
# Shape: { "turn": int, "action": dict, "outcome": dict, "world_delta": dict }
EPISODIC_EVENT_KEYS = {"turn", "action", "outcome", "world_delta"}

# Beliefs: agent view of world variables and confidence per variable
# Shape: { "variables": dict[str, float], "confidence": dict[str, float] }
BELIEFS_KEYS = {"variables", "confidence"}

# Semantic memory: summary and metadata (updated in AgentMemory.update_beliefs)
# Typical keys: "global_state_summary" (dict), "last_turn" (int), "last_version" (int)
SEMANTIC_MEMORY_KEYS = {"global_state_summary", "last_turn", "last_version"}

# Long-term memory entry (BaseAgent.long_term_memory): summarized event with importance
# Shape: { "turn": int, "event": str, "importance": float, "emotional_valence": float }
LONG_TERM_ENTRY_KEYS = {"turn", "event", "importance", "emotional_valence"}


def episodic_event_shape() -> dict[str, Any]:
    """Return expected shape description for episodic event (documentation)."""
    return {
        "turn": "int",
        "action": "dict (Proposal or equivalent)",
        "outcome": "dict",
        "world_delta": "dict (Delta or equivalent)",
    }


def beliefs_shape() -> dict[str, Any]:
    """Return expected shape description for beliefs (documentation)."""
    return {
        "variables": "dict[str, float]",
        "confidence": "dict[str, float]",
    }


def long_term_entry_shape() -> dict[str, Any]:
    """Return expected shape description for long-term memory entry (documentation)."""
    return {
        "turn": "int",
        "event": "str",
        "importance": "float",
        "emotional_valence": "float",
    }
