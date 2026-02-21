"""
Narrative firewall: replace placeholders with values from TurnRecord.
Model outputs prose with placeholders only; engine replaces deterministically.
"""

from __future__ import annotations

import re
from typing import Any

PLACEHOLDER_PATTERN = re.compile(r"\{\{([^:}]+)(?::([^}]*))?\}\}")


def replace_placeholders(
    text: str,
    turn_record: dict[str, Any],
    turn_index: int = 0,
) -> str:
    """
    Replace placeholders in text with values from turn_record.
    Placeholders: {{PRE:var}}, {{POST:var}}, {{DELTA:var}}, {{CROSS:var}}, {{EVENT:name}}, {{TURN}}, {{AGENT}}, {{ACTION}}
    """
    pre = turn_record.get("pre_state") or {}
    post = turn_record.get("post_state") or {}
    pre_vars = pre.get("variables") or pre.get("global_state") or {}
    post_vars = post.get("variables") or post.get("global_state") or {}
    delta_applied = turn_record.get("delta_applied") or {}
    events = turn_record.get("events_fired") or []
    chosen = turn_record.get("chosen_actions") or []

    def replacer(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        arg = (match.group(2) or "").strip()
        key_lower = key.lower()
        if key_lower == "turn":
            return str(turn_record.get("turn", turn_index))
        if key_lower == "pre" and arg:
            return str(pre_vars.get(arg, "?"))
        if key_lower == "post" and arg:
            return str(post_vars.get(arg, "?"))
        if key_lower == "delta":
            if ":" in (arg or ""):
                var, _ = arg.split(":", 1)
                return str(delta_applied.get(var.strip(), "?"))
            return str(delta_applied.get(arg, "?"))
        if key_lower == "var" and arg:
            return str(post_vars.get(arg, pre_vars.get(arg, "?")))
        if key_lower == "event":
            if events and isinstance(events[0], dict):
                return str(events[0].get("event_type", arg or "?"))
            return arg or "?"
        if key_lower == "agent" and chosen and isinstance(chosen[0], dict):
            return str(chosen[0].get("agent", "?"))
        if key_lower == "action" and chosen and isinstance(chosen[0], dict):
            return str(chosen[0].get("action_id", "?"))
        return match.group(0)

    return PLACEHOLDER_PATTERN.sub(replacer, text)


def strip_numeric_literals(text: str) -> str:
    """
    Remove standalone numeric literals that might have been output by model (for regeneration hint).
    Returns text with numbers replaced by placeholder markers.
    """
    return re.sub(r"\b\d+\.?\d*\b", "{{NUM}}", text)
