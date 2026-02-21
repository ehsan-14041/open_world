"""
Deterministic narrative renderer (Layer 2). Consumes NarrativeFacts only.
Output: 2-3 short paragraphs; no digits when allow_numbers=False; no banned artifacts.
First sentence MUST start with the opening phrase from lang.py.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from summarization.lang import opening_phrase
from summarization.validators import BANNED_ARTIFACTS

if TYPE_CHECKING:
    from summarization.facts import NarrativeFacts


def _strip_digits(text: str) -> str:
    """Remove Western digits from text."""
    if not text:
        return text
    return re.sub(r"\s+", " ", re.sub(r"-?\d+\.?\d*", "", text)).strip()


def render_narrative(
    facts: NarrativeFacts | dict[str, Any],
    lang: str = "en",
    allow_numbers: bool = False,
) -> str:
    """
    Produce 2-3 short paragraphs from NarrativeFacts. No digits when allow_numbers=False.
    No lists, no "Causal chain:", "max_delta", "Variable", "Turn". First sentence starts with opening phrase.
    """
    lang = (lang or "en").strip().lower()
    prefix = opening_phrase(lang)
    if hasattr(facts, "to_dict"):
        d = facts.to_dict()
    else:
        d = dict(facts)
    opening_context = d.get("opening_context") or []
    key_actors = d.get("key_actors") or []
    turning_points = d.get("turning_points") or []
    tradeoff = d.get("tradeoff") or {}
    ending_state = d.get("ending_state") or []

    if lang == "fa":
        return _render_fa(
            prefix, opening_context, key_actors, turning_points, tradeoff, ending_state, allow_numbers
        )
    return _render_en(
        prefix, opening_context, key_actors, turning_points, tradeoff, ending_state, allow_numbers
    )


def _render_en(
    prefix: str,
    opening_context: list[str],
    key_actors: list[Any],
    turning_points: list[str],
    tradeoff: dict[str, str],
    ending_state: list[str],
    allow_numbers: bool,
) -> str:
    parts_p1: list[str] = []
    first = prefix
    if opening_context:
        rest = " ".join(opening_context[:3])
        if not allow_numbers:
            rest = _strip_digits(rest)
        first = f"{prefix}, {rest[0].lower()}{rest[1:]}" if len(rest) > 1 else f"{prefix}, {rest}."
    else:
        first = f"{prefix}, the situation was shaped by key factors."
    parts_p1.append(first)
    if key_actors:
        actor_phrase = " and ".join(
            f"{a.get('id', 'Actor')} sought to {a.get('intent', 'act')}" for a in key_actors[:3]
        )
        if not allow_numbers:
            actor_phrase = _strip_digits(actor_phrase)
        parts_p1.append(actor_phrase + ".")
    para1 = " ".join(parts_p1).strip()
    if not allow_numbers:
        para1 = _strip_digits(para1)

    parts_p2: list[str] = []
    if turning_points:
        parts_p2.append(" ".join(turning_points[:2]) + ".")
    if tradeoff:
        imp = tradeoff.get("improvement", "")
        dec = tradeoff.get("decline", "")
        if imp and dec:
            if not allow_numbers:
                imp, dec = _strip_digits(imp), _strip_digits(dec)
            parts_p2.append(f"As a result, {imp} Meanwhile, {dec}")
    if ending_state:
        parts_p2.append(" ".join(ending_state[:2]) + ".")
    para2 = " ".join(parts_p2).strip()
    if not allow_numbers:
        para2 = _strip_digits(para2)

    if not para2:
        para2 = "In the course of the run, changes and final outcomes took shape."
    out = (para1 + "\n\n" + para2).strip()
    for banned in BANNED_ARTIFACTS:
        if banned in out:
            out = out.replace(banned, "")
    out = re.sub(r"\n\n+", "\n\n", out).strip()
    return out


def _render_fa(
    prefix: str,
    opening_context: list[str],
    key_actors: list[Any],
    turning_points: list[str],
    tradeoff: dict[str, str],
    ending_state: list[str],
    allow_numbers: bool,
) -> str:
    parts_p1: list[str] = []
    first = prefix
    if opening_context:
        rest = " ".join(opening_context[:3])
        if not allow_numbers:
            rest = _strip_digits(rest)
        first = f"{prefix}، {rest}"
    else:
        first = f"{prefix}، وضعیت با عوامل کلیدی شکل گرفت."
    parts_p1.append(first)
    if key_actors:
        actor_phrase = " و ".join(
            f"{a.get('id', 'کنشگر')} برای {a.get('intent', 'عمل')} تلاش کرد" for a in key_actors[:3]
        )
        if not allow_numbers:
            actor_phrase = _strip_digits(actor_phrase)
        parts_p1.append(actor_phrase + ".")
    para1 = " ".join(parts_p1).strip()
    if not allow_numbers:
        para1 = _strip_digits(para1)

    parts_p2: list[str] = []
    if turning_points:
        parts_p2.append(" ".join(turning_points[:2]) + ".")
    if tradeoff:
        imp = tradeoff.get("improvement", "")
        dec = tradeoff.get("decline", "")
        if imp and dec:
            if not allow_numbers:
                imp, dec = _strip_digits(imp), _strip_digits(dec)
            parts_p2.append(f"در نتیجه، {imp} در عوض، {dec}")
    if ending_state:
        parts_p2.append(" ".join(ending_state[:2]) + ".")
    para2 = " ".join(parts_p2).strip()
    if not allow_numbers:
        para2 = _strip_digits(para2)

    if not para2:
        para2 = "در ادامه، تغییرات و نتایج نهایی رخ داد."
    out = (para1 + "\n\n" + para2).strip()
    for banned in BANNED_ARTIFACTS:
        if banned in out:
            out = out.replace(banned, "")
    out = re.sub(r"\n\n+", "\n\n", out).strip()
    return out
