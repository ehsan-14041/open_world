"""
Self-correction: SurpriseAnalysis when actual outcome deviates from predicted_delta_light.
"""

from __future__ import annotations

from typing import Any


def run_surprise_analysis(
    predicted_delta_light: dict[str, float] | None,
    actual_outcome: dict[str, Any] | None,
    deviation_threshold: float,
) -> dict[str, Any]:
    """
    Compare predicted vs actual; trigger when any |actual - predicted| > deviation_threshold.
    Returns dict: triggered (bool), deviation_by_var (dict), message (str).
    """
    result: dict[str, Any] = {
        "triggered": False,
        "deviation_by_var": {},
        "message": "",
    }
    if not predicted_delta_light or not actual_outcome:
        return result
    actual_deltas: dict[str, float] = {}
    if isinstance(actual_outcome.get("variable_changes"), list):
        for ch in actual_outcome["variable_changes"]:
            if isinstance(ch, dict):
                var = ch.get("var") or ch.get("variable")
                delta = ch.get("delta") or ch.get("change")
                if var and isinstance(delta, (int, float)):
                    actual_deltas[str(var)] = float(delta)
    if isinstance(actual_outcome.get("delta_applied"), dict):
        for k, v in actual_outcome["delta_applied"].items():
            if isinstance(v, (int, float)):
                actual_deltas[str(k)] = actual_deltas.get(str(k), 0.0) + float(v)
    deviation_by_var: dict[str, float] = {}
    for var in set(predicted_delta_light) | set(actual_deltas):
        pred = float(predicted_delta_light.get(var, 0.0))
        act = float(actual_deltas.get(var, 0.0))
        dev = abs(act - pred)
        if dev > deviation_threshold:
            deviation_by_var[var] = dev
    result["deviation_by_var"] = deviation_by_var
    result["triggered"] = len(deviation_by_var) > 0
    result["message"] = f"SurpriseAnalysis triggered: {len(deviation_by_var)} vars exceeded threshold {deviation_threshold}" if deviation_by_var else ""
    return result
