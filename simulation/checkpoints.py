"""
Checkpoint store for simulation rollback: hold bounded list of (turn, snapshot, provenance_slice).
Restore world and truncate provenance to a given turn.
"""

from __future__ import annotations

from typing import Any


class CheckpointStore:
    """Bounded list of checkpoints for rollback. Each entry: {turn, snapshot, provenance_slice, action_trace_slice}."""

    def __init__(self, max_count: int = 10) -> None:
        self._max_count = max(1, max_count)
        self._checkpoints: list[dict[str, Any]] = []

    def push(
        self,
        turn: int,
        snapshot: dict[str, Any],
        provenance_slice: list[dict[str, Any]],
        action_trace_slice: list[dict[str, Any]] | None = None,
    ) -> None:
        """Append a checkpoint; trim if over max_count."""
        self._checkpoints.append({
            "turn": turn,
            "snapshot": dict(snapshot),
            "provenance_slice": list(provenance_slice),
            "action_trace_slice": list(action_trace_slice or []),
        })
        while len(self._checkpoints) > self._max_count:
            self._checkpoints.pop(0)

    def get_for_turn(self, turn: int) -> dict[str, Any] | None:
        """Return the checkpoint for the given turn, or None."""
        for cp in reversed(self._checkpoints):
            if cp["turn"] == turn:
                return cp
        return None

    def rollback_to_turn(
        self,
        world: Any,
        provenance_list: list[dict[str, Any]],
        action_trace_list: list[dict[str, Any]],
        turn: int,
    ) -> bool:
        """
        Restore world and truncate provenance/action_trace to the given turn.
        Returns True if a checkpoint was found and applied.
        """
        cp = self.get_for_turn(turn)
        if cp is None:
            return False
        snap = cp["snapshot"]
        if hasattr(world, "load_snapshot"):
            world.load_snapshot(snap)
        else:
            world.variables = dict(snap.get("variables") or snap.get("global_state") or {})
            world.entities = dict(snap.get("entities") or {})
            world.relations = list(snap.get("relations") or [])
            world.turn = int(snap.get("turn", 0))
            world.version = int(snap.get("version", 0))
        provenance_list.clear()
        provenance_list.extend(cp.get("provenance_slice") or [])
        action_trace_list.clear()
        action_trace_list.extend(cp.get("action_trace_slice") or [])
        return True

    def rollback_last_step(
        self,
        world: Any,
        provenance_list: list[dict[str, Any]],
        action_trace_list: list[dict[str, Any]],
    ) -> bool:
        """Rollback to the previous turn (state at start of current step). Returns True if applied."""
        current_turn = getattr(world, "turn", 0)
        target_turn = max(0, current_turn - 1)
        return self.rollback_to_turn(world, provenance_list, action_trace_list, target_turn)

    def clear(self) -> None:
        """Clear all checkpoints."""
        self._checkpoints.clear()
