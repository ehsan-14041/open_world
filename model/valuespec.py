"""
ValueSpec: schema and adapters for every variable.
Supports numeric / ordinal / categorical / text + unknowns.
Domain-agnostic; backward compatible with legacy variable_specs (min, max, clip, rate_limit).
"""

from __future__ import annotations

from typing import Any, Literal

# --- Types ---
ValueSpecType = Literal["numeric", "ordinal", "categorical", "text"]
BehaviorType = Literal["STOCK", "FLOW"]

# Ordinal intensity levels (domain-agnostic)
ORDINAL_LEVELS = ["very_low", "low", "medium", "high", "very_high"]


def _ordinal_index(level: str) -> int:
    """Map ordinal label to index 0..len(ORDINAL_LEVELS)-1. Unknown -> 2 (medium)."""
    s = (level or "").strip().lower().replace(" ", "_")
    for i, lbl in enumerate(ORDINAL_LEVELS):
        if lbl == s or s == lbl.replace("_", ""):
            return i
    if s in ("vl", "vlow"):
        return 0
    if s in ("l", "lo"):
        return 1
    if s in ("m", "med", "mid"):
        return 2
    if s in ("h", "hi"):
        return 3
    if s in ("vh", "vhigh"):
        return 4
    return 2


def _ordinal_delta(direction: str, intensity: str) -> int:
    """Direction increase|decrease|stabilize|shift -> delta in ordinal index. intensity modulates magnitude."""
    d = (direction or "").strip().lower()
    mag = max(0, min(4, _ordinal_index(intensity or "medium")))
    if d in ("increase", "up", "raise", "1"):
        return 1 + (mag // 2)
    if d in ("decrease", "down", "lower", "reduce", "-1"):
        return -(1 + (mag // 2))
    if d in ("stabilize", "stable", "0"):
        return 0
    if d == "shift":
        return 1 if mag >= 2 else -1
    return 0


class ValueSpec:
    """
    Schema for a single variable. Required for every variable in v2.
    variables[var_id] has an associated ValueSpec (or legacy dict with min/max/clip/rate_limit).
    """

    __slots__ = (
        "type",
        "scale",
        "ordinal_labels",
        "categories",
        "clamp",
        "unit",
        "rate_limit",
        "soft_max",
        "softness",
        "behavior_type",
        "damping_factor",
        "decay_rate",
    )

    def __init__(
        self,
        *,
        type: ValueSpecType = "numeric",
        scale: dict[str, float] | None = None,
        ordinal_labels: list[str] | None = None,
        categories: list[str] | None = None,
        clamp: dict[str, Any] | None = None,
        unit: str | None = None,
        rate_limit: float | None = None,
        soft_max: float | None = None,
        softness: float | None = None,
        behavior_type: BehaviorType = "STOCK",
        damping_factor: float | None = None,
        decay_rate: float | None = None,
    ) -> None:
        self.type = type
        self.scale = scale or {}
        self.ordinal_labels = list(ordinal_labels or ORDINAL_LEVELS)
        self.categories = list(categories or [])
        self.clamp = dict(clamp or {})
        self.unit = unit
        self.rate_limit = rate_limit
        self.soft_max = soft_max
        self.softness = softness
        self.behavior_type = behavior_type if behavior_type in ("STOCK", "FLOW") else "STOCK"
        self.damping_factor = damping_factor
        self.decay_rate = decay_rate

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type}
        if self.scale:
            out["scale"] = self.scale
        if self.ordinal_labels:
            out["ordinal_labels"] = self.ordinal_labels
        if self.categories:
            out["categories"] = self.categories
        if self.clamp:
            out["clamp"] = self.clamp
        if self.unit:
            out["unit"] = self.unit
        if self.rate_limit is not None:
            out["rate_limit"] = self.rate_limit
        if self.soft_max is not None:
            out["soft_max"] = self.soft_max
        if self.softness is not None:
            out["softness"] = self.softness
        if self.behavior_type != "STOCK":
            out["behavior_type"] = self.behavior_type
        if self.damping_factor is not None:
            out["damping_factor"] = self.damping_factor
        if self.decay_rate is not None:
            out["decay_rate"] = self.decay_rate
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ValueSpec:
        if d is None:
            return cls()
        return cls(
            type=(d.get("type") or "numeric") if isinstance(d.get("type"), str) else "numeric",
            scale=d.get("scale") if isinstance(d.get("scale"), dict) else None,
            ordinal_labels=d.get("ordinal_labels") if isinstance(d.get("ordinal_labels"), list) else None,
            categories=d.get("categories") if isinstance(d.get("categories"), list) else None,
            clamp=d.get("clamp") if isinstance(d.get("clamp"), dict) else None,
            unit=d.get("unit") if isinstance(d.get("unit"), str) else None,
            rate_limit=d.get("rate_limit") if isinstance(d.get("rate_limit"), (int, float)) else None,
            soft_max=d.get("soft_max") if isinstance(d.get("soft_max"), (int, float)) else None,
            softness=d.get("softness") if isinstance(d.get("softness"), (int, float)) else None,
            behavior_type=(d.get("behavior_type") or "STOCK") if str(d.get("behavior_type", "STOCK")).upper() in ("STOCK", "FLOW") else "STOCK",
            damping_factor=d.get("damping_factor") if isinstance(d.get("damping_factor"), (int, float)) else None,
            decay_rate=d.get("decay_rate") if isinstance(d.get("decay_rate"), (int, float)) else None,
        )


def value_spec_from_legacy(legacy: dict[str, Any] | None) -> ValueSpec:
    """
    Build ValueSpec from legacy variable_specs entry (min, max, clip, rate_limit, soft_max, softness).
    Default type is numeric.
    """
    if not legacy or not isinstance(legacy, dict):
        return ValueSpec()
    scale = {}
    if legacy.get("min") is not None and isinstance(legacy["min"], (int, float)):
        scale["min"] = float(legacy["min"])
    if legacy.get("max") is not None and isinstance(legacy["max"], (int, float)):
        scale["max"] = float(legacy["max"])
    behavior_type = "FLOW" if str(legacy.get("behavior_type", "STOCK")).upper() == "FLOW" else "STOCK"
    damping_factor = legacy.get("damping_factor") if isinstance(legacy.get("damping_factor"), (int, float)) else None
    return ValueSpec(
        type="numeric",
        scale=scale or None,
        clamp=legacy if legacy.get("clip") else None,
        rate_limit=legacy.get("rate_limit") if isinstance(legacy.get("rate_limit"), (int, float)) else None,
        soft_max=legacy.get("soft_max") if isinstance(legacy.get("soft_max"), (int, float)) else None,
        softness=legacy.get("softness") if isinstance(legacy.get("softness"), (int, float)) else None,
        behavior_type=behavior_type,
        damping_factor=damping_factor,
        decay_rate=legacy.get("decay_rate") if isinstance(legacy.get("decay_rate"), (int, float)) else None,
    )


def clamp_value(
    var_id: str,
    value: Any,
    spec: ValueSpec | dict[str, Any] | None,
    *,
    is_delta: bool = False,
) -> Any:
    """
    Clamp a value (or delta) to ValueSpec. For numeric: min/max/rate_limit.
    For ordinal/categorical: ensure value is in labels/categories; for delta use ordinal index.
    Unknown (None) is returned as-is unless spec forces a default.
    """
    if spec is None:
        return value
    vs = spec if isinstance(spec, ValueSpec) else ValueSpec.from_dict(spec) if isinstance(spec, dict) else ValueSpec()

    if value is None:
        if vs.type == "numeric" and vs.scale:
            lo = vs.scale.get("min")
            hi = vs.scale.get("max")
            if lo is not None and hi is not None:
                return (float(lo) + float(hi)) / 2
        return value

    if vs.type == "numeric":
        try:
            v = float(value)
        except (TypeError, ValueError):
            return value
        if is_delta and vs.rate_limit is not None:
            v = max(-float(vs.rate_limit), min(float(vs.rate_limit), v))
        if not is_delta:
            lo = vs.scale.get("min")
            hi = vs.scale.get("max")
            if lo is not None and v < float(lo):
                v = float(lo)
            if hi is not None and v > float(hi):
                v = float(hi)
        return v

    if vs.type == "ordinal":
        if is_delta:
            return value  # caller applies to index
        labels = vs.ordinal_labels or ORDINAL_LEVELS
        if isinstance(value, (int, float)):
            idx = max(0, min(len(labels) - 1, int(value)))
            return labels[idx]
        if isinstance(value, str) and value in labels:
            return value
        idx = _ordinal_index(str(value))
        return labels[min(idx, len(labels) - 1)]

    if vs.type == "categorical":
        if is_delta:
            return value
        if vs.categories and value in vs.categories:
            return value
        if vs.categories:
            return vs.categories[0]
        return value

    return value


def to_scalar_for_utility(
    var_id: str,
    value: Any,
    spec: ValueSpec | dict[str, Any] | None,
) -> float:
    """
    Map a variable value to a scalar for utility weighting. Supports numeric, ordinal, categorical, unknown.
    Unknown (None or distribution dict) -> use expected value or interval midpoint.
    """
    if value is None:
        return 0.0
    vs = spec if isinstance(spec, ValueSpec) else ValueSpec.from_dict(spec) if isinstance(spec, dict) else ValueSpec()

    # Belief distribution: numeric
    if isinstance(value, dict):
        if "mean" in value and isinstance(value.get("mean"), (int, float)):
            return float(value["mean"])
        if "min" in value and "max" in value:
            lo, hi = value["min"], value["max"]
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
                return (float(lo) + float(hi)) / 2
        if "distribution" in value and isinstance(value["distribution"], dict):
            dist = value["distribution"]
            # Expected value for categorical/ordinal
            total = 0.0
            weight_sum = 0.0
            for k, w in dist.items():
                try:
                    total += float(k) * float(w)
                    weight_sum += float(w)
                except (TypeError, ValueError):
                    pass
            if weight_sum > 0:
                return total / weight_sum
        if "value" in value and isinstance(value.get("value"), (int, float)):
            return float(value["value"])
        return 0.0

    if vs.type == "numeric":
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    if vs.type == "ordinal":
        labels = vs.ordinal_labels or ORDINAL_LEVELS
        idx = _ordinal_index(str(value)) if not isinstance(value, (int, float)) else max(0, min(len(labels) - 1, int(value)))
        return (idx / max(1, len(labels) - 1)) * 100.0  # 0..100 scale
    if vs.type == "categorical":
        cats = vs.categories or []
        if value in cats:
            return (cats.index(value) / max(1, len(cats) - 1)) * 100.0
        return 50.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_belief_value(value: Any, spec: ValueSpec | dict[str, Any] | None) -> Any:
    """
    Parse a belief_state value (may be distribution/interval) for display or comparison.
    Returns a canonical form: for numeric {mean, std} or {min, max}; ordinal/categorical {distribution}; text {value, confidence}.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        return value
    vs = spec if isinstance(spec, ValueSpec) else ValueSpec.from_dict(spec) if isinstance(spec, dict) else ValueSpec()
    if vs.type == "text" and "value" in value:
        return {"value": value.get("value"), "confidence": value.get("confidence", 0.5)}
    return value
ue
