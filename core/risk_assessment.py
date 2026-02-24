"""
Enhanced risk assessment: agent-behavior summary, scenario prediction, optional lightweight MC tail risk.
"""

from __future__ import annotations

import math
from typing import Any


def agent_behavior_summary(
    provenance_history: list[dict[str, Any]],
    agents_list: list[dict[str, Any]],
    last_n_turns: int = 5,
) -> dict[str, Any]:
    """Per-agent summary: recent action streak, variance of chosen actions."""
    per_agent: dict[str, Any] = {}
    for ag in agents_list or []:
        name = ag.get("name") if isinstance(ag, dict) else None
        if not name:
            continue
        per_agent[name] = {"recent_actions": [], "action_variance": 0.0}

    recent = (provenance_history or [])[-last_n_turns:]
    action_counts: dict[str, dict[str, int]] = {}
    for entry in recent:
        chosen = (entry.get("turn_record") or {}).get("chosen_actions") or []
        for c in chosen:
            if not isinstance(c, dict):
                continue
            agent = c.get("agent", "")
            action_id = c.get("action_id") or c.get("action", "")
            if agent and agent in per_agent:
                per_agent[agent]["recent_actions"].append(action_id)
                if agent not in action_counts:
                    action_counts[agent] = {}
                action_counts[agent][action_id] = action_counts[agent].get(action_id, 0) + 1

    for agent, counts in action_counts.items():
        if agent not in per_agent:
            continue
        vals = list(counts.values())
        if len(vals) >= 2:
            mean = sum(vals) / len(vals)
            variance = sum((x - mean) ** 2 for x in vals) / len(vals)
            per_agent[agent]["action_variance"] = round(math.sqrt(variance), 3)
        per_agent[agent]["recent_actions"] = per_agent[agent]["recent_actions"][-5:]

    agent_volatility = 0.0
    if per_agent:
        variances = [p.get("action_variance", 0) for p in per_agent.values()]
        agent_volatility = round(sum(variances) / len(variances), 3)

    return {"per_agent": per_agent, "agent_volatility": agent_volatility}


def next_turn_risk_score(
    snapshot: dict[str, Any],
    provenance_entry: dict[str, Any] | None,
    scenario: dict[str, Any],
) -> float:
    """Simple next-turn risk from distance to stability threshold (0-100)."""
    if not provenance_entry:
        return 0.0
    derived = (snapshot or {}).get("derived") or {}
    stability = float(derived.get("system_stability", 70.0))
    dissatisfaction = float(derived.get("dissatisfaction", 30.0))
    risk = 0.0
    if stability < 50:
        risk += (50 - stability) * 0.5
    if dissatisfaction > 60:
        risk += min(40, (dissatisfaction - 60) * 0.5)
    return min(100.0, risk)


def tail_risk_from_mc(
    snapshot: dict[str, Any],
    provenance_history: list[dict[str, Any]],
    causal_links: list[dict[str, Any]],
    n_sims: int = 3,
    key_vars: int = 5,
) -> dict[str, Any]:
    """Lightweight MC: run n_sims steps with last-observed deltas; return max deviation over key vars."""
    variables = (snapshot or {}).get("variables") or (snapshot or {}).get("global_state") or {}
    if not isinstance(variables, dict):
        return {"max_deviation": 0.0, "trajectories": {}}
    var_names = [k for k, v in variables.items() if isinstance(v, (int, float))][:key_vars]
    if not var_names:
        return {"max_deviation": 0.0, "trajectories": {}}
    recent = (provenance_history or [])[-5:]
    delta_avg: dict[str, float] = {v: 0.0 for v in var_names}
    count = 0
    for entry in recent:
        applied = (entry.get("turn_record") or {}).get("delta_applied") or {}
        if isinstance(applied, dict):
            for v in var_names:
                if v in applied and isinstance(applied[v], (int, float)):
                    delta_avg[v] += applied[v]
            count += 1
    if count > 0:
        for v in var_names:
            delta_avg[v] /= count
    trajectories: dict[str, list[float]] = {v: [] for v in var_names}
    for _ in range(n_sims):
        state = {v: float(variables.get(v, 0)) for v in var_names}
        for _step in range(3):
            for v in var_names:
                state[v] = state[v] + delta_avg.get(v, 0)
            for v in var_names:
                trajectories[v].append(state[v])
    max_deviation = 0.0
    for v in var_names:
        vals = trajectories[v]
        if vals:
            initial = float(variables.get(v, 0))
            dev = max(abs(x - initial) for x in vals) if initial == initial else 0.0
            max_deviation = max(max_deviation, dev)
    return {
        "max_deviation": round(max_deviation, 3),
        "trajectories": {k: [round(x, 3) for x in v[:10]] for k, v in trajectories.items()},
    }


def enrich_risk_report(
    risk_report: dict[str, Any],
    provenance_history: list[dict[str, Any]],
    agents_list: list[dict[str, Any]],
    snapshot: dict[str, Any],
    provenance_entry: dict[str, Any] | None,
    scenario: dict[str, Any],
    include_mc_tail: bool = False,
) -> dict[str, Any]:
    """Add agent_volatility and optional next_turn_risk, tail_risk_from_mc to risk_report."""
    out = dict(risk_report)
    breakdown = dict(out.get("breakdown") or {})
    behavior = agent_behavior_summary(provenance_history, agents_list)
    breakdown["agent_volatility"] = round(behavior.get("agent_volatility", 0), 1)
    out["breakdown"] = breakdown
    out["agent_behavior"] = behavior.get("per_agent", {})
    next_risk = next_turn_risk_score(snapshot, provenance_entry, scenario)
    if next_risk > 0:
        breakdown["next_turn_risk"] = round(next_risk, 1)
    if include_mc_tail:
        try:
            from config.settings import MC_N_SIMS, MC_KEY_VARS
            mc = tail_risk_from_mc(
                snapshot, provenance_history,
                scenario.get("causal_links") or [],
                n_sims=min(3, MC_N_SIMS),
                key_vars=MC_KEY_VARS,
            )
            breakdown["tail_risk_from_mc"] = mc.get("max_deviation", 0)
            out["tail_risk_mc"] = mc
        except Exception:
            pass
    return out
