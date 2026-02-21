"""
Narrative token substitution, lang auto-detect, facts, renderer, validators, llm_narrator.
"""

from summarization.bucketing import bucket_numeric_to_ordinal, humanize_var_id
from summarization.facts import NarrativeFacts, build_narrative_facts
from summarization.lang import detect_narrative_language_from_scenario, opening_phrase
from summarization.narrative import detect_lang_from_scenario, substitute_narrative_tokens
from summarization.renderer import render_narrative
from summarization.validators import BANNED_ARTIFACTS, validate_narrative

__all__ = [
    "BANNED_ARTIFACTS",
    "NarrativeFacts",
    "bucket_numeric_to_ordinal",
    "build_narrative_facts",
    "detect_lang_from_scenario",
    "detect_narrative_language_from_scenario",
    "humanize_var_id",
    "opening_phrase",
    "render_narrative",
    "substitute_narrative_tokens",
    "validate_narrative",
]
