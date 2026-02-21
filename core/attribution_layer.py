"""
Attribution layer: produce human-readable sentences stating which action led to which variable change.
Uses turn_record data: chosen_actions, delta_applied, self_effect_per_agent.
"""

from __future__ import annotations

from typing import Any


def _humanize_var(var: str) -> str:
    return (var or "").replace("_", " ").strip() or "variable"


def build_attribution_sentences(
    provenance: list[dict[str, Any]],
    *,
    allow_numbers: bool = True,
    max_sentences: int = 50,
) -> list[str]:
    """
    Build a list of attribution sentences from provenance (turn_record per entry).
    Each sentence: "The change in X by Δ is directly attributed to action A by agent Z."
    or "Part of the change in X is attributed to Z (action A), part to W (action B)."
    """
    sentences: list[str] = []
    seen: set[tuple[int, str, str, str]] = set()  # (turn, var, agent, action_id) to dedupe

    for entry in provenance:
        tr = entry.get("turn_record")
        if not isinstance(tr, dict):
            continue
        turn = tr.get("turn") or entry.get("turn")
        delta_applied = tr.get("delta_applied") or {}
        self_effect = tr.get("self_effect_per_agent") or {}
        chosen = tr.get("chosen_actions") or []

        if not isinstance(delta_applied, dict):
            continue

        # Map agent -> action_id for this turn
        agent_to_action: dict[str, str] = {}
        for c in chosen:
            if isinstance(c, dict):
                agent_to_action[c.get("agent", "") or ""] = (c.get("action_id") or c.get("action") or "unknown")

        for var, applied_delta in delta_applied.items():
            if not isinstance(applied_delta, (int, float)) or abs(float(applied_delta)) < 1e-9:
                continue
            var_label = _humanize_var(var)
            delta_val = float(applied_delta)
            direction = "increase" if delta_val > 0 else "decrease"
            contributors: list[tuple[str, str, float]] = []  # (agent, action_id, share)
            for agent, agent_effect in self_effect.items():
                if not isinstance(agent_effect, dict):
                    continue
                val = agent_effect.get(var)
                if isinstance(val, (int, float)) and abs(val) > 1e-9:
                    action_id = agent_to_action.get(agent, "unknown")
                    contributors.append((agent, action_id, float(val)))

            if not contributors:
                if allow_numbers:
                    sentences.append(
                        f"The {direction} in {var_label} by {abs(delta_val):.1f} is attributed to system or propagation (turn {turn})."
                    )
                else:
                    sentences.append(
                        f"The {direction} in {var_label} is attributed to system or propagation."
                    )
                if len(sentences) >= max_sentences:
                    return sentences
                continue

            # Dedupe by (turn, var, first agent, first action)
            key = (turn, var, contributors[0][0], contributors[0][1])
            if key in seen:
                continue
            seen.add(key)

            if len(contributors) == 1:
                agent, action_id, _ = contributors[0]
                if allow_numbers:
                    sentences.append(
                        f"The {direction} in {var_label} by {abs(delta_val):.1f} is directly attributed to action {action_id} by {agent}."
                    )
                else:
                    sentences.append(
                        f"The {direction} in {var_label} is directly attributed to action {action_id} by {agent}."
                    )
            else:
                parts = [f"{ag} (action {act})" for ag, act, _ in contributors[:3]]
                if allow_numbers:
                    sentences.append(
                        f"Part of the change in {var_label} ({abs(delta_val):.1f}) is attributed to {', '.join(parts)}."
                    )
                else:
                    sentences.append(
                        f"Part of the change in {var_label} is attributed to {', '.join(parts)}."
                    )

            if len(sentences) >= max_sentences:
                return sentences

    return sentences
