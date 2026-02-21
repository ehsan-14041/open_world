"""
Action trace: turn, agent_id, action, delta_raw, delta_applied, expected_utility, realized_utility.
Never store in causal_links; append to dedicated action_trace list.
"""

from __future__ import annotations

from typing import Any


def ActionTraceEntry(
    turn: int,
    agent_id: str,
    action: dict[str, Any],
    delta_raw: dict[str, float],
    delta_applied: dict[str, float],
    *,
    expected_utility: float | None = None,
    realized_utility: float | None = None,
    belief_basis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a single action trace entry (dict)."""
    return {
        "turn": turn,
        "agent_id": agent_id,
        "action": dict(action),
        "delta_raw": dict(delta_raw),
        "delta_applied": dict(delta_applied),
        "expected_utility": expected_utility,
        "realized_utility": realized_utility,
        "belief_basis": dict(belief_basis) if belief_basis else None,
    }


def append_action_trace_entry(
    action_trace: list[dict[str, Any]],
    turn: int,
    agent_id: str,
    action: dict[str, Any],
    delta_raw: dict[str, float],
    delta_applied: dict[str, float],
    *,
    expected_utility: float | None = None,
    realized_utility: float | None = None,
    belief_basis: dict[str, Any] | None = None,
) -> None:
    """Append one entry to action_trace. Mutates action_trace in place."""
    action_trace.append(
        ActionTraceEntry(
            turn,
            agent_id,
            action,
            delta_raw,
            delta_applied,
            expected_utility=expected_utility,
            realized_utility=realized_utility,
            belief_basis=belief_basis,
        )
    )
