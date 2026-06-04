"""
Prediction calibration: per-agent rolling MSE, bias, variance, and calibration weight.
Updates from actual_delta vs predicted_delta each turn. When surprise is triggered
(relative_error > threshold), temporarily increase learning rate and set causal_learning flag.
"""

from __future__ import annotations

from typing import Any

ALPHA_DEFAULT = 0.1
ALPHA_SURPRISE = 0.25  # higher learning rate when surprise triggered
ALPHA_HUMILITY = 0.15  # learning rate in humility mode (1.5 * ALPHA_DEFAULT)
WEIGHT_MIN = 0.2
WEIGHT_MAX = 1.5
CAUSAL_LEARNING_FLAG_TURNS = 2  # number of turns to keep flag set
CONFIDENCE_BIAS_MULTIPLIER_HUMILITY = 0.7  # confidence bias scale in humility mode

_store: dict[str, dict[str, Any]] = {}


def _ensure_agent(agent_id: str) -> None:
    if agent_id not in _store:
        _store[agent_id] = {
            "rolling_mse": 0.0,
            "rolling_bias": 0.0,
            "rolling_variance": 0.0,
            "calibration_weight": 1.0,
            "learning_rate_override": None,
            "causal_learning_flag": False,
            "causal_learning_countdown": 0,
            "confidence_bias_multiplier": 1.0,
            "humility_mode": False,
        }


def update(
    agent_id: str,
    predicted_delta: dict[str, float],
    actual_delta: dict[str, float],
    *,
    alpha: float = ALPHA_DEFAULT,
) -> None:
    """
    Update per-agent calibration from this turn's error (actual - predicted).
    Uses scalar summary over variables: mean error and mean squared error for EMA.
    """
    if not agent_id:
        return
    _ensure_agent(agent_id)
    all_vars = set(predicted_delta.keys()) | set(actual_delta.keys())
    if not all_vars:
        return
    errors = [
        actual_delta.get(v, 0.0) - predicted_delta.get(v, 0.0)
        for v in all_vars
        if isinstance(actual_delta.get(v), (int, float)) or isinstance(predicted_delta.get(v), (int, float))
    ]
    if not errors:
        return
    mean_error = sum(errors) / len(errors)
    mean_sq_error = sum(e * e for e in errors) / len(errors)
    variance = sum((e - mean_error) ** 2 for e in errors) / len(errors) if len(errors) > 1 else 0.0
    alpha = max(0.01, min(0.5, float(alpha)))
    prev = _store[agent_id]
    prev_mse = prev["rolling_mse"]
    prev_bias = prev["rolling_bias"]
    prev_var = prev["rolling_variance"]
    new_mse = alpha * mean_sq_error + (1 - alpha) * prev_mse
    new_bias = alpha * mean_error + (1 - alpha) * prev_bias
    new_var = alpha * variance + (1 - alpha) * prev_var

    # NaN/Inf guard: reset to previous valid value if computed value is invalid
    if not (new_mse == new_mse and abs(new_mse) != float("inf")):
        new_mse = prev_mse
    if not (new_bias == new_bias and abs(new_bias) != float("inf")):
        new_bias = prev_bias
    if not (new_var == new_var and abs(new_var) != float("inf")):
        new_var = prev_var

    # Bias explosion dampen: no learning rate explosions
    if abs(new_bias) > 1e6:
        new_bias = new_bias * 0.1

    _store[agent_id]["rolling_mse"] = new_mse
    _store[agent_id]["rolling_bias"] = new_bias
    _store[agent_id]["rolling_variance"] = max(0.0, new_var)
    denom = 1.0 + abs(new_bias) + max(0.0, new_var)
    w = 1.0 / denom if denom > 1e-12 else 1.0
    calibration_weight = min(WEIGHT_MAX, max(WEIGHT_MIN, w))
    _store[agent_id]["calibration_weight"] = calibration_weight


