"""Tests for the Actor Archetype Library (Phase 3 — reacting agents).

Uses the shared `l4_scenario` factory (tests/conftest.py); the archetype "base" is the
canonical scenario with the second mover removed (founder only), so it starts below L3.
"""

from __future__ import annotations

from core.actor_archetypes import list_archetypes, build_archetype_agent, apply_archetypes
from core.scenario_linter import lint_scenario


def _base(l4_scenario) -> dict:
    """Canonical scenario minus its second mover -> a single-actor base (caps below L3)."""
    sc = l4_scenario()
    sc["initial_agents"] = [a for a in sc["initial_agents"] if a.get("name") == "founder"]
    return sc


def test_list_archetypes() -> None:
    names = {a["name"] for a in list_archetypes()}
    assert {"competitor", "customer", "regulator", "supplier"} <= names


def test_build_competitor_anchors_to_variables(l4_scenario) -> None:
    agent = build_archetype_agent("competitor", _base(l4_scenario))
    assert agent is not None and agent["role"] == "Competitor"
    # competitor wants to erode your position -> decrease_customers / decrease_mrr
    assert any(k.startswith("decrease_") for k in agent["objectives"])
    assert any(k in ("decrease_customers", "decrease_mrr") for k in agent["objectives"])


def test_archetype_without_matching_variable_is_skipped() -> None:
    sc = {"initial_state": {"temperature": 20}}  # no var a supplier cares about
    assert build_archetype_agent("supplier", sc) is None


def test_apply_archetypes_appends_and_dedupes(l4_scenario) -> None:
    sc, added, skipped = apply_archetypes(_base(l4_scenario), ["competitor", "founder"])
    assert "competitor" in added
    assert "founder" in skipped  # already present
    names = {a["name"] for a in sc["initial_agents"]}
    assert "competitor" in names and "founder" in names


def test_competitor_raises_completeness_to_l3(l4_scenario) -> None:
    # base has no second mover -> capped below L3; adding competitor unlocks it.
    before = lint_scenario(_base(l4_scenario))
    assert before["level"] < 3
    enriched, _a, _s = apply_archetypes(_base(l4_scenario), ["competitor"])
    after = lint_scenario(enriched)
    assert after["level"] >= 3, after["level_reasons"]


def test_original_scenario_not_mutated(l4_scenario) -> None:
    base = _base(l4_scenario)
    apply_archetypes(base, ["competitor", "regulator"])
    assert len(base["initial_agents"]) == 1  # original untouched
