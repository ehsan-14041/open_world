"""Founder-friendly language in outcome recommendations."""

from __future__ import annotations

from ui.startup_outcomes import (
    FEATURED_DECISIONS,
    build_startup_outcomes,
    defoundify,
    founder_kill_summary,
    humanize_regime,
)

_ENGINE_JARGON = (
    "kill criterion",
    "CRISIS regime",
    "system_stability",
    "structural assumptions",
    "simulation flags",
    "primary driver",
)


def test_defoundify_strips_engine_jargon() -> None:
    raw = "System enters CRISIS regime — simulation flags kill criterion on system_stability"
    cleaned = defoundify(raw).lower()
    for term in _ENGINE_JARGON:
        assert term not in cleaned


def test_founder_kill_summary_readable() -> None:
    line = founder_kill_summary({
        "watch_variable": "runway_months",
        "threshold": "falls below 6",
        "signal": "Runway falls below 6 months",
        "why": "Decision becomes untenable",
    })
    assert "Cash runway" in line or "runway" in line.lower()
    assert "kill criterion" not in line.lower()


def test_wedge_hire_verdict_when_tight_runway() -> None:
    final = {"variables": {"runway_months": 5, "growth": 8, "mrr": 5000, "burn_rate": 12000}, "derived": {}}
    brief = {"regime": {"level": "FRAGILE"}, "confidence": {"level": "moderate"}, "kill_criteria": [], "top_drivers": []}
    out = build_startup_outcomes(final, [], {"startup_name": "Acme"}, brief, decision_id="hire_engineer")
    assert "don't hire" in out["one_line_recommendation"].lower()
    assert out["risk_level"] == "High"
    assert out["runway_headline"]
    assert out["why_now"]
    assert out["next_step"]


def test_wedge_includes_runway_delta_headline() -> None:
    initial = {"variables": {"runway_months": 12, "growth": 10}}
    final = {"variables": {"runway_months": 9.5, "growth": 11, "mrr": 8000, "burn_rate": 9000}, "derived": {}}
    brief = {"regime": {"level": "NORMAL"}, "confidence": {"level": "high"}, "kill_criteria": [], "top_drivers": []}
    out = build_startup_outcomes(final, [{"pre_state": initial}], {}, brief, initial_snapshot=initial, decision_id="hire_engineer")
    assert "lost" in out["runway_headline"].lower() or "gained" in out["runway_headline"].lower()
    assert out["one_line_recommendation"]


def test_featured_decisions_list() -> None:
    assert "hire_engineer" in FEATURED_DECISIONS
    assert "cut_burn" in FEATURED_DECISIONS


def test_humanize_regime() -> None:
    assert humanize_regime("CRISIS") == "Critical"
    assert humanize_regime("FRAGILE") == "Shaky"
