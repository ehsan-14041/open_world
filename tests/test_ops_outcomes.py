"""Tests for enterprise operations outcomes."""

from __future__ import annotations

from ui.ops_outcomes import (
    FEATURED_DECISIONS,
    build_comparison_card,
    build_ops_outcomes,
    dejargonize,
    humanize_regime,
    ops_kill_summary,
)


def test_dejargonize_strips_engine_jargon() -> None:
    raw = "System enters CRISIS regime — multi-agent simulation flags kill criterion"
    cleaned = dejargonize(raw).lower()
    assert "kill criterion" not in cleaned
    assert "multi-agent" not in cleaned


def test_ops_kill_summary_readable() -> None:
    line = ops_kill_summary({
        "watch_variable": "fill_rate",
        "signal": "Fill rate falls below 88%",
    })
    assert "Fill rate" in line


def test_increase_safety_stock_verdict_when_high_fill() -> None:
    final = {
        "variables": {
            "fill_rate": 0.96,
            "holding_cost_weekly": 5200,
            "stockout_risk": 0.08,
            "lead_time_days": 12,
        },
        "derived": {},
    }
    brief = {"regime": {"level": "NORMAL"}, "confidence": {"level": "moderate"}, "kill_criteria": [], "top_drivers": []}
    out = build_ops_outcomes(
        final, [], {"site_name": "Midwest DC"}, brief, decision_id="increase_safety_stock"
    )
    assert "don't" in out["one_line_recommendation"].lower() or "cautiously" in out["one_line_recommendation"].lower()
    assert out["service_level_headline"]
    assert out["cost_headline"]
    assert out["risk_headline"]
    assert out["why_now"]
    assert out["next_step"]


def test_service_level_delta_headline() -> None:
    initial = {"variables": {"fill_rate": 0.91, "holding_cost_weekly": 3000, "stockout_risk": 0.15}}
    final = {"variables": {"fill_rate": 0.94, "holding_cost_weekly": 3400, "stockout_risk": 0.12, "lead_time_days": 10}}
    brief = {"regime": {"level": "FRAGILE"}, "confidence": {"level": "moderate"}, "kill_criteria": [], "top_drivers": []}
    out = build_ops_outcomes(
        final, [{"pre_state": initial}], {}, brief,
        initial_snapshot=initial, decision_id="expedite_reorder",
    )
    assert "fill rate" in out["service_level_headline"].lower()
    assert out["one_line_recommendation"]


def test_bottleneck_and_lead_time_headlines() -> None:
    initial = {
        "variables": {
            "fill_rate": 0.91,
            "holding_cost_weekly": 4000,
            "stockout_risk": 0.15,
            "lead_time_days": 20,
            "backlog_weeks": 1.2,
            "capacity_utilization": 0.88,
        },
    }
    final = {
        "variables": {
            "fill_rate": 0.93,
            "holding_cost_weekly": 4200,
            "stockout_risk": 0.12,
            "lead_time_days": 16,
            "backlog_weeks": 0.8,
            "capacity_utilization": 0.85,
        },
        "derived": {},
    }
    brief = {"regime": {"level": "FRAGILE"}, "confidence": {"level": "moderate"}, "kill_criteria": [], "top_drivers": []}
    out = build_ops_outcomes(
        final, [], {}, brief,
        initial_snapshot=initial,
        decision_id="expedite_reorder",
    )
    assert out.get("lead_time_headline")
    assert out.get("bottleneck_headline")
    assert "days" in out["lead_time_headline"].lower()


def test_featured_decisions_list() -> None:
    assert "increase_safety_stock" in FEATURED_DECISIONS
    assert "expedite_reorder" in FEATURED_DECISIONS


def test_humanize_regime() -> None:
    assert humanize_regime("CRISIS") == "Critical"
    assert humanize_regime("FRAGILE") == "Constrained"


def test_comparison_card() -> None:
    final = {"variables": {"fill_rate": 0.93, "holding_cost_weekly": 4000, "stockout_risk": 0.1}}
    brief = {"regime": {"level": "NORMAL"}, "confidence": {"level": "high"}, "kill_criteria": [], "top_drivers": []}
    card = build_comparison_card(
        "expedite_reorder", "Expedite reorder", final, [], {}, brief,
    )
    assert card["service_level_headline"]
    assert card["decision_id"] == "expedite_reorder"
