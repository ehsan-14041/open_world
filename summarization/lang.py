"""
Language detection and opening phrase for narrative (presentation only).
Does not affect engine semantics: variable discovery, actions, governance, propagation, etc.
"""

from __future__ import annotations

from typing import Any


def detect_narrative_language_from_scenario(scenario: dict[str, Any] | None) -> str:
    """
    Detect narrative language from scenario text/description. Returns 'fa' or 'en'.
    Presentation-only; used only for narrative opening phrase and prose language.
    """
    if not scenario:
        return "en"
    text = (
        str(scenario.get("description") or "")
        + " "
        + str(scenario.get("scenario_text") or "")
        + " "
        + str(scenario.get("narrative") or "")
        + " "
        + str(scenario.get("name") or "")
    )
    if any("\u0600" <= c <= "\u06FF" for c in text):
        return "fa"
    if scenario.get("language") == "fa":
        return "fa"
    return "en"


def opening_phrase(lang: str) -> str:
    """
    Return the required first-sentence prefix for the narrative.
    fa -> "در آغاز"; en -> "At the beginning"; other -> "At the beginning".
    """
    lang = (lang or "").strip().lower()
    if lang == "fa":
        return "در آغاز"
    return "At the beginning"
