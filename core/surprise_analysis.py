"""
Self-correction: SurpriseAnalysis when actual outcome deviates from predicted_delta_light.
Computes relative_error for adaptive calibration; triggers when relative_error > SURPRISE_THRESHOLD.
"""

from __future__ import annotations

from typing import Any

EPS = 1e-9


def _extract_actual_deltas(actual_outcome: dict[str, Any] | None) -> dict[str, float]:
    actual_deltas: dict[str, float] = {}
    if not actual_outcome:
        return actual_deltas
    if isinstance(actual_outcome.get("variable_changes"), list):
        for ch in actual_outcome["variable_changes"]:
            if isinstance(ch, dict):
                var = ch.get("var") or ch.get("variable")
                delta = ch.get("delta") or ch.get("change")
                if var and isinstance(delta, (int, float)):
                    actual_deltas[str(var)] = actual_deltas.get(str(var), 0.0) + float(delta)
    if isinstance(actual_outcome.get("delta_applied"), dict):
        for k, v in actual_outcome["delta_applied"].items():
            if isinstance(v, (int, float)):
                actual_deltas[str(k)] = actual_deltas.get(str(k), 0.0) + float(v)
    return actual_deltas


def run_surprise_analysis(
    predicted_delta_light: dict[str, float] | None,
    actual_outcome: dict[str, Any] | None,
    deviation_threshold: float,
    *,
    surprise_threshold: float | None = None,
) -> dict[str, Any]:
    """
    Compare predicted vs actual. Computes relative_error = sum(|predicted - actual|) / (sum(|actual_delta|) + eps).
    Triggers when: (1) any |actual - predicted| > deviation_threshold, or
    (2) relative_error > surprise_threshold (e.g. 0.2).
    Returns dict: triggered (bool), relative_error (float), deviation_by_var (dict), message (str).
    """
    try:
        from config.settings import SURPRISE_THRESHOLD as default_surprise
    except ImportError:
        default_surprise = 0.2
    thresh = surprise_threshold if surprise_threshold is not None else default_surprise

    result: dict[str, Any] = {
        "triggered": False,
        "relative_error": 0.0,
        "deviation_by_var": {},
        "message": "",
    }
    if not predicted_delta_light or not actual_outcome:
        return result

    actual_deltas = _extract_actual_deltas(actual_outcome)
    deviation_by_var: dict[str, float] = {}
    sum_abs_error = 0.0
    sum_abs_actual = 0.0
    for var in set(predicted_delta_light) | set(actual_deltas):
        pred = float(predicted_delta_light.get(var, 0.0))
        act = float(actual_deltas.get(var, 0.0))
        dev = abs(act - pred)
        sum_abs_error += dev
        sum_abs_actual += abs(act)
        if dev > deviation_threshold:
            deviation_by_var[var] = dev

    relative_error = sum_abs_error / (sum_abs_actual + EPS)
    result["relative_error"] = relative_error
    result["deviation_by_var"] = deviation_by_var
    result["triggered"] = len(deviation_by_var) > 0 or relative_error > thresh
    if result["triggered"]:
        result["message"] = (
            f"SurpriseAnalysis: relative_error={relative_error:.4f} (threshold {thresh}); "
            f"{len(deviation_by_var)} vars exceeded deviation threshold {deviation_threshold}"
        )
    return result
