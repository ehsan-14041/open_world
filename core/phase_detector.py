"""
Phase detection and importance scoring for simulation summary.
Deterministic: magnitude of delta_applied, threshold crossings, events, propagation depth.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

try:
    from config.settings import PHASE_TOP_K_TURNS
except ImportError:
    PHASE_TOP_K_TURNS = 3


def importance_score_per_turn(
    turn_record: dict[str, Any],
) -> float:
    """
    Deterministic importance score: magnitude of delta_applied, events count, propagation depth.
    """
    score = 0.0
    delta_applied = turn_record.get("delta_applied") or {}
    if isinstance(delta_applied, dict):
        score += sum(abs(v) for v in delta_applied.values() if isinstance(v, (int, float)))
    events = turn_record.get("events_fired") or []
    score += len(events) * 10.0
    rules = turn_record.get("rules_fired") or []
    score += len(rules) * 5.0
    prop_trace = turn_record.get("propagation_trace") or []
    if prop_trace:
        iters = set(t.get("iter", 0) for t in prop_trace if isinstance(t, dict))
        score += len(iters) * 2.0
    return score


def detect_phases(
    turn_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Phase detection: rolling dominant strategy, variable regime shifts.
    Returns list of phases with {start_turn, end_turn, dominant_strategy, top_turns}.
    """
    if not turn_records:
        return []

    phases: list[dict[str, Any]] = []
    strategy_counts: Counter[str] = Counter()
    window = 3
    i = 0
    while i < len(turn_records):
        chunk = turn_records[i : i + window]
        for tr in chunk:
            for ca in tr.get("chosen_actions") or []:
                strat = ca.get("strategy_class", "general") if isinstance(ca, dict) else "general"
                strategy_counts[strat] += 1
        dominant = strategy_counts.most_common(1)[0][0] if strategy_counts else "general"
        top_turns = sorted(
            range(i, min(i + window, len(turn_records))),
            key=lambda j: importance_score_per_turn(turn_records[j]),
            reverse=True,
        )[: PHASE_TOP_K_TURNS]
        phases.append({
            "start_turn": i + 1,
            "end_turn": min(i + window, len(turn_records)),
            "dominant_strategy": dominant,
            "top_turns": [j + 1 for j in top_turns],
        })
        strategy_counts.clear()
        i += window
    return phases


def build_phase_summary_facts(
    turn_records: list[dict[str, Any]],
    phases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Build fact bullets with placeholders for each phase's top-k turns.
    Returns list of {fact, turn_record} for placeholder replacement.
    """
    result: list[dict[str, Any]] = []
    for phase in phases:
        for t in phase.get("top_turns", []):
            idx = t - 1
            if 0 <= idx < len(turn_records):
                tr = turn_records[idx]
                chosen = tr.get("chosen_actions") or []
                events = tr.get("events_fired") or []
                delta_applied = tr.get("delta_applied") or {}
                parts = [f"Turn {{{{TURN:{t}}}}}"]
                for ca in chosen[:1]:
                    if isinstance(ca, dict):
                        agent = ca.get("agent", "?")
                        action = ca.get("action_id", "?")
                        parts.append(f"{{{{AGENT:{agent}}}}} chose {{{{ACTION:{action}}}}}")
                if isinstance(delta_applied, dict) and delta_applied:
                    var = next(iter(delta_applied.keys()), "?")
                    d = delta_applied.get(var, 0)
                    parts.append(f"causing {{{{DELTA:{var}:{d}}}}} on {{{{var:{var}}}}}")
                if events:
                    ev = events[0] if events else {}
                    ename = ev.get("event_type", "?") if isinstance(ev, dict) else "?"
                    parts.append(f"triggering {{{{EVENT:{ename}}}}}")
                result.append({"fact": ". ".join(parts) + ".", "turn_record": tr})
    return result
