"""
Regime detector: classifies system state as NORMAL, FRAGILE, or CRISIS.
Used for regime-aware physics (increased decay/inertia in CRISIS) and dashboard.
"""

from __future__ import annotations

from typing import Any

# Default entropy growth threshold for CRISIS (percent_high > 0.3 and entropy_growth > this)
DEFAULT_ENTROPY_GROWTH_THRESHOLD = 0.5


def _spec_max(spec: dict[str, Any] | None) -> float | None:
    """Return max bound from legacy or scale; None if not set."""
    if not spec or not isinstance(spec, dict):
        return None
    hi = spec.get("max")
    if isinstance(hi, (int, float)):
        return float(hi)
    scale = spec.get("scale")
    if isinstance(scale, dict):
        hi = scale.get("max")
        if isinstance(hi, (int, float)):
            return float(hi)
    return None


def detect_regime(
    variables: dict[str, float],
    variable_specs: dict[str, dict[str, Any]] | None,
    entropy_t: float,
    entropy_t_minus_1: float | None,
    agent_calibration_scores: list[float] | None = None,
    *,
    entropy_growth_threshold: float | None = None,
) -> dict[str, Any]:
    """
    Compute regime from saturation, entropy growth, and calibration.

    Inputs:
        variables: current variable values
        variable_specs: per-var specs (legacy min/max or scale)
        entropy_t: current turn world entropy
        entropy_t_minus_1: previous turn world entropy (None => 0)
        agent_calibration_scores: list of 0-1 calibration scores per agent (optional)
        entropy_growth_threshold: threshold for entropy_growth to trigger CRISIS (default DEFAULT_ENTROPY_GROWTH_THRESHOLD)

    Returns:
        {
            "regime": "NORMAL" | "FRAGILE" | "CRISIS",
            "percent_high": float,
            "entropy_growth": float,
            "calibration_avg": float,
        }
    """
    threshold = (
        entropy_growth_threshold
        if entropy_growth_threshold is not None
        else DEFAULT_ENTROPY_GROWTH_THRESHOLD
    )
    entropy_prev = entropy_t_minus_1 if entropy_t_minus_1 is not None else entropy_t
    entropy_growth = entropy_t - entropy_prev

    # percent_high: fraction of (bounded) variables with value > 0.9 * max_bound
    bounded_vars = 0
    high_count = 0
    specs = variable_specs or {}
    for var_id, value in variables.items():
        if not isinstance(value, (int, float)):
            continue
        max_bound = _spec_max(specs.get(var_id))
        if max_bound is None:
            continue
        bounded_vars += 1
        if float(value) > 0.9 * max_bound:
            high_count += 1
    percent_high = high_count / bounded_vars if bounded_vars else 0.0

    # calibration_avg: mean of agent calibration scores (0-1)
    if agent_calibration_scores:
        calibration_avg = sum(agent_calibration_scores) / len(agent_calibration_scores)
        calibration_avg = max(0.0, min(1.0, calibration_avg))
    else:
        calibration_avg = 0.5  # neutral when no agents

    # Classification
    if percent_high > 0.3 and entropy_growth > threshold:
        regime = "CRISIS"
    elif percent_high > 0.15:
        regime = "FRAGILE"
    else:
        regime = "NORMAL"

    return {
        "regime": regime,
        "percent_high": percent_high,
        "entropy_growth": entropy_growth,
        "calibration_avg": calibration_avg,
    }
