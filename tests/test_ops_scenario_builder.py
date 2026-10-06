"""Tests for operations scenario builder."""

from __future__ import annotations

from adapters.ops_scenario_builder import (
    build_scenario,
    get_decision_template,
    get_editable_assumptions,
    load_decision_templates,
)
from schemas.ops_schema import normalize_ops_profile


def test_load_decision_templates() -> None:
    templates = load_decision_templates()
    assert len(templates) == 12


def test_build_scenario_has_ops_variables() -> None:
    profile = normalize_ops_profile({
        "business_unit_type": "distribution",
        "inventory_on_hand": 12000,
        "weekly_demand": 800,
        "fill_rate": 0.94,
    })
    template = get_decision_template("increase_safety_stock")
    assert template is not None
    scenario = build_scenario(profile, template)
    state = scenario["initial_state"]
    assert "inventory_on_hand" in state
    assert "fill_rate" in state
    assert "lead_time_days" in state
    assert scenario.get("ops_profile")
    assert scenario.get("decision_template_id") == "increase_safety_stock"
    assert scenario.get("product_decision_action") == "decision_increase_safety_stock"
    allowed = scenario.get("allowed_actions") or []
    assert allowed[0] == "decision_increase_safety_stock"
    assert scenario.get("governance", {}).get("stability_variable") == "fill_rate"


def test_build_scenario_includes_causal_links() -> None:
    profile = normalize_ops_profile({"business_unit_type": "manufacturing"})
    scenario = build_scenario(profile, get_decision_template("expedite_reorder"))
    links = scenario.get("causal_links") or []
    assert any(l.get("from") == "lead_time_days" for l in links)


def test_editable_assumptions_for_expedite() -> None:
    template = get_decision_template("expedite_reorder")
    specs = get_editable_assumptions(template)
    assert specs
    assert specs[0]["key"] == "lead_time_reduction"
