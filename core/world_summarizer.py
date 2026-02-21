"""
World summarizer: convert full JSON world state into a compact textual description.
Agents receive only this summary text, not raw JSON. Token-efficient, deterministic.
Supports qualitative Persian "World Brief" with no raw numbers when allow_numbers=False.
"""

from __future__ import annotations

import re
from typing import Any

# Optional max length for the summary (chars). None = no hard cap.
DEFAULT_MAX_SUMMARY_LENGTH = 1200

# Persian level labels (ratio-like 0..1)
FA_RATIO_LOWEST = "خیلی کم"
FA_RATIO_LOW = "کم"
FA_RATIO_MID = "متوسط"
FA_RATIO_HIGH = "زیاد"
FA_RATIO_HIGHEST = "خیلی زیاد"

# Unbounded scale
FA_LEVEL_VERY_LOW = "بسیار پایین"
FA_LEVEL_LOW = "پایین"
FA_LEVEL_MID = "متوسط"
FA_LEVEL_HIGH = "بالا"
FA_LEVEL_VERY_HIGH = "بسیار بالا"

# Trend (direction)
FA_TREND_UP = "رو به بهبود"
FA_TREND_DOWN = "رو به افت"
FA_TREND_STABLE = "تقریباً ثابت"

# English level labels (same structure as Persian)
EN_RATIO_LOWEST = "very low"
EN_RATIO_LOW = "low"
EN_RATIO_MID = "moderate"
EN_RATIO_HIGH = "high"
EN_RATIO_HIGHEST = "very high"
EN_LEVEL_VERY_LOW = "very low"
EN_LEVEL_LOW = "low"
EN_LEVEL_MID = "moderate"
EN_LEVEL_HIGH = "high"
EN_LEVEL_VERY_HIGH = "very high"
EN_TREND_UP = "improving"
EN_TREND_DOWN = "declining"
EN_TREND_STABLE = "roughly stable"


def detect_language(text: str) -> str:
    """Detect language from text. Returns 'fa' if any Persian/Arabic character in \\u0600-\\u06FF, else 'en'."""
    if not text:
        return "en"
    for c in text:
        if "\u0600" <= c <= "\u06FF":
            return "fa"
    return "en"


def strip_digits(text: str, allow_numbers: bool) -> str:
    """Remove Western digits and float patterns when allow_numbers is False; leave unchanged when True."""
    if allow_numbers or not text:
        return text
    # Remove standalone numbers and floats (preserve letters and spaces)
    out = re.sub(r"-?\d+\.?\d*", "", text)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def bucket_numeric(
    value: float,
    spec: dict[str, Any] | None,
    history: list[float] | None = None,
    lang: str = "fa",
) -> tuple[str, str]:
    """
    Bucket a numeric value into (level_label, trend_label). spec may have min, max, units.
    Returns labels in the requested language: lang='fa' (Persian) or 'en' (English).
    """
    fa = lang == "fa"
    trend_label = FA_TREND_STABLE if fa else EN_TREND_STABLE
    level_label: str

    vmin = spec.get("min") if spec else None
    vmax = spec.get("max") if spec else None
    if spec and "range" in spec:
        r = spec["range"]
        if isinstance(r, (list, tuple)) and len(r) >= 2:
            vmin, vmax = float(r[0]), float(r[1])

    try:
        val = float(value)
    except (TypeError, ValueError):
        return (FA_LEVEL_MID if fa else EN_LEVEL_MID), trend_label

    if history and len(history) >= 2:
        delta = history[-1] - history[-2]
        if delta > 1e-6:
            trend_label = FA_TREND_UP if fa else EN_TREND_UP
        elif delta < -1e-6:
            trend_label = FA_TREND_DOWN if fa else EN_TREND_DOWN

    if vmin is not None and vmax is not None:
        lo, hi = float(vmin), float(vmax)
        span = hi - lo
        if span <= 0:
            level_label = FA_LEVEL_MID if fa else EN_LEVEL_MID
        else:
            pct = (val - lo) / span
            if pct <= 0.2:
                level_label = (FA_RATIO_LOWEST if (lo == 0 and hi == 1) else FA_LEVEL_VERY_LOW) if fa else (EN_RATIO_LOWEST if (lo == 0 and hi == 1) else EN_LEVEL_VERY_LOW)
            elif pct <= 0.4:
                level_label = (FA_RATIO_LOW if (lo == 0 and hi == 1) else FA_LEVEL_LOW) if fa else (EN_RATIO_LOW if (lo == 0 and hi == 1) else EN_LEVEL_LOW)
            elif pct <= 0.6:
                level_label = (FA_RATIO_MID if (lo == 0 and hi == 1) else FA_LEVEL_MID) if fa else (EN_RATIO_MID if (lo == 0 and hi == 1) else EN_LEVEL_MID)
            elif pct <= 0.8:
                level_label = (FA_RATIO_HIGH if (lo == 0 and hi == 1) else FA_LEVEL_HIGH) if fa else (EN_RATIO_HIGH if (lo == 0 and hi == 1) else EN_LEVEL_HIGH)
            else:
                level_label = (FA_RATIO_HIGHEST if (lo == 0 and hi == 1) else FA_LEVEL_VERY_HIGH) if fa else (EN_RATIO_HIGHEST if (lo == 0 and hi == 1) else EN_LEVEL_VERY_HIGH)
        return level_label, trend_label

    if history and len(history) >= 2:
        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / len(history)
        std = (variance ** 0.5) if variance > 0 else 1.0
        if std > 1e-9:
            z = (val - mean) / std
            if z < -1.0:
                level_label = FA_LEVEL_VERY_LOW if fa else EN_LEVEL_VERY_LOW
            elif z < -0.3:
                level_label = FA_LEVEL_LOW if fa else EN_LEVEL_LOW
            elif z <= 0.3:
                level_label = FA_LEVEL_MID if fa else EN_LEVEL_MID
            elif z <= 1.0:
                level_label = FA_LEVEL_HIGH if fa else EN_LEVEL_HIGH
            else:
                level_label = FA_LEVEL_VERY_HIGH if fa else EN_LEVEL_VERY_HIGH
        else:
            level_label = FA_LEVEL_MID if fa else EN_LEVEL_MID
    else:
        abs_val = abs(val)
        if abs_val < 0.01:
            level_label = FA_LEVEL_VERY_LOW if fa else EN_LEVEL_VERY_LOW
        elif abs_val < 0.2:
            level_label = FA_LEVEL_LOW if fa else EN_LEVEL_LOW
        elif abs_val < 1.0:
            level_label = FA_LEVEL_MID if fa else EN_LEVEL_MID
        elif abs_val < 10.0:
            level_label = FA_LEVEL_HIGH if fa else EN_LEVEL_HIGH
        else:
            level_label = FA_LEVEL_VERY_HIGH if fa else EN_LEVEL_VERY_HIGH

    return level_label, trend_label


