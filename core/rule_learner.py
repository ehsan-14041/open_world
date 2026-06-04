"""
Offline rule learner: suggest governance rule changes or strictness from historical (delta, outcome) runs.
Output is candidate updates for human review or config deploy; no automatic application.
"""

from __future__ import annotations

from typing import Any


def suggest_rule_updates(
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Input: list of { "delta": delta_dict, "world_snapshot": dict, "outcome": dict, "accepted": bool, "ssi": float }.
    Output: { "suggest_strictness_level": int | None, "suggested_rules": [...], "reason": str }.
    suggested_rules are candidate scenario rules (condition_key, effect_key, params) for human review.
    """
    if not history:
        return {"suggest_strictness_level": None, "suggested_rules": [], "reason": "No history"}

    rejected_count = sum(1 for h in history if h.get("accepted") is False)
    repair_count = sum(1 for h in history if (h.get("outcome") or {}).get("repaired"))
    n = len(history)
    ssi_values = [h.get("ssi") for h in history if isinstance(h.get("ssi"), (int, float))]
    low_ssi_count = sum(1 for s in ssi_values if s is not None and float(s) < 0.05)

    suggest_strictness = None
    reason_parts = []
    suggested_rules: list[dict[str, Any]] = []

    if n >= 5 and rejected_count / n > 0.2:
        suggest_strictness = 2
        reason_parts.append(f"High rejection rate ({rejected_count}/{n}); consider strictness 2")
    elif repair_count / max(1, n) > 0.5:
        suggest_strictness = 1
        reason_parts.append(f"Frequent auto-repairs ({repair_count}/{n}); strictness 1 may help")

    if ssi_values and low_ssi_count / len(ssi_values) > 0.3:
        suggested_rules.append({
            "id": "learned_stability_guard",
            "name": "stability_guard",
            "condition_key": "ssi_low",
            "effect_key": "apply_soft_constraint",
            "params": {"max_delta_scale": 0.8},
        })
        reason_parts.append("Low SSI in >30% of turns; consider adding stability_guard rule (register condition_key 'ssi_low' and effect_key 'apply_soft_constraint').")

    return {
        "suggest_strictness_level": suggest_strictness,
        "suggested_rules": suggested_rules,
        "reason": " ".join(reason_parts) if reason_parts else "No change suggested",
    }
