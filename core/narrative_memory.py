"""
Narrative memory: store structured narrative per turn and generate longitudinal story.
Updated each turn when narrative is generated; supports generate_longitudinal_story(last_n_turns).
"""

from __future__ import annotations

from typing import Any

from core.narrative_model import TurnNarrativeInputs

_narrative_history: list[dict[str, Any]] = []
_inputs_history: list[TurnNarrativeInputs] = []


def append_narrative(narrative: dict[str, Any], turn: int | None = None) -> None:
    """
    Append a structured narrative dict for this turn. Optionally set turn index.

    Phase 3: if the narrative dict contains a fact/tag representation (under
    the 'inputs' key), we also track it as TurnNarrativeInputs in a parallel
    history list for run-level renderers.
    """
    entry = dict(narrative)
    if turn is not None:
        entry["turn"] = turn
    _narrative_history.append(entry)
    raw_inputs = entry.get("inputs") or entry.get("turn_inputs")
    if isinstance(raw_inputs, dict):
        try:
            inputs = TurnNarrativeInputs.from_dict(raw_inputs)
            if turn is not None and inputs.turn is None:
                inputs.turn = turn
            _inputs_history.append(inputs)
        except Exception:
            # Narrative inputs are optional; failures here must not break the loop.
            return


def get_narrative_history() -> list[dict[str, Any]]:
    """Return the full narrative history (read-only copy of list; entries are refs)."""
    return list(_narrative_history)


def clear_narrative_history() -> None:
    """Clear stored narratives (e.g. for new run)."""
    _narrative_history.clear()
    _inputs_history.clear()


def get_turn_inputs_history() -> list[TurnNarrativeInputs]:
    """
    Return the per-turn narrative inputs history.
    This is primarily intended for run-level renderers and exports.
    """
    return list(_inputs_history)


def generate_longitudinal_story(last_n_turns: int = 5) -> str:
    """
    Synthesize 2–4 sentences from the last N turns' turn_summary and outcome_assessment.
    Variable-agnostic; reflects direction (stabilizing/escalatory) and regime transitions.
    """
    history = get_narrative_history()
    if not history or last_n_turns <= 0:
        return "No narrative history available."
    slice_ = history[-last_n_turns:]
    outcomes: list[str] = []
    regimes: list[str] = []
    directions: list[str] = []
    for i, entry in enumerate(slice_):
        if isinstance(entry, dict):
            oa = entry.get("outcome_assessment") or {}
            if isinstance(oa, dict):
                outcomes.append(oa.get("outcome") or "Mixed Outcome")
            regimes.append(entry.get("regime_commentary") or "")
            summary = entry.get("turn_summary") or ""
            if "Stabilizing" in summary:
                directions.append("stabilizing")
            elif "Escalatory" in summary:
                directions.append("escalatory")
            else:
                directions.append("mixed")
    num = len(slice_)
    if num == 0:
        return "No narrative history for the requested turns."
    stabil = sum(1 for d in directions if d == "stabilizing")
    escal = sum(1 for d in directions if d == "escalatory")
    if stabil > escal and stabil >= num // 2:
        trend = "stabilizing"
    elif escal > stabil and escal >= num // 2:
        trend = "escalatory"
    else:
        trend = "mixed"
    outcome_set = list(dict.fromkeys(outcomes))
    outcome_str = ", ".join(outcome_set[:3])
    regime_set = list(dict.fromkeys(r for r in regimes if r))
    regime_note = ""
    if len(regime_set) == 1 and regime_set[0]:
        regime_note = f" {regime_set[0]}"
    elif len(regime_set) > 1:
        regime_note = " Regime conditions varied over the period."
    sentences = [
        f"Over the last {num} turn(s), dynamics were predominantly {trend}.",
        f"Outcomes included: {outcome_str}.",
    ]
    if regime_note:
        sentences.append(regime_note.strip())
    return " ".join(sentences)
