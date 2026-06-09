"""Tests for startup outcome cards."""

from __future__ import annotations

from ui.startup_outcomes import build_startup_outcomes, humanize_var


def test_humanize_var() -> None:
    assert humanize_var("runway_months") == "Cash runway"
    assert humanize_var("mrr") == "MRR"


def test_build_startup_outcomes_from_synthetic_snapshot() -> None:
    final = {
        "variables": {"runway_months": 8, "growth": 12, "mrr": 10000, "burn_rate": 15000},
        "derived": {"system_stability": 65},
    }
    provenance = [{"turn": 1, "pre_state": {"variables": {"runway_months": 10, "growth": 10}}}]
    brief = {
        "regime": {"level": "FRAGILE"},
        "confidence": {"level": "moderate"},
        "top_drivers": [{"name": "runway_months", "direction": "down"}],
        "kill_criteria": [],
        "hidden_assumptions": [],
    }
    profile = {"startup_name": "TestCo", "primary_goal": "profitability"}
    out = build_startup_outcomes(final, provenance, profile, brief)
    assert out["runway_months"] == 8
    assert "survival_probability" not in out
    rh = out["runway_health"]
    assert 0 <= rh["score"] <= 99
    assert rh["label"] == "Runway health (directional)"
    assert out["verdict_basis"]["simulation"]["runway_delta"] == -2.0
    assert out["disclaimer"]
    assert out["calculation_explanation"]["steps"]
    assert out["recommended_action"]
    assert out["best_case"].startswith("(Illustrative)")
    assert out["worst_case"].startswith("(Illustrative)")
