"""
Stage 5: Model Serializer.
Input: full dynamic model
Output: final JSON compatible with SimulationLoop.
Emits action_tradeoffs, variable_specs, strategy_classes, rules, events, per-agent actions.
"""

from __future__ import annotations

from typing import Any

from core.scenario_compiler import build_agent_prompt
from schemas.scenario_schema import normalize_scenario


def _derive_relations(entities: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Derive relations from entity alignments."""
    relations: list[dict[str, str]] = []
    names = [e.get("name") for e in entities if isinstance(e.get("name"), str)]
    alignments = {
        e.get("name"): (e.get("alignment") or "").strip().lower()
        for e in entities
        if isinstance(e, dict)
    }
    for i, n1 in enumerate(names):
        for n2 in names[i + 1 :]:
            if not n1 or not n2:
                continue
            a1, a2 = alignments.get(n1, ""), alignments.get(n2, "")
            if a1 and a2 and a1 != a2:
                if any(x in a1 for x in ("adversar", "oppos", "hostile", "conflict")) or any(
                    x in a2 for x in ("adversar", "oppos", "hostile", "conflict")
                ):
                    relations.append({"from": n1, "to": n2, "type": "conflicts_with"})
    return relations


def _causal_links_for_engine(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure causal links have weight for propagation."""
    out = []
    for link in links:
        d = dict(link)
        if "weight" not in d or d.get("weight") is None:
            pol = (d.get("polarity") or "positive").lower()
            strength = float(d.get("strength", 0.5))
            d["weight"] = -strength if pol == "negative" else strength
        out.append(d)
    return out


def _variable_tradeoffs_from_causal(causal_graph: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Derive variable_tradeoffs from causal graph secondary effects."""
    out: dict[str, dict[str, float]] = {}
    for link in causal_graph:
        from_var = link.get("from")
        to_var = link.get("to")
        if not from_var or not to_var:
            continue
        weight = link.get("weight")
        if weight is None:
            pol = (link.get("polarity") or "positive").lower()
            strength = float(link.get("strength", 0.5))
            weight = -strength if pol == "negative" else strength
        try:
            w = float(weight)
        except (TypeError, ValueError):
            continue
        if from_var not in out:
            out[from_var] = {}
        out[from_var][to_var] = w
    return out


def _variable_specs_from_variables(variables: dict[str, float]) -> dict[str, dict[str, Any]]:
    """Infer variable_specs (min, max, rate_limit) from variables."""
    out: dict[str, dict[str, Any]] = {}
    for var, val in variables.items():
        v = float(val) if isinstance(val, (int, float)) else 50.0
        out[var] = {
            "min": 0,
            "max": 100,
            "clip": True,
            "rate_limit": 10,
        }
    return out


def _events_from_variables_and_causal(
    variables: dict[str, float],
    causal_graph: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate potential emergent events from variables and causal structure."""
    events: list[dict[str, Any]] = []
    var_names = list(variables.keys())
    for var in var_names:
        if any(kw in var.lower() for kw in ("tension", "conflict", "stress")):
            events.append({
                "event_type": "crisis_if_high",
                "condition_key": f"{var}_above_80",
                "effect_key": "apply_crisis_effect",
                "params": {"variable": var, "threshold": 80},
            })
    return events[:5]


class ModelSerializer:
    """Serialize full dynamic model to scenario JSON."""

    @staticmethod
    def serialize(model: dict[str, Any]) -> dict[str, Any]:
        """
        Serialize model to scenario JSON.
        Emits action_tradeoffs, variable_specs, strategy_classes, rules, events, per-agent actions.
        """
        description = model.get("description") or "User-defined scenario"
        entities = model.get("entities") or []
        variables = model.get("variables") or {}
        causal_graph = model.get("causal_graph") or []
        incentives = model.get("incentives") or {}
        actions = model.get("actions") or []

        action_tradeoffs = model.get("action_tradeoffs") or {}
        action_specs = model.get("action_specs") or {}
        per_agent_actions = model.get("per_agent_actions") or {}
        strategy_classes = model.get("strategy_classes") or {}

        relations = _derive_relations(entities)
        causal_links = _causal_links_for_engine(causal_graph)
        variable_tradeoffs = model.get("variable_tradeoffs") or _variable_tradeoffs_from_causal(causal_graph)
        variable_specs = model.get("variable_specs") or _variable_specs_from_variables(variables)
        rules = model.get("rules") or []
        events = model.get("events") or _events_from_variables_and_causal(variables, causal_graph)

        initial_agents: list[dict[str, Any]] = []
        for e in entities:
            if not isinstance(e, dict):
                continue
            name = e.get("name")
            if not name:
                continue
            profile = incentives.get(name) or {}
            objectives = profile.get("objectives") or {}
            risk_tolerance = profile.get("risk_tolerance", 0.5)
            aggressiveness = profile.get("aggressiveness", 0.5)

            agent_actions = list(actions)
            if name in per_agent_actions and per_agent_actions[name]:
                agent_actions = per_agent_actions[name]

            world_model = {"variables": variables, "causal_links": causal_links}
            system_prompt = build_agent_prompt(e, profile, world_model, agent_actions)

            agent_entry: dict[str, Any] = {
                "name": name,
                "role": e.get("role") or name,
                "objectives": objectives,
                "risk_tolerance": risk_tolerance,
                "aggressiveness": aggressiveness,
                "system_prompt_override": system_prompt,
            }
            if agent_actions != actions:
                agent_entry["allowed_actions"] = agent_actions
            if profile.get("capabilities"):
                agent_entry["capabilities"] = profile["capabilities"]
            if profile.get("strategic_constraints"):
                agent_entry["strategic_constraints"] = profile["strategic_constraints"]
            initial_agents.append(agent_entry)

        scenario = {
            "description": description,
            "initial_agents": initial_agents,
            "initial_state": dict(variables),
            "relations": relations,
            "allowed_actions": list(actions),
            "causal_links": causal_links,
            "action_tradeoffs": dict(action_tradeoffs),
            "action_specs": dict(action_specs),
            "variable_tradeoffs": dict(variable_tradeoffs),
            "variable_specs": dict(variable_specs),
            "strategy_classes": dict(strategy_classes),
            "rules": list(rules),
            "events": list(events),
        }

        return normalize_scenario(scenario)
