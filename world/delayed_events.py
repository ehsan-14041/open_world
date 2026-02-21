"""
Delayed events: queue of effects that fire at a given turn.

Class diagram:
  DelayedEvent
    - trigger_turn: int
    - delta: Delta
    - source_action: str
    - probability: float | None
    - to_dict() / from_dict()
  apply_delayed_events_for_turn(world, current_turn, delayed_events) -> list[DelayedEvent]
"""

from __future__ import annotations

import random
from typing import Any

from schemas.delta_schema import Delta


class DelayedEvent:
    """Single delayed effect: trigger_turn, delta, source_action, optional probability."""

    __slots__ = ("trigger_turn", "delta", "source_action", "probability")

    def __init__(
        self,
        trigger_turn: int,
        delta: Delta | dict[str, Any],
        source_action: str,
        *,
        probability: float | None = None,
    ) -> None:
        self.trigger_turn = trigger_turn
        self.delta = delta if isinstance(delta, Delta) else Delta.from_dict(delta)
        self.source_action = source_action
        self.probability = probability  # None means 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_turn": self.trigger_turn,
            "delta": self.delta.to_dict() if hasattr(self.delta, "to_dict") else self.delta,
            "source_action": self.source_action,
            "probability": self.probability,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DelayedEvent:
        delta = d.get("delta")
        if isinstance(delta, dict):
            delta = Delta.from_dict(delta)
        return cls(
            trigger_turn=int(d["trigger_turn"]),
            delta=delta,
            source_action=str(d.get("source_action", "")),
            probability=d.get("probability"),
        )


def apply_delayed_events_for_turn(
    world: Any,
    current_turn: int,
    delayed_events: list[DelayedEvent],
    *,
    rng: random.Random | None = None,
) -> list[DelayedEvent]:
    """
    Apply all delayed events where trigger_turn == current_turn.
    If probability is set, roll and skip if not triggered.
    Mutates world via world.apply_delta; mutates delayed_events list by removing applied.
    Returns list of events that were applied.
    """
    rng = rng or random.Random()
    to_apply: list[tuple[int, DelayedEvent]] = []
    for i, event in enumerate(delayed_events):
        if event.trigger_turn != current_turn:
            continue
        if event.probability is not None:
            if not (0 <= event.probability <= 1):
                continue
            if rng.random() > event.probability:
                continue
        to_apply.append((i, event))

    applied: list[DelayedEvent] = []
    for i, event in reversed(to_apply):
        if hasattr(world, "apply_delta"):
            world.apply_delta(event.delta)
        applied.append(event)
        delayed_events.pop(i)

    return applied