def label_for_key(
    key: str,
    ontology_or_label_map: dict[str, Any] | None = None,
    lang: str = "fa",
) -> str:
    """Return display label for a variable key. Same structure for fa/en; ontology used when provided."""
    if ontology_or_label_map:
        spec = ontology_or_label_map.get(key) if isinstance(ontology_or_label_map.get(key), dict) else None
        if spec and isinstance(spec, dict):
            label = spec.get("label") or spec.get("display_name")
            if isinstance(label, str) and label.strip():
                return label.strip()
        if isinstance(ontology_or_label_map.get(key), str):
            return ontology_or_label_map[key]
    return str(key).replace("_", " ").strip()


def fa_label_for_key(key: str, ontology_or_label_map: dict[str, Any] | None = None) -> str:
    """Return display label for a variable key (fa). Uses ontology/label map if provided."""
    return label_for_key(key, ontology_or_label_map, lang="fa")


def _salient_keys(
    variables: dict[str, Any],
    state_spec: dict[str, Any] | None,
    prev_snapshot: dict[str, Any] | None,
    max_keys: int = 8,
) -> list[str]:
    """Select salient keys: prefer recently changed (by delta), then ontology/priority, else all keys up to max_keys."""
    if not variables:
        return []
    keys = list(variables.keys())
    if not prev_snapshot:
        # No deltas: use state_spec priority/tags or first keys
        prev_vars = {}
    else:
        prev_vars = prev_snapshot.get("variables") or prev_snapshot.get("global_state") or {}
        if not isinstance(prev_vars, dict):
            prev_vars = {}

    # Rank by absolute delta magnitude
    deltas: list[tuple[str, float]] = []
    for k in keys:
        cur = variables.get(k)
        prev = prev_vars.get(k)
        try:
            c, p = float(cur), float(prev) if prev is not None else 0.0
            deltas.append((k, abs(c - p)))
        except (TypeError, ValueError):
            deltas.append((k, 0.0))

    deltas.sort(key=lambda x: -x[1])
    ordered = [k for k, _ in deltas]
    # state_spec priority: if a key has priority/tag, boost (already in ordered; just take top max_keys)
    return ordered[:max_keys]


