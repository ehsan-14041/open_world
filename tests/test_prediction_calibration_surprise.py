"""
Tests for prediction_calibration (update_with_surprise, causal_learning_flag) and surprise_analysis (relative_error).
"""

from __future__ import annotations

import pytest

from core.surprise_analysis import run_surprise_analysis, _extract_actual_deltas
from core.prediction_calibration import (
    update_with_surprise,
    get_causal_learning_flag,
    get_learning_rate_override,
    get_metrics,
)


def test_surprise_relative_error_below_threshold() -> None:
    """relative_error is computed and triggered is False when below threshold."""
    pred = {"x": 1.0, "y": 2.0}
    actual_outcome = {"variable_changes": [{"var": "x", "delta": 1.0}, {"var": "y", "delta": 2.0}]}
    result = run_surprise_analysis(pred, actual_outcome, deviation_threshold=10.0, surprise_threshold=0.5)
    assert "relative_error" in result
    assert result["relative_error"] <= 0.5
    assert result["triggered"] is False


def test_surprise_relative_error_above_threshold() -> None:
    """When relative_error > surprise_threshold, triggered is True."""
    pred = {"x": 0.0, "y": 0.0}
    actual_outcome = {"variable_changes": [{"var": "x", "delta": 5.0}, {"var": "y", "delta": 5.0}]}
    result = run_surprise_analysis(pred, actual_outcome, deviation_threshold=0.1, surprise_threshold=0.2)
    assert "relative_error" in result
    assert result["relative_error"] > 0.2
    assert result["triggered"] is True


def test_extract_actual_deltas() -> None:
    """_extract_actual_deltas builds var->delta from variable_changes and delta_applied (top-level)."""
    entry = {
        "variable_changes": [{"var": "a", "delta": 1.0}, {"var": "b", "delta": -2.0}],
        "delta_applied": {"c": 3.0},
    }
    out = _extract_actual_deltas(entry)
    assert out.get("a") == 1.0
    assert out.get("b") == -2.0
    assert out.get("c") == 3.0


def test_update_with_surprise_sets_flag() -> None:
    """When surprise_triggered=True, causal_learning_flag is set and learning_rate_override is higher."""
    agent_id = "test_agent_surprise_%s" % id(object())
    update_with_surprise(
        agent_id,
        predicted_delta={"x": 1.0},
        actual_delta={"x": 5.0},
        relative_error=0.8,
        surprise_triggered=True,
    )
    assert get_causal_learning_flag(agent_id) is True
    assert get_learning_rate_override(agent_id) is not None
    m = get_metrics(agent_id)
    assert m.get("causal_learning_flag") is True


def test_update_with_surprise_no_surprise_clears_override() -> None:
    """When surprise_triggered=False, learning_rate_override is None after countdown."""
    agent_id = "test_agent_nosurprise_%s" % id(object())
    update_with_surprise(
        agent_id,
        predicted_delta={"x": 1.0},
        actual_delta={"x": 1.0},
        relative_error=0.05,
        surprise_triggered=False,
    )
    m = get_metrics(agent_id)
    assert m.get("learning_rate_override") is None or not m.get("causal_learning_flag")
