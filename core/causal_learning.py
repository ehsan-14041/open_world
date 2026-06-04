"""
Oracle-driven causal learning: suggest LocalCausalLink updates from recurring patterns.
Belief graph edge confidence increases gradually; BELIEF_DRIFT_RATE governs learning speed.
"""

from __future__ import annotations

from typing import Any


def suggest_causal_link_from_trace(
    provenance_history: list[dict[str, Any]],
    *,
    min_occurrences: int = 2,
) -> dict[str, Any] | None:
    """
    If a recurring pattern is detected (same source->target delta pattern), return a causal suggestion.
    Returns {source, target, polarity, strength_estimate} or None.
    """
    if not provenance_history or len(provenance_history) < min_occurrences:
        return None
    # Stub: aggregate variable_changes/delta_applied and look for repeated (var_a, var_b) co-changes
    seen: dict[tuple[str, str], int] = {}
    for entry in provenance_history[-20:]:
        delta = entry.get("turn_record", {}).get("delta_applied") or entry.get("delta_applied") or {}
        if not isinstance(delta, dict):
            continue
        vars_changed = [k for k, v in delta.items() if isinstance(v, (int, float)) and abs(float(v)) > 1e-6]
        for i, a in enumerate(vars_changed):
            for b in vars_changed[i + 1 :]:
                key = (min(a, b), max(a, b))
                seen[key] = seen.get(key, 0) + 1
    for (source, target), count in seen.items():
        if count >= min_occurrences:
            return {
                "source": source,
                "target": target,
                "polarity": "positive",
                "strength_estimate": 0.5,
            }
    return None


def apply_belief_drift(edge_confidence: dict[tuple[str, str], float], suggestion: dict[str, Any], rate: float) -> None:
    """Increase edge confidence for the suggested link by rate (BELIEF_DRIFT_RATE). Mutates edge_confidence."""
    key = (suggestion.get("source"), suggestion.get("target"))
    if not key[0] or not key[1]:
        return
    edge_confidence[key] = min(1.0, edge_confidence.get(key, 0.0) + rate)
