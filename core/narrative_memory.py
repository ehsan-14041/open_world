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


def _direction_from_entry(entry: dict) -> str:
    """Read canonical direction from the stored narrative tags (language-agnostic)."""
    for tag in entry.get("tags") or []:
        if isinstance(tag, dict) and tag.get("kind") == "direction":
            v = str(tag.get("value") or "").strip().lower()
            if v.startswith("stabil"):
                return "stabilizing"
            if v.startswith("escal"):
                return "escalatory"
            return "mixed"
    return "mixed"


def generate_longitudinal_story(last_n_turns: int = 5, lang: str = "en") -> str:
    """
    Synthesize 2–4 sentences from the last N turns' turn_summary and outcome_assessment.
    Variable-agnostic; reflects direction (stabilizing/escalatory) and regime transitions.
    Localized to Persian when lang='fa'.
    """
    from core.narrative_engine import outcome_label_display

    fa = str(lang or "").strip().lower().startswith("fa")
    history = get_narrative_history()
    if not history or last_n_turns <= 0:
        return "تاریخچه‌ی روایت موجود نیست." if fa else "No narrative history available."
    slice_ = history[-last_n_turns:]
    outcomes: list[str] = []
    regimes: list[str] = []
    directions: list[str] = []
    for i, entry in enumerate(slice_):
        if isinstance(entry, dict):
            oa = entry.get("outcome_assessment") or {}
            if isinstance(oa, dict):
                outcomes.append(outcome_label_display(oa.get("outcome") or "Mixed Outcome", lang))
            regimes.append(entry.get("regime_commentary") or "")
            directions.append(_direction_from_entry(entry))
    num = len(slice_)
    if num == 0:
        return "تاریخچه‌ای برای نوبت‌های خواسته‌شده نیست." if fa else "No narrative history for the requested turns."
    stabil = sum(1 for d in directions if d == "stabilizing")
    escal = sum(1 for d in directions if d == "escalatory")
    if stabil > escal and stabil >= num // 2:
        trend = "تثبیت‌کننده" if fa else "stabilizing"
    elif escal > stabil and escal >= num // 2:
        trend = "تشدیدکننده" if fa else "escalatory"
    else:
        trend = "مختلط" if fa else "mixed"
    outcome_set = list(dict.fromkeys(outcomes))
    outcome_str = "، ".join(outcome_set[:3]) if fa else ", ".join(outcome_set[:3])
    regime_set = list(dict.fromkeys(r for r in regimes if r))
    regime_note = ""
    if len(regime_set) == 1 and regime_set[0]:
        regime_note = f" {regime_set[0]}"
    elif len(regime_set) > 1:
        regime_note = " شرایطِ رژیم در این دوره متغیر بود." if fa else " Regime conditions varied over the period."
    if fa:
        sentences = [
            f"در {num} نوبتِ اخیر، دینامیک عمدتاً {trend} بود.",
            f"نتایج شامل: {outcome_str}.",
        ]
    else:
        sentences = [
            f"Over the last {num} turn(s), dynamics were predominantly {trend}.",
            f"Outcomes included: {outcome_str}.",
        ]
    if regime_note:
        sentences.append(regime_note.strip())
    return " ".join(sentences)
