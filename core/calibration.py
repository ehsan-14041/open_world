"""
Dynamic calibration: periodic or drift-triggered recalibration from prediction vs realized metrics.
Recalibration action: reduce LLM influence flag, store calibration_event in provenance and dashboard.
"""

from __future__ import annotations

from typing import Any

# Module state for recalibration
_recalibration_triggered: bool = False
_last_recalibration_turn: int = -1


def check_recalibration_trigger(
    provenance_history: list[dict[str, Any]],
    *,
    recalibrate_turns: int = 10,
    drift_threshold_pct: float = 0.2,
    rmse_red_threshold: float = 3.0,
    min_interval_turns: int | None = None,
    max_interval_turns: int | None = None,
) -> tuple[bool, str]:
    """
    Returns (should_recalibrate, reason).
    Periodic: every recalibrate_turns, if health is red or RMSE > rmse_red_threshold.
    Drift: moving average of prediction error increases by drift_threshold_pct over last K turns.
    min_interval_turns: do not trigger if last recalibration was fewer turns ago (avoid overfitting).
    max_interval_turns: force a check when turn - last_recalibration_turn >= this (avoid drift).
    """
    try:
        from core.dashboard_payload import compute_calibration_from_provenance
    except ImportError:
        return False, ""

    if not provenance_history or len(provenance_history) < 2:
        return False, ""

    turn = provenance_history[-1].get("turn", len(provenance_history))
    if min_interval_turns is not None and _last_recalibration_turn >= 0:
        if turn - _last_recalibration_turn < min_interval_turns:
            return False, ""
    if max_interval_turns is not None and max_interval_turns > 0 and _last_recalibration_turn >= 0:
        if turn - _last_recalibration_turn >= max_interval_turns:
            return True, "max_interval: forced recalibration check"

    cal = compute_calibration_from_provenance(provenance_history)
    health = cal.get("health", "green")
    rmse_over_time = cal.get("rmse_over_time") or []
    mean_rmse = sum(rmse_over_time) / len(rmse_over_time) if rmse_over_time else 0.0

    # Periodic: every N turns check
    if turn > 0 and turn % recalibrate_turns == 0:
        if health == "red" or mean_rmse >= rmse_red_threshold:
            return True, f"periodic: health={health}, mean_rmse={mean_rmse:.2f}"

    # Drift: last K turns error trend
    if len(rmse_over_time) >= 5:
        recent = rmse_over_time[-5:]
        older = rmse_over_time[-10:-5] if len(rmse_over_time) >= 10 else rmse_over_time[:5]
        if older:
            mean_older = sum(older) / len(older)
            mean_recent = sum(recent) / len(recent)
            if mean_older > 1e-9 and (mean_recent - mean_older) / mean_older >= drift_threshold_pct:
                return True, f"drift: prediction error increased {drift_threshold_pct*100:.0f}%"

    return False, ""


def apply_recalibration_action() -> dict[str, Any]:
    """
    When recalibration is triggered: set module state (recalibration_triggered, last_turn).
    Returns calibration_event dict for provenance/dashboard. No automatic model retraining.
    """
    global _recalibration_triggered, _last_recalibration_turn
    _recalibration_triggered = True
    # last_recalibration_turn set by caller with current turn
    return {
        "recalibration_triggered": True,
        "action": "flag_set",
        "message": "Recalibration flag set; consider reducing LLM weight or using rule-based for next turn.",
    }


def set_last_recalibration_turn(turn: int) -> None:
    global _last_recalibration_turn
    _last_recalibration_turn = turn


def get_recalibration_state() -> dict[str, Any]:
    return {
        "recalibration_triggered": _recalibration_triggered,
        "last_recalibration_turn": _last_recalibration_turn,
        "min_interval_turns": None,
        "max_interval_turns": None,
    }


def clear_recalibration_trigger() -> None:
    global _recalibration_triggered
    _recalibration_triggered = False
