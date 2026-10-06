"""Enterprise operations language in outcome recommendations."""

from __future__ import annotations

from ui.ops_outcomes import build_ops_outcomes, dejargonize

_BANNED_TERMS = (
    "runway",
    "mrr",
    "founder",
    "seed round",
    "churn",
    "simulation engine",
    "multi-agent",
)

_REQUIRED_TERMS = (
    "service",
    "fill rate",
    "inventory",
    "lead time",
    "holding cost",
    "stockout",
)


def test_outcomes_avoid_startup_jargon() -> None:
    final = {
        "variables": {
            "fill_rate": 0.89,
            "holding_cost_weekly": 4500,
            "stockout_risk": 0.22,
            "lead_time_days": 18,
        },
        "derived": {},
    }
    brief = {"regime": {"level": "FRAGILE"}, "confidence": {"level": "moderate"}, "kill_criteria": [], "top_drivers": []}
    out = build_ops_outcomes(
        final, [], {"site_name": "East Plant"}, brief, decision_id="expedite_reorder"
    )
    combined = " ".join([
        out["one_line_recommendation"],
        out["why_now"],
        out["next_step"],
        out["service_level_headline"],
        out["disclaimer"],
    ]).lower()
    for term in _BANNED_TERMS:
        assert term not in combined, f"Found banned term: {term}"


def test_outcomes_use_ops_language() -> None:
    final = {
        "variables": {"fill_rate": 0.92, "holding_cost_weekly": 3000, "stockout_risk": 0.12},
        "derived": {},
    }
    brief = {"regime": {"level": "NORMAL"}, "confidence": {"level": "high"}, "kill_criteria": [], "top_drivers": []}
    out = build_ops_outcomes(final, [], {}, brief, decision_id="switch_supplier")
    combined = (out["service_level_headline"] + out["cost_headline"] + out["risk_headline"]).lower()
    assert "fill rate" in combined or "holding" in combined or "stockout" in combined


def test_dejargonize_rewrites_simulation_phrases() -> None:
    assert "scenario" in dejargonize("in this simulation").lower()