def world_brief_qualitative(
    world_state: dict[str, Any],
    *,
    allow_numbers: bool = False,
    state_spec: dict[str, Any] | None = None,
    prev_snapshot: dict[str, Any] | None = None,
    max_length: int | None = DEFAULT_MAX_SUMMARY_LENGTH,
    ontology_or_label_map: dict[str, Any] | None = None,
    lang: str = "auto",
) -> str:
    """
    Produce a qualitative "World Brief" for agents. Language is not hardcoded: use lang='fa' or 'en'
    (caller should set from scenario). When lang is 'auto', default to 'en'. Same structure for both:
    salient keys, qualitative buckets, trend. No digits when allow_numbers=False.
    """
    # Do not hardcode Persian: "auto" -> en when unresolved
    resolved = "en" if lang == "auto" else lang
    parts: list[str] = []
    variables = world_state.get("variables") or world_state.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}

    salient = _salient_keys(variables, state_spec, prev_snapshot)
    if not salient:
        salient = list(variables.keys())[:8]

    for key in salient:
        if key not in variables:
            continue
        val = variables[key]
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        spec = (state_spec or {}).get(key)
        if not isinstance(spec, dict):
            spec = None
        history = None
        if prev_snapshot:
            pvars = prev_snapshot.get("variables") or prev_snapshot.get("global_state") or {}
            if isinstance(pvars, dict) and key in pvars:
                try:
                    history = [float(pvars[key]), v]
                except (TypeError, ValueError):
                    pass
        level_label, trend_label = bucket_numeric(v, spec, history, lang=resolved)
        label = label_for_key(key, ontology_or_label_map, lang=resolved)
        if resolved == "fa":
            parts.append(f"{label}: {level_label}، {trend_label}")
        else:
            parts.append(f"{label}: {level_label}, {trend_label}")

    if parts:
        parts.append("")

    derived = world_state.get("derived") or {}
    if isinstance(derived, dict):
        if derived.get("instability_mode"):
            parts.append("Instability mode is active." if resolved == "en" else "وضعیت ناپایداری فعال است.")
        else:
            if "system_stability" in derived and derived["system_stability"] is not None:
                parts.append("System stability is moderate." if resolved == "en" else "ثبات سیستم در حد متعادل.")
            if "dissatisfaction" in derived and derived["dissatisfaction"] is not None:
                parts.append("Dissatisfaction is moderate." if resolved == "en" else "سطح نارضایتی در حد متعادل.")

    turn = world_state.get("turn", 0)
    if not allow_numbers:
        parts.append("Current turn in progress." if resolved == "en" else "نوبت جاری در حال پیشرفت.")
    else:
        parts.append(f"Turn: {turn}")

    narrative = world_state.get("narrative") or []
    if isinstance(narrative, list) and narrative:
        recent = narrative[-2:] if len(narrative) >= 2 else narrative
        for line in recent:
            if isinstance(line, str) and line.strip():
                sanitized = strip_digits(line.strip()[:200], allow_numbers)
                if sanitized:
                    parts.append(f"Recent: {sanitized}")

    text = " ".join(p for p in parts if p).strip()
    if max_length is not None and len(text) > max_length:
        text = text[: max_length - 3] + "..."
    return text


def summarize(
    world_state: dict[str, Any],
    *,
    max_length: int | None = DEFAULT_MAX_SUMMARY_LENGTH,
    allow_numbers: bool = False,
    qualitative: bool = True,
    state_spec: dict[str, Any] | None = None,
    prev_snapshot: dict[str, Any] | None = None,
    lang: str = "auto",
) -> str:
    """
    Convert full world state into a short text summary. Language is not hardcoded: use lang='fa' or 'en'
    (e.g. from scenario); when 'auto', defaults to 'en'. When qualitative=True, produces a qualitative
    World Brief in the requested language (same structure for both). No raw numbers when allow_numbers=False.
    """
    if qualitative:
        ontology = world_state.get("ontology") or {}
        return world_brief_qualitative(
            world_state,
            allow_numbers=allow_numbers,
            state_spec=state_spec,
            prev_snapshot=prev_snapshot,
            max_length=max_length,
            ontology_or_label_map=ontology if isinstance(ontology, dict) else None,
            lang=lang,
        )

    # Legacy path
    parts: list[str] = []

    variables = world_state.get("variables") or world_state.get("global_state") or {}
    if isinstance(variables, dict) and variables:
        var_str = ", ".join(f"{k}: {v}" for k, v in variables.items())
        parts.append(f"Variables: {var_str}")

    derived = world_state.get("derived") or {}
    if isinstance(derived, dict):
        if "system_stability" in derived:
            parts.append(f"System stability: {derived['system_stability']}")
        if "dissatisfaction" in derived:
            parts.append(f"Dissatisfaction: {derived['dissatisfaction']}")
        if derived.get("instability_mode"):
            parts.append("Instability mode is active.")

    turn = world_state.get("turn", 0)
    version = world_state.get("version", 0)
    parts.append(f"Turn: {turn}, version: {version}")

    narrative = world_state.get("narrative") or []
    if isinstance(narrative, list) and narrative:
        recent = narrative[-2:] if len(narrative) >= 2 else narrative
        for line in recent:
            if isinstance(line, str) and line.strip():
                parts.append(f"Recent: {line.strip()[:200]}")

    text = " ".join(parts)
    if max_length is not None and len(text) > max_length:
        text = text[: max_length - 3] + "..."
    return text
