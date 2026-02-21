"""
Event queue: unified queue of events that fire at trigger_turn.
Supports (1) delayed-delta events (from world.delayed_events) and (2) scenario-defined events (event_type + params).
No domain logic in core—only "at trigger_turn run handler for event_type with params".
"""

from __future__ import annotations

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


def _register_default_handlers() -> None:
    """Register handlers for environment agent default event types."""
    for name in ("incident", "negotiation_round", "deconfliction", "external_shock"):
        if name not in _event_handlers:
            register_event_handler(name, _apply_effects_handler)


_register_default_handlers()


def process_events_for_turn(
    world: Any,
    current_turn: int,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Run all events where trigger_turn == current_turn; remove them from the list.
    Returns list of triggered event records for trace: [{"trigger_turn": int, "event_type": str, "origin": str, "metadata": {}}, ...].
    """
    triggered: list[tuple[int, dict[str, Any]]] = []
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            continue
        if ev.get("trigger_turn") != current_turn:
            continue
        triggered.append((i, ev))
    applied: list[dict[str, Any]] = []
    for i, ev in reversed(triggered):
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
        events.pop(i)
    return applied
