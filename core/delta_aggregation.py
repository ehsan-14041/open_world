"""
Aggregate per-turn deltas into global delta and action impact summary.
Used by scenario_analysis_output for Logic Core.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def compute_global_delta(provenance: list[dict[str, Any]]) -> dict[str, float]:
    """
    Compute cumulative change per variable from first to last turn.
    provenance: list of entries with "turn_record" containing "delta_applied".
    Returns dict[var, total_delta].
    """
    out: dict[str, float] = {}
    for entry in provenance:
        tr = entry.get("turn_record")
        if not isinstance(tr, dict):
            continue
        delta_applied = tr.get("delta_applied")
        if not isinstance(delta_applied, dict):
            continue
        for var, val in delta_applied.items():
            if isinstance(val, (int, float)):
                out[var] = out.get(var, 0.0) + float(val)
    return out


def compute_action_impact_summary(
    provenance: list[dict[str, Any]],
    action_definitions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    For each distinct action_id chosen across the run, summarize its impact on variables
    (from self_effect_per_agent and chosen_actions). Returns a list of
    { "action_id", "agent", "turn", "variables_affected": { var: delta }, "dominant_variable" }.
    dominant_variable: variable with largest absolute effect for that action instance.
    """
    action_definitions = action_definitions or {}
    impact_list: list[dict[str, Any]] = []

    for entry in provenance:
        tr = entry.get("turn_record")
        if not isinstance(tr, dict):
            continue
        chosen = tr.get("chosen_actions") or []
        self_effect = tr.get("self_effect_per_agent") or {}
        turn = tr.get("turn") or entry.get("turn")

        for choice in chosen:
            if not isinstance(choice, dict):
                continue
            agent = choice.get("agent", "")
            action_id = choice.get("action_id") or choice.get("action")
            if not action_id:
                continue
            # Aggregate this agent's attributed effect for this turn
            agent_effect = self_effect.get(agent)
            if not isinstance(agent_effect, dict):
                agent_effect = {}
            variables_affected = {k: v for k, v in agent_effect.items() if isinstance(v, (int, float)) and abs(v) > 1e-9}
            if not variables_affected:
                continue
            dominant_var = max(variables_affected.keys(), key=lambda v: abs(variables_affected[v])) if variables_affected else None
            impact_list.append({
                "action_id": action_id,
                "agent": agent,
                "turn": turn,
                "variables_affected": variables_affected,
                "dominant_variable": dominant_var,
            })

    return impact_list


def summarize_action_impact_by_action_id(
    action_impact_list: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Group impact list by action_id and return per action_id:
    - total_occurrences
    - variables_affected_aggregate: sum of absolute deltas per var
    - dominant_variable_overall: var most often dominant or with largest aggregate effect
    """
    by_action: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in action_impact_list:
        aid = item.get("action_id", "")
        if aid:
            by_action[aid].append(item)

    result: dict[str, dict[str, Any]] = {}
    for action_id, items in by_action.items():
        var_totals: dict[str, float] = defaultdict(float)
        dominant_counts: dict[str, int] = defaultdict(int)
        for it in items:
            for var, delta in (it.get("variables_affected") or {}).items():
                var_totals[var] += abs(delta)
            dom = it.get("dominant_variable")
            if dom:
                dominant_counts[dom] += 1
        dominant_overall = max(dominant_counts.keys(), key=lambda v: dominant_counts[v]) if dominant_counts else (
            max(var_totals.keys(), key=lambda v: var_totals[v]) if var_totals else None
        )
        result[action_id] = {
            "total_occurrences": len(items),
            "variables_affected_aggregate": dict(var_totals),
            "dominant_variable_overall": dominant_overall,
        }
    return result
