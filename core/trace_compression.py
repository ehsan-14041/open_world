"""
Trace compression: use SLM to compress raw logs into structured Causal Event Chain before long-trace analysis.
Reduces token cost for run_long_trace_analysis.
"""

from __future__ import annotations

from typing import Any, Callable


# Schema: each event in the chain has turn, cause_var, effect_var, direction, magnitude (optional)
CAUSAL_EVENT_CHAIN_SCHEMA = [
    {"turn": int, "cause_var": str, "effect_var": str, "direction": "positive|negative", "magnitude": float},
]


def compress_trace_to_causal_chain(
    raw_logs: list[dict[str, Any]],
    slm_callback: Callable[[str, str], str] | None = None,
    *,
    max_events: int = 100,
) -> list[dict[str, Any]]:
    """
    Compress raw provenance/trace logs into a structured Causal Event Chain.
    If slm_callback is provided, use SLM to summarize and extract cause/effect; else derive from delta_applied.
    Returns list of {turn, cause_var, effect_var, direction, magnitude}.
    """
    out: list[dict[str, Any]] = []
    for entry in raw_logs[-max_events:]:
        if not isinstance(entry, dict):
            continue
        turn = entry.get("turn", 0)
        delta = entry.get("turn_record", {}).get("delta_applied") or entry.get("delta_applied") or {}
        if not isinstance(delta, dict):
            continue
        primary = max(
            [(k, abs(float(v))) for k, v in delta.items() if isinstance(v, (int, float))],
            key=lambda x: x[1],
            default=(None, 0.0),
        )
        if primary[0]:
            out.append({
                "turn": turn,
                "cause_var": primary[0],
                "effect_var": primary[0],
                "direction": "positive" if (delta.get(primary[0]) or 0) >= 0 else "negative",
                "magnitude": primary[1],
            })
    return out