def update_with_surprise(
    agent_id: str,
    predicted_delta: dict[str, float],
    actual_delta: dict[str, float],
    relative_error: float,
    surprise_triggered: bool,
    *,
    surprise_threshold: float = 0.2,
) -> None:
    """
    Update calibration; when surprise_triggered (relative_error > surprise_threshold),
    use higher learning rate (alpha), reduce/cap confidence weight, and set causal_learning flag.
    """
    alpha = ALPHA_SURPRISE if surprise_triggered else ALPHA_DEFAULT
    _ensure_agent(agent_id)
    update(agent_id, predicted_delta, actual_delta, alpha=alpha)
    if surprise_triggered:
        _store[agent_id]["learning_rate_override"] = alpha
        _store[agent_id]["causal_learning_flag"] = True
        _store[agent_id]["causal_learning_countdown"] = CAUSAL_LEARNING_FLAG_TURNS
        # Reduce confidence weight when surprise: cap calibration_weight from above
        cw = _store[agent_id]["calibration_weight"]
        _store[agent_id]["calibration_weight"] = min(cw, 0.8)
    else:
        countdown = _store[agent_id].get("causal_learning_countdown", 0)
        if countdown > 0:
            _store[agent_id]["causal_learning_countdown"] = countdown - 1
        else:
            _store[agent_id]["causal_learning_flag"] = False
            _store[agent_id]["learning_rate_override"] = None


def get_calibration_weight(agent_id: str) -> float:
    """Return calibration weight for agent; 1.0 if unknown."""
    _ensure_agent(agent_id)
    return float(_store[agent_id]["calibration_weight"])


def get_calibration_score(agent_id: str) -> float:
    """
    Return a 0-1 calibration score for the agent. Higher = better predictions.
    Uses 1 / (1 + rolling_mse) with a penalty for large bias; clamped to [0, 1].
    """
    _ensure_agent(agent_id)
    row = _store[agent_id]
    mse = max(0.0, float(row["rolling_mse"]))
    bias = abs(float(row["rolling_bias"]))
    score = 1.0 / (1.0 + mse + 0.2 * bias)
    return max(0.0, min(1.0, score))


def get_metrics(agent_id: str) -> dict[str, Any]:
    """Return rolling_mse, bias (rolling_bias), calibration_weight, calibration_score, causal_learning_flag for dashboard."""
    _ensure_agent(agent_id)
    row = _store[agent_id]
    return {
        "rolling_mse": row["rolling_mse"],
        "bias": row["rolling_bias"],
        "rolling_variance": row["rolling_variance"],
        "calibration_weight": row["calibration_weight"],
        "calibration_score": get_calibration_score(agent_id),
        "causal_learning_flag": row.get("causal_learning_flag", False),
        "learning_rate_override": row.get("learning_rate_override"),
        "confidence_bias_multiplier": row.get("confidence_bias_multiplier", 1.0),
        "humility_mode": row.get("humility_mode", False),
    }


def get_causal_learning_flag(agent_id: str) -> bool:
    """Return whether causal learning should be invoked for this agent (surprise-driven)."""
    _ensure_agent(agent_id)
    return bool(_store[agent_id].get("causal_learning_flag", False))


def get_learning_rate_override(agent_id: str) -> float | None:
    """Return temporary learning rate (alpha) when surprise or humility mode; None otherwise."""
    _ensure_agent(agent_id)
    return _store[agent_id].get("learning_rate_override")


def get_confidence_bias_multiplier(agent_id: str) -> float:
    """Return confidence bias multiplier (1.0 normally, 0.7 in humility mode)."""
    _ensure_agent(agent_id)
    return float(_store[agent_id].get("confidence_bias_multiplier", 1.0))


def apply_humility_mode(
    agent_ids: list[str],
    regime: str,
    *,
    calibration_threshold: float = 0.2,
) -> None:
    """
    When regime == "CRISIS" or any agent has calibration_score < calibration_threshold,
    set humility mode: learning_rate_override = ALPHA_HUMILITY, confidence_bias_multiplier = 0.7.
    Otherwise clear override and set multiplier to 1.0.
    """
    active = regime == "CRISIS"
    if not active and agent_ids:
        for aid in agent_ids:
            if get_calibration_score(aid) < calibration_threshold:
                active = True
                break
    for aid in agent_ids:
        _ensure_agent(aid)
        if active:
            _store[aid]["learning_rate_override"] = ALPHA_HUMILITY
            _store[aid]["confidence_bias_multiplier"] = CONFIDENCE_BIAS_MULTIPLIER_HUMILITY
            _store[aid]["humility_mode"] = True
        else:
            _store[aid]["confidence_bias_multiplier"] = 1.0
            _store[aid]["humility_mode"] = False
