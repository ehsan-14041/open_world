"""
Registry health check: contextual validation. Emit INFO (not WARNING) when empty if scenario doesn't reference.
"""

from __future__ import annotations

import logging
from typing import Any

from core.rule_engine import get_registry_counts

logger = logging.getLogger(__name__)


def validate_registry_health(scenario: dict[str, Any]) -> dict[str, Any]:
    """
    Validate registries only if scenario includes corresponding constructs.
    Returns registry_status dict for output.
    """
    cond_count, effect_count = get_registry_counts()
    status: dict[str, Any] = {
        "condition_registry_count": cond_count,
        "effect_registry_count": effect_count,
        "rules_referenced": bool(scenario.get("rules")),
        "events_referenced": bool(scenario.get("events")),
        "constraints_referenced": bool(scenario.get("variable_specs") or scenario.get("governance")),
        "healthy": True,
        "messages": [],
    }

    rules = scenario.get("rules") or []
    events = scenario.get("events") or []

    if rules:
        if cond_count == 0 or effect_count == 0:
            status["healthy"] = False
            status["messages"].append(
                "Scenario has rules but condition/effect registry is empty; rules will not fire."
            )
            logger.info(
                "Registry: scenario has %d rules but condition_registry=%d, effect_registry=%d",
                len(rules), cond_count, effect_count,
            )
        else:
            status["messages"].append(
                f"Rules enabled: {len(rules)} rules, registries populated."
            )
    else:
        status["messages"].append("No rules in scenario; registry check skipped (INFO).")

    if events:
        if effect_count == 0:
            status["messages"].append(
                "Scenario has events but effect registry may be empty; event handlers may not fire."
            )
            logger.info("Registry: scenario has events but effect_registry=%d", effect_count)
    else:
        status["messages"].append("No events in scenario; event handler check skipped (INFO).")

    return status
