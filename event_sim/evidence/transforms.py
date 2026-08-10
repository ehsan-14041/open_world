"""
Named, testable transformations between real-world units and simulation units.

The simulator works in deviations from baseline; real data arrives as TEU/week, days,
USD/40ft, percentages and index points. Converting between them is where a grounding
effort quietly goes wrong, so every conversion here is:

  - a **named** function, referenced by name from a ProxyMapping
  - **pure** and unit-annotated
  - **non-destructive** — the raw observed value and its unit are never overwritten;
    `apply()` returns a new record carrying both the raw and the converted value

Never fit across incompatible scales without going through one of these.
"""

from __future__ import annotations

from typing import Any, Callable

TransformFn = Callable[..., float]

_REGISTRY: dict[str, TransformFn] = {}


def register(name: str) -> Callable[[TransformFn], TransformFn]:
    def _wrap(fn: TransformFn) -> TransformFn:
        _REGISTRY[name] = fn
        return fn
    return _wrap


def get(name: str) -> TransformFn:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown transformation {name!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def available() -> list[str]:
    return sorted(_REGISTRY)


@register("identity")
def identity(value: float, **_: Any) -> float:
    """Real metric is already in the simulation variable's unit."""
    return float(value)


@register("normalize_against_baseline")
def normalize_against_baseline(value: float, *, baseline: float, scale: float = 100.0, **_: Any) -> float:
    """
    Convert an absolute level to an index where `baseline` maps to `scale`.

    Example: Yantian throughput 30% of normal -> normalize_against_baseline(0.30, baseline=1.0)
    = 30.0 index points on a 100 = normal scale.
    """
    if baseline == 0:
        raise ValueError("normalize_against_baseline requires a non-zero baseline")
    return float(value) / float(baseline) * float(scale)


@register("percent_change_from_baseline")
def percent_change_from_baseline(value: float, *, baseline: float, scale: float = 100.0, **_: Any) -> float:
    """Convert a level to an index of percent change: baseline -> `scale`, +10% -> scale*1.1."""
    if baseline == 0:
        raise ValueError("percent_change_from_baseline requires a non-zero baseline")
    return (float(value) - float(baseline)) / float(baseline) * float(scale) + float(scale)


@register("index_to_relative_deviation")
def index_to_relative_deviation(value: float, *, baseline: float, scale: float, **_: Any) -> float:
    """Convert an index value to the engine's deviation space: (value - baseline) / scale."""
    if scale == 0:
        raise ValueError("index_to_relative_deviation requires a non-zero scale")
    return (float(value) - float(baseline)) / float(scale)


@register("percent_to_fraction")
def percent_to_fraction(value: float, **_: Any) -> float:
    """35.6 (%) -> 0.356."""
    return float(value) / 100.0


@register("reliability_to_delay_days")
def reliability_to_delay_days(value: float, *, baseline_delay: float, baseline_reliability: float, **_: Any) -> float:
    """
    Convert a schedule-reliability percentage to an implied delay in days, relative to a
    stated baseline pair.

    DELIBERATELY CRUDE and flagged as such wherever it is used: reliability (share of
    vessels arriving on time) and delay (how late the late ones are) are different
    quantities, and this linear inversion is an assumption, not a measurement. Prefer the
    directly published average-delay-in-days series when one exists.
    """
    if baseline_reliability == 0:
        raise ValueError("reliability_to_delay_days requires a non-zero baseline reliability")
    return float(baseline_delay) * (float(baseline_reliability) / max(1e-9, float(value)))


def apply(
    transformation: str,
    raw_value: float,
    *,
    raw_unit: str = "",
    target_unit: str = "",
    **params: Any,
) -> dict[str, Any]:
    """
    Apply a named transformation, preserving the raw value and unit alongside the result.

    Returns a record rather than a bare float precisely so that raw source data is never
    lost behind a normalised number.
    """
    fn = get(transformation)
    converted = float(fn(float(raw_value), **params))
    return {
        "raw_value": float(raw_value),
        "raw_unit": raw_unit,
        "transformation": transformation,
        "parameters": dict(params),
        "value": converted,
        "unit": target_unit,
    }
