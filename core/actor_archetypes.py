"""
Actor Archetype Library (Phase 3 — the reacting agents).

The linter (and the Scenario Grammar §7.5 L3) demands a *second mover* — a competitor,
regulator, or supplier that reacts — because a world with only the decider is a
shadow-box, not a war-game. Authoring those actors by hand is the friction this library
removes: drop in a named archetype and it anchors its objectives to the variables your
scenario actually declares.

Archetypes are **variable-agnostic**: each declares preferred (keyword, direction)
objective patterns. `build_archetype_agent` binds them to the real variables present in a
scenario; if none match, the archetype can't anchor and is skipped (no fictional goals).

Objective keys use `increase_<var>` / `decrease_<var>` so direction is explicit
(`core.legacy_semantics.legacy_goal_to_var_direction`).
"""

from __future__ import annotations

import copy
from typing import Any

# Each archetype: role + ordered (keyword, direction_prefix) objective preferences.
# We bind to the first `max_objectives` distinct variables whose name contains a keyword.
ARCHETYPES: dict[str, dict[str, Any]] = {
    "competitor": {
        "role": "Competitor",
        "intent": "erode your market position",
        "prefs": [
            ("customers", "decrease_"), ("market_share", "decrease_"), ("share", "decrease_"),
            ("mrr", "decrease_"), ("revenue", "decrease_"), ("sales", "decrease_"),
            ("fill_rate", "decrease_"),
        ],
        "max_objectives": 2,
    },
    "customer": {
        "role": "Customer",
        "intent": "resist price increases and churn-inducing moves",
        "prefs": [
            ("price", "decrease_"), ("unit_cost", "decrease_"), ("churn", "decrease_"),
            ("fill_rate", "increase_"), ("quality", "increase_"), ("service", "increase_"),
        ],
        "max_objectives": 2,
    },
    "regulator": {
        "role": "Regulator",
        "intent": "enforce stability and limit systemic risk",
        "prefs": [
            ("stability", "increase_"), ("compliance", "increase_"), ("safety", "increase_"),
            ("risk", "decrease_"), ("dissatisfaction", "decrease_"),
        ],
        "max_objectives": 2,
    },
    "supplier": {
        "role": "Supplier",
        "intent": "protect its margin and capacity",
        "prefs": [
            ("unit_cost", "increase_"), ("capacity_utilization", "increase_"),
            ("lead_time", "increase_"), ("volume", "increase_"), ("supplier_risk", "increase_"),
        ],
        "max_objectives": 2,
    },
}


def list_archetypes() -> list[dict[str, str]]:
    """Return the catalog (name, role, intent) for UI / API listing."""
    return [{"name": k, "role": v["role"], "intent": v["intent"]} for k, v in ARCHETYPES.items()]


def _state_vars(scenario: dict[str, Any]) -> list[str]:
    st = scenario.get("initial_state")
    return list(st.keys()) if isinstance(st, dict) else []


def build_archetype_agent(name: str, scenario: dict[str, Any]) -> dict[str, Any] | None:
    """
    Build an actor of the given archetype, anchored to the scenario's variables.
    Returns an `initial_agents` entry, or None if no variable matches (cannot anchor).
    """
    spec = ARCHETYPES.get(name)
    if not spec:
        return None
    state_vars = _state_vars(scenario)
    objectives: dict[str, float] = {}
    used: set[str] = set()
    for keyword, prefix in spec["prefs"]:
        if len(objectives) >= spec["max_objectives"]:
            break
        for var in state_vars:
            if var in used:
                continue
            if keyword in var.lower():
                objectives[f"{prefix}{var}"] = 1.0
                used.add(var)
                break
    if not objectives:
        return None
    return {"name": name, "role": spec["role"], "objectives": objectives}


def apply_archetypes(
    scenario: dict[str, Any],
    names: list[str],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Return (scenario_copy, added, skipped). Appends archetype actors to initial_agents,
    skipping any whose name already exists or that cannot anchor to a scenario variable.
    """
    sc = copy.deepcopy(scenario or {})
    agents = sc.get("initial_agents")
    if not isinstance(agents, list):
        agents = []
    existing = {a.get("name") for a in agents if isinstance(a, dict)}
    added: list[str] = []
    skipped: list[str] = []
    for name in names or []:
        if name in existing:
            skipped.append(name)
            continue
        agent = build_archetype_agent(name, sc)
        if agent is None:
            skipped.append(name)
            continue
        agents.append(agent)
        existing.add(name)
        added.append(name)
    sc["initial_agents"] = agents
    return sc, added, skipped
