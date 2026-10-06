"""Tests for kill criteria derivation."""

from __future__ import annotations

from core.kill_criteria import derive_kill_criteria


def test_derive_kill_criteria_returns_regime_thresholds() -> None:
    scenario = {
        "variables": [
            {"name": "revenue", "min": 0, "max": 100, "label": "Revenue"},
            {"name": "churn", "min": 0, "max": 50, "label": "Churn"},
        ],
    }
    final_snapshot = {
        "variables": {"revenue": 55, "churn": 12},
        "derived": {"system_stability": 65, "dissatisfaction": 40},
    }
    criteria = derive_kill_criteria(final_snapshot, [], scenario, decision_input={"move": "raise prices"})
    assert len(criteria) >= 1
    assert all("watch_variable" in c and "threshold" in c and "why" in c for c in criteria)
    vars_seen = {c["watch_variable"] for c in criteria}
    assert "system_stability" in vars_seen or "dissatisfaction" in vars_seen or "revenue" in vars_seen


def test_derive_kill_criteria_uses_scenario_variable_bounds() -> None:
    scenario = {
        "variables": [
            {"name": "customer_churn", "min": 0, "max": 100, "label": "Customer churn"},
        ],
    }
    final_snapshot = {
        "variables": {"customer_churn": 92},
        "derived": {"system_stability": 80, "dissatisfaction": 20},
    }
    decision = {"move": "raise prices for customers"}
    criteria = derive_kill_criteria(final_snapshot, [], scenario, decision_input=decision, max_criteria=3)
    var_names = [c["watch_variable"] for c in criteria]
    assert any(v in ("customer_churn", "system_stability", "dissatisfaction") for v in var_names)
    for c in criteria:
        assert c["threshold"]
        assert c["signal"]
        assert c["why"]


def test_derive_kill_criteria_fallback_when_empty() -> None:
    criteria = derive_kill_criteria({}, [], {}, decision_input=None, max_criteria=3)
    assert len(criteria) >= 1
    assert criteria[0]["watch_variable"]
