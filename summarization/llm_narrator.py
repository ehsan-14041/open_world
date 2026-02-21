"""
Optional LLM narrator (Layer 2). Receives only NarrativeFacts; no raw trace or state.
When allow_numbers=True, LLM must output placeholders only: {{PRE:var}}, {{POST:var}}, {{DELTA:var}}, {{EVENT:id}}.
Engine substitutes from snapshots; reject if digits pre-substitution or placeholders unresolved.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from summarization.validators import has_digits_pre_substitution, has_unresolved_placeholders


def build_llm_prompt(
    facts: Any,
    lang: str = "en",
    allow_numbers: bool = False,
) -> str:
    """
    Build domain-agnostic LLM prompt from NarrativeFacts only. No raw trace or state.
    When allow_numbers=True, instruct to use only placeholders {{PRE:var}}, {{POST:var}}, {{DELTA:var}}, {{EVENT:id}}.
    """
    if hasattr(facts, "to_dict"):
        d = facts.to_dict()
    else:
        d = dict(facts)
    lang = (lang or "en").strip().lower()
    lang_instruction = "Write in Persian." if lang == "fa" else "Write in English."
    if allow_numbers:
        number_instruction = (
            "Use only placeholders for numbers: {{PRE:var}}, {{POST:var}}, {{DELTA:var}}, {{EVENT:id}}. "
            "Do not output raw digits; the engine will substitute values."
        )
    else:
        number_instruction = "Do not include any digits or raw numbers. Use qualitative descriptions only."
    prompt = (
        f"{lang_instruction} Start from the beginning. {number_instruction} "
        "Write a coherent narrative in 2-3 short paragraphs. "
        "Include: (1) Initial situation and actors' goals. "
        "(2) One to three turning points, tradeoffs, and how the situation ended. "
        "Use cause-and-effect connectors. Do not invent facts beyond the provided data. "
        "Do not use phrases like 'Causal chain:', 'max_delta', 'Variable', or 'Turn N'.\n\n"
        "Structured data:\n" + json.dumps(d, default=str)
    )
    return prompt


def invoke_llm_narrator(
    facts: Any,
    llm_callback: Callable[[str, str | None], str],
    lang: str = "en",
    allow_numbers: bool = False,
) -> str:
    """
    Call LLM with NarrativeFacts-only prompt. Returns prose. Caller should validate
    and substitute placeholders when allow_numbers=True.
    """
    prompt = build_llm_prompt(facts, lang=lang, allow_numbers=allow_numbers)
    system = "You are a narrative writer. Output only the narrative prose, no headers or bullet lists."
    return llm_callback(prompt, system)


def reject_if_invalid_for_allow_numbers(prose: str, allow_numbers: bool) -> tuple[bool, str | None]:
    """
    When allow_numbers=True: reject if prose contains raw digits (pre-substitution)
    or unresolved placeholders. Returns (is_valid, reason).
    """
    if allow_numbers:
        if has_digits_pre_substitution(prose):
            return False, "digits_before_substitution"
        # After substitution, caller checks unresolved placeholders
    return True, None
