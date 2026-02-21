"""
Narrative validators: digit ban, banned artifacts, opening prefix.
Retry once on failure; then caller falls back to deterministic renderer.
"""

from __future__ import annotations

import re
from typing import Any

from summarization.lang import opening_phrase

# Tokens/phrases that must not appear in narrative output
BANNED_ARTIFACTS = (
    "Causal chain:",
    "max_delta",
    "Variable ",
    "Turn ",
)

# Pattern to detect digits in text
DIGIT_PATTERN = re.compile(r"[0-9]")


def validate_narrative(
    prose: str,
    lang: str = "en",
    allow_numbers: bool = False,
) -> tuple[bool, str | None]:
    """
    Validate narrative output. Returns (passed, reason).
    (1) If allow_numbers=False: reject if any digit appears.
    (2) Reject if any banned artifact appears.
    (3) Reject if first sentence does not start with required opening phrase.
    """
    if not prose or not isinstance(prose, str):
        return False, "empty"

    # Digits when not allowed
    if not allow_numbers and DIGIT_PATTERN.search(prose):
        return False, "digits_not_allowed"

    # Banned artifacts
    for banned in BANNED_ARTIFACTS:
        if banned in prose:
            return False, f"banned_artifact:{banned!r}"

    # First sentence must start with opening phrase
    prefix = opening_phrase(lang)
    first_sentence = prose.split("\n")[0].strip()
    if not first_sentence.startswith(prefix):
        return False, f"wrong_prefix: expected {prefix!r}"

    return True, None


def has_unresolved_placeholders(prose: str) -> bool:
    """Return True if prose contains {{PRE:...}}, {{POST:...}}, {{DELTA:...}}, {{EVENT:...}} still present."""
    return bool(
        re.search(r"\{\{(?:PRE|POST|DELTA|EVENT)(?::[^}]*)?\}\}", prose, re.IGNORECASE)
    )


def has_digits_pre_substitution(prose: str) -> bool:
    """Return True if prose contains digits (for allow_numbers=True path: LLM must not output raw digits)."""
    return bool(DIGIT_PATTERN.search(prose))
