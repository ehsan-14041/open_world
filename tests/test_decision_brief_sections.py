"""Tests for decision brief four-section output from synthetic provenance."""

from __future__ import annotations

from ui.decision_brief import build_decision_brief


def _synthetic_provenance() -> list[dict]:
    return [
        {
            "turn": 1,
            "turn_record": {
                "propagation_trace": [
                    {"from": "price", "to": "demand", "hop": 1, "delta_contrib": 0.4},
                    {"from": "demand", "to": "revenue", "hop": 2, "delta_contrib": -0.55},
                    {"from": "revenue", "to": "runway", "hop": 3, "delta_contrib": -0.3},
                ],
                "delta_applied": {"price": 5.0, "demand": -3.0, "revenue": -2.0},
            },
            "narrative": {
                "turn_summary": "Price increase reduced demand.",
                "outcome_assessment": {"outcome": "Mixed Outcome"},
                "key_drivers": ["Demand: -3.0", "Revenue: -2.0"],
                "hidden_costs": ["Sales cycle lengthens"],
                "tags": [{"kind": "regime", "value": "FRAGILE"}],
                "causal_chain": [
                    {
                        "actor": "ceo",
                        "action": "raise_price",
                        "chain": [("price", 5.0), ("demand", -3.0), ("revenue", -2.0)],
                    }
                ],
            },
        },
    ]


def _synthetic_scenario() -> dict:
    return {
        "description": "SaaS pricing decision",
        "decision_input": {
            "move": "Raise prices 30%",
            "actors": ["existing customers"],
            "constraints": {"runway_months": 9},
            "horizon_months": 6,
        },
        "variables": [
            {"name": "price", "min": 0, "max": 100},
            {"name": "demand", "min": 0, "max": 100},
            {"name": "revenue", "min": 0, "max": 100},
            {"name": "runway", "min": 0, "max": 24},
        ],
    }


def test_build_decision_brief_populates_four_sections() -> None:
    final = {
        "variables": {"price": 65, "demand": 40, "revenue": 50},
        "derived": {"system_stability": 55, "dissatisfaction": 45},
    }
    brief = build_decision_brief(
        final,
        _synthetic_provenance(),
        _synthetic_scenario(),
        agents_list=[],
    )

    assert brief["decision"]["move"] == "Raise prices 30%"
    assert brief["decision"]["horizon_months"] == 6
    assert brief["what_likely_happens"] or brief["outcome"]

    assert isinstance(brief["top_drivers"], list)
    assert len(brief["top_drivers"]) >= 1
    assert "name" in brief["top_drivers"][0]

    assert isinstance(brief["second_order_effects"], list)
    assert len(brief["second_order_effects"]) >= 1
    effect = brief["second_order_effects"][0]
    assert "effect" in effect and "trigger" in effect and "hops" in effect

    assert isinstance(brief["hidden_assumptions"], list)
    assert len(brief["hidden_assumptions"]) >= 1

    assert isinstance(brief["kill_criteria"], list)
    assert len(brief["kill_criteria"]) >= 1

    # Backward-compat aliases
    assert isinstance(brief["key_drivers"], list)
    assert isinstance(brief["hidden_risks"], list)


def test_build_decision_brief_legacy_path_empty_decision() -> None:
    scenario = {"description": "Free text scenario without structured input"}
    brief = build_decision_brief({}, [], scenario, agents_list=[])
    assert brief["decision"]["move"] == ""
    assert brief["top_drivers"] == [] or isinstance(brief["top_drivers"], list)


def test_build_decision_brief_ops_recommended_fields() -> None:
    scenario = {
        "description": "Inventory buffer decision",
        "ops_profile": {
            "site_name": "Midwest DC",
            "business_unit_type": "distribution",
            "inventory_on_hand": 12000,
            "weekly_demand": 800,
            "fill_rate": 0.92,
            "planning_goal": "hit service target",
        },
        "decision_input": {"move": "Increase safety stock", "horizon_months": 2},
    }
    final = {
        "variables": {
            "fill_rate": 0.94,
            "holding_cost_weekly": 4200,
            "stockout_risk": 0.1,
            "lead_time_days": 14,
        },
        "derived": {"system_stability": 60},
    }
    provenance = [{"turn": 1, "pre_state": {"variables": {"fill_rate": 0.91, "holding_cost_weekly": 3800}}}]
    brief = build_decision_brief(final, provenance, scenario, agents_list=[])
    assert "recommended_action" in brief
    assert "best_case" in brief
    assert "worst_case" in brief
    assert brief["recommended_action"]
