"""
Layer 1: Deterministic fact extraction from run snapshots/turn_records.
Produces NarrativeFacts (domain-agnostic) for Layer 2 narrative weaving only.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from summarization.bucketing import bucket_numeric_to_ordinal, humanize_var_id


@dataclass
class NarrativeFacts:
    """Domain-agnostic facts for narrative. No raw numbers in labels; no domain keywords."""

    opening_context: list[str] = field(default_factory=list)  # 2-3 qualitative statements
    key_actors: list[dict[str, str]] = field(default_factory=list)  # 2-4: id (humanized), intent
    turning_points: list[str] = field(default_factory=list)  # 1-3 qualitative moments
    tradeoff: dict[str, str] = field(default_factory=dict)  # improvement, decline
    ending_state: list[str] = field(default_factory=list)  # 2-3 qualitative statements

    def to_dict(self) -> dict[str, Any]:
        return {
            "opening_context": self.opening_context,
            "key_actors": self.key_actors,
            "turning_points": self.turning_points,
            "tradeoff": self.tradeoff,
            "ending_state": self.ending_state,
        }


def _initial_state_from_trace(
    trace: list[dict[str, Any]],
    final_snapshot: dict[str, Any],
) -> dict[str, float]:
    """Derive initial variable state by reversing variable_changes along trace."""
    variables = dict(final_snapshot.get("variables") or final_snapshot.get("global_state") or {})
    if not isinstance(variables, dict):
        variables = {}
    initial = dict(variables)
    for entry in reversed(trace):
        for vc in entry.get("variable_changes") or []:
            var = vc.get("var")
            delta = vc.get("delta", 0)
            if var is not None:
                try:
                    initial[var] = initial.get(var, 0) - float(delta)
                except (TypeError, ValueError):
                    pass
    return initial


def _impact_score_turn(entry: dict[str, Any]) -> float:
    """Deterministic impact score for a trace entry (deltas, events, derived)."""
    score = 0.0
    for vc in entry.get("variable_changes") or []:
        score += abs(float(vc.get("delta", 0)))
    score += len(entry.get("events_triggered") or []) * 10.0
    derived = entry.get("derived") or {}
    if derived.get("instability_mode"):
        score += 5.0
    return score


def build_narrative_facts(
    trace: list[dict[str, Any]],
    final_snapshot: dict[str, Any],
    agents: list[dict[str, Any]] | None = None,
    scenario: dict[str, Any] | None = None,
    *,
    state_specs: dict[str, Any] | None = None,
) -> NarrativeFacts:
    """
    Build NarrativeFacts from trace and final_snapshot (and optional turn_records inside trace).
    Domain-agnostic: no domain keywords; variable names only as humanized ids.
    """
    state_specs = state_specs or {}
    variables = final_snapshot.get("variables") or final_snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}
    initial = _initial_state_from_trace(trace, final_snapshot)

    # opening_context: 2-3 qualitative statements (bucketing)
    opening_context: list[str] = []
    for i, (var_id, val) in enumerate(list(initial.items())[:3]):
        if i >= 3:
            break
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        spec = state_specs.get(var_id) if isinstance(state_specs, dict) else None
        level = bucket_numeric_to_ordinal(v, spec, lang="en")
        label = humanize_var_id(var_id)
        opening_context.append(f"{label} was {level}.")
    if not opening_context:
        opening_context = ["Key variables were in flux.", "The run started from an initial state."]

    # key_actors: 2-4 with generic humanized id + intent from objectives/goals
    key_actors: list[dict[str, str]] = []
    agent_configs: dict[str, dict] = {}
    for a in agents or []:
        if isinstance(a, dict) and a.get("name"):
            agent_configs[a["name"]] = a
    if scenario:
        for a in scenario.get("initial_agents") or []:
            if isinstance(a, dict) and a.get("name") and a["name"] not in agent_configs:
                agent_configs[a["name"]] = a
    # Collect from trace if no agents passed
    if not agent_configs:
        for entry in trace:
            for p in entry.get("actions") or entry.get("proposals") or []:
                name = p.get("agent_name") or p.get("agent")
                if name and name not in agent_configs:
                    agent_configs[name] = {"name": name, "role": name}
    for name, cfg in list(agent_configs.items())[:4]:
        role = (cfg.get("role") or name)
        display_id = humanize_var_id(role) if role else "Actor"
        objectives = cfg.get("objectives") or cfg.get("goals") or []
        if isinstance(objectives, dict):
            objectives = list(objectives.keys()) if objectives else []
        if isinstance(objectives, list) and objectives:
            intent = " and ".join(humanize_var_id(str(o)) for o in objectives[:2])
        else:
            intent = "pursue objectives"
        key_actors.append({"id": display_id, "intent": intent})
    if not key_actors:
        key_actors = [{"id": "Actors", "intent": "pursue objectives"}]

    # turning_points: 1-3 by impact score (qualitative description)
    turn_scores: list[tuple[int, float]] = []
    for i, entry in enumerate(trace):
        turn_scores.append((i, _impact_score_turn(entry)))
    turn_scores.sort(key=lambda x: -x[1])
    turning_points: list[str] = []
    for i, (idx, _) in enumerate(turn_scores[:3]):
        if i == 0:
            turning_points.append("A decisive shift occurred.")
        elif i == 1:
            turning_points.append("A notable change took place.")
        else:
            turning_points.append("A further development followed.")

    # tradeoff: one improvement, one decline (qualitative)
    var_totals: dict[str, float] = {}
    for entry in trace:
        for vc in entry.get("variable_changes") or []:
            var = vc.get("var")
            delta = vc.get("delta", 0)
            if var:
                var_totals[var] = var_totals.get(var, 0) + float(delta)
    sorted_vars = sorted(var_totals.items(), key=lambda x: -abs(x[1]))
    improvement_var = None
    decline_var = None
    for v, d in sorted_vars:
        if d > 0.5 and improvement_var is None:
            improvement_var = (v, d)
        if d < -0.5 and decline_var is None:
            decline_var = (v, d)
        if improvement_var and decline_var:
            break
    improvement = "One aspect improved."
    decline = "Another aspect declined."
    if improvement_var:
        improvement = f"{humanize_var_id(improvement_var[0])} improved."
    if decline_var:
        decline = f"{humanize_var_id(decline_var[0])} declined."
    tradeoff = {"improvement": improvement, "decline": decline}

    # ending_state: 2-3 qualitative statements
    ending_state: list[str] = []
    for var_id, val in list(variables.items())[:3]:
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        spec = state_specs.get(var_id) if isinstance(state_specs, dict) else None
        level = bucket_numeric_to_ordinal(v, spec, lang="en")
        label = humanize_var_id(var_id)
        ending_state.append(f"{label} ended {level}.")
    if not ending_state:
        ending_state = ["The run reached a final state.", "Outcomes were determined by the actions taken."]

    return NarrativeFacts(
        opening_context=opening_context[:3],
        key_actors=key_actors[:4],
        turning_points=turning_points,
        tradeoff=tradeoff,
        ending_state=ending_state[:3],
    )
