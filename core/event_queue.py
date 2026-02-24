"""
Event queue: unified queue of events that fire at trigger_turn.
Supports (1) delayed-delta events (from world.delayed_events) and (2) scenario-defined events (event_type + params).
No domain logic in core—only "at trigger_turn run handler for event_type with params".
"""

from __future__ import annotations

import heapq
from typing import Any, Callable

from schemas.delta_schema import Delta

# Registry: event_type -> (world, params) -> None
_event_handlers: dict[str, Callable[[Any, dict[str, Any]], None]] = {}


def register_event_handler(event_type: str, fn: Callable[[Any, dict[str, Any]], None]) -> None:
    """Register handler for scenario-defined events. Domain loaders register by event_type."""
    _event_handlers[event_type] = fn


def _apply_effects_handler(world: Any, params: dict[str, Any]) -> None:
    """Generic handler: apply params['effects'] as delta ops (increase_variable, decrease_variable, set_variable)."""
    effects = params.get("effects") or []
    if not effects or not hasattr(world, "apply_delta"):
        return
    numeric_updates: dict[str, float] = {}
    for op in effects:
        if not isinstance(op, dict):
            continue
        op_type = op.get("op", "")
        key = op.get("key")
        value = op.get("value")
        if not key:
            continue
        try:
            v = float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            continue
        if op_type == "increase_variable":
            numeric_updates[key] = numeric_updates.get(key, 0) + v
        elif op_type == "decrease_variable":
            numeric_updates[key] = numeric_updates.get(key, 0) - v
        elif op_type == "set_variable":
            current = getattr(world, "variables", {}).get(key, 0) or 0
            try:
                cur = float(current)
            except (TypeError, ValueError):
                cur = 0.0
            numeric_updates[key] = v - cur
    if numeric_updates:
        delta = Delta(numeric_updates=numeric_updates, rationale="Environment event")
        world.apply_delta(delta)


def _conflict_handler(_world: Any, params: dict[str, Any]) -> None:
    """Log-only handler for epistemic_gap ConflictEvent. No world state change by default."""
    import logging
    agent = params.get("agent", "?")
    variable = params.get("variable", "?")
    gap = params.get("gap", 0)
    logging.getLogger(__name__).info(
        "ConflictEvent (epistemic_gap): agent=%s variable=%s gap=%.4f",
        agent, variable, float(gap) if isinstance(gap, (int, float)) else 0,
    )


def _register_default_handlers() -> None:
    """Register handlers for environment agent default event types."""
    for name in ("incident", "negotiation_round", "deconfliction", "external_shock"):
        if name not in _event_handlers:
            register_event_handler(name, _apply_effects_handler)
    if "conflict" not in _event_handlers:
        register_event_handler("conflict", _conflict_handler)


_register_default_handlers()


def process_events_for_turn(
    world: Any,
    current_turn: int,
    events: list[dict[str, Any]],
    max_events_per_turn: int | None = None,
) -> list[dict[str, Any]]:
    """
    Run events where trigger_turn == current_turn; sort by priority (lower = higher), then process up to max_events_per_turn.
    Remove processed events from the list. Returns list of triggered event records for trace.
    """
    try:
        from config.settings import MAX_EVENTS_PER_TURN
        limit = max_events_per_turn if max_events_per_turn is not None else MAX_EVENTS_PER_TURN
    except ImportError:
        limit = 20
    heap: list[tuple[int, int, dict[str, Any]]] = []
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            continue
        if ev.get("trigger_turn") != current_turn:
            continue
        priority = int(ev.get("priority", 0))
        heapq.heappush(heap, (priority, i, ev))
    to_process: list[tuple[int, dict[str, Any]]] = []
    while heap and len(to_process) < limit:
        _pri, i, ev = heapq.heappop(heap)
        to_process.append((i, ev))
    if heap and limit:
        import logging
        logging.getLogger(__name__).warning(
            "Event queue: %d events for turn %d, processing only first %d (MAX_EVENTS_PER_TURN)",
            len(to_process) + len(heap), current_turn, limit,
        )
    applied: list[dict[str, Any]] = []
    for i, ev in reversed(to_process):
        event_type = ev.get("event_type", "")
        params = ev.get("params") or {}
        handler = _event_handlers.get(event_type)
        if handler is not None:
            try:
                handler(world, params)
            except Exception:
                pass
        applied.append({
            "trigger_turn": current_turn,
            "event_type": event_type,
            "origin": ev.get("origin", ""),
            "metadata": dict(ev.get("metadata") or {}),
        })
    for i in sorted((idx for idx, _ in to_process), reverse=True):
        if 0 <= i < len(events):
            events.pop(i)
    return applied
