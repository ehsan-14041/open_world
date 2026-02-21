"""
Generic numeric-to-ordinal mapping for narrative (domain-agnostic).
Uses ValueSpec when available; otherwise simple threshold bucketing.
No domain-specific variable names or keywords.
"""

from __future__ import annotations

from typing import Any

# Generic ordinal labels (no domain meaning)
LEVEL_LOW = "low"
LEVEL_MODERATE = "moderate"
LEVEL_HIGH = "high"
LEVEL_VERY_LOW = "very low"
LEVEL_VERY_HIGH = "very high"

# Persian equivalents (presentation only)
LEVEL_FA = {
    LEVEL_VERY_LOW: "بسیار پایین",
    LEVEL_LOW: "پایین",
    LEVEL_MODERATE: "متوسط",
    LEVEL_HIGH: "بالا",
    LEVEL_VERY_HIGH: "بسیار بالا",
}


def bucket_numeric_to_ordinal(
    value: float,
    spec: dict[str, Any] | None = None,
    *,
    lang: str = "en",
) -> str:
    """
    Map a numeric value to a qualitative ordinal label (e.g. low, moderate, high).
    spec may have min, max, or range; if absent, use 0–100 as default scale.
    Domain-agnostic: no variable-name or domain logic.
    """
    try:
        val = float(value)
    except (TypeError, ValueError):
        return LEVEL_FA.get(LEVEL_MODERATE, LEVEL_MODERATE) if lang == "fa" else LEVEL_MODERATE

    vmin, vmax = 0.0, 100.0
    if spec and isinstance(spec, dict):
        if spec.get("min") is not None:
            try:
                vmin = float(spec["min"])
            except (TypeError, ValueError):
                pass
        if spec.get("max") is not None:
            try:
                vmax = float(spec["max"])
            except (TypeError, ValueError):
                pass
        if "range" in spec and isinstance(spec["range"], (list, tuple)) and len(spec["range"]) >= 2:
            try:
                vmin, vmax = float(spec["range"][0]), float(spec["range"][1])
            except (TypeError, ValueError):
                pass

    span = vmax - vmin
    if span <= 0:
        level = LEVEL_MODERATE
    else:
        pct = (val - vmin) / span
        if pct <= 0.2:
            level = LEVEL_VERY_LOW
        elif pct <= 0.4:
            level = LEVEL_LOW
        elif pct <= 0.6:
            level = LEVEL_MODERATE
        elif pct <= 0.8:
            level = LEVEL_HIGH
        else:
            level = LEVEL_VERY_HIGH

    if lang == "fa":
        return LEVEL_FA.get(level, level)
    return level


def humanize_var_id(var_id: str) -> str:
    """
    Convert a variable id (snake_case) to a generic display form (spaced words).
    No domain-specific mapping; purely structural.
    """
    if not var_id or not isinstance(var_id, str):
        return "variable"
    s = str(var_id).replace("_", " ").strip()
    # Simple title-style: first letter upper per word
    parts = s.split()
    return " ".join(p.capitalize() for p in parts) if parts else "variable"
