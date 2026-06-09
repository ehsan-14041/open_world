"""
Compact turn-by-turn trace for operations-facing "what changed" panel.
"""

from __future__ import annotations

from typing import Any

from ui.ops_outcomes import humanize_var

try:
    from core.trace_compression import compress_trace_to_causal_chain
except Exception:
    def compress_trace_to_causal_chain(_trace: list) -> list:
        return []


def _key_deltas(entry: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    deltas: list[tuple[str, float]] = []
    for key in ("primary_delta", "applied_delta", "delta"):
        d = entry.get(key)
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, (int, float)) and abs(v) >= 0.01:
                    deltas.append((k, float(v)))
    # Also check post_state vs pre if available
    post = entry.get("post_state") or {}
    pre = entry.get("pre_state") or {}
    if isinstance(post, dict) and isinstance(pre, dict):
        pv = post.get("variables") or post.get("global_state") or post
        prev = pre.get("variables") or pre.get("global_state") or pre
        if isinstance(pv, dict) and isinstance(prev, dict):
            for k in set(pv) | set(prev):
                a, b = pv.get(k), prev.get(k)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    diff = float(a) - float(b)
                    if abs(diff) >= 0.01:
                        deltas.append((k, diff))
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for name, val in sorted(deltas, key=lambda x: abs(x[1]), reverse=True):
        if name in seen:
            continue
        seen.add(name)
        out.append({
            "variable": name,
            "label": humanize_var(name),
            "delta": round(val, 2),
            "direction": "up" if val > 0 else "down",
        })
        if len(out) >= limit:
            break
    return out


def _narrative_summary(entry: dict[str, Any]) -> str:
    narrative = entry.get("narrative") or {}
    if isinstance(narrative, dict):
        for key in ("summary", "outcome_summary", "headline"):
            val = narrative.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:300]
        tags = narrative.get("tags") or []
        for tag in tags:
            if isinstance(tag, dict) and tag.get("kind") == "outcome":
                return str(tag.get("value") or "")[:300]
    return ""


def build_turn_trace(
    provenance: list[dict[str, Any]],
    scenario: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build a compact per-turn trace for the UI."""
    trace: list[dict[str, Any]] = []
    for entry in provenance or []:
        if not isinstance(entry, dict):
            continue
        turn = entry.get("turn") or len(trace) + 1
        propagation = entry.get("propagation_trace") or []
        chain = compress_trace_to_causal_chain(propagation) if propagation else []
        chain_str = " → ".join(
            f"{humanize_var(c.get('from', c.get('source', '')))}"
            for c in chain[:4]
            if isinstance(c, dict)
        ) if chain else ""

        events: list[str] = []
        for key in ("triggered_rules", "triggered_events", "events_fired"):
            val = entry.get(key)
            if isinstance(val, list):
                events.extend(str(x) for x in val[:3])

        action = entry.get("selected_action") or entry.get("action") or entry.get("action_type") or ""
        summary = _narrative_summary(entry)
        if not summary and action:
            summary = f"Action: {action}"

        trace.append({
            "turn": turn,
            "summary": summary,
            "action": str(action)[:120] if action else "",
            "key_changes": _key_deltas(entry),
            "causal_chain": chain_str,
            "events": events[:3],
        })
    return trace
