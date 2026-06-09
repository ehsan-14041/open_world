"""Tests for operations decision library."""

from __future__ import annotations

from adapters.ops_scenario_builder import load_decision_templates


def test_decision_library_shape() -> None:
    decisions = load_decision_templates()
    assert len(decisions) == 12
    for d in decisions:
        assert d.get("id")
        assert d.get("label_en")
        assert d.get("move_en")
        assert d.get("horizon_weeks")
        assert isinstance(d.get("tradeoff_hint"), dict)


def test_featured_decisions_present() -> None:
    decisions = load_decision_templates()
    featured = [d["id"] for d in decisions if d.get("featured")]
    assert "increase_safety_stock" in featured
    assert "expedite_reorder" in featured
    assert "switch_supplier" in featured
    assert "reallocate_demand" in featured
