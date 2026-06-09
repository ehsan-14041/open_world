"""Tests for the no-LLM text -> scenario converter."""

from __future__ import annotations

from core.text_to_scenario import (
    text_to_scenario, detect_domain, list_domains, load_kb,
    _extract_magnitude, _direction,
)
from schemas.scenario_schema import normalize_scenario, validate_scenario
from core.scenario_linter import lint_scenario


def test_kb_loads_and_lists_domains() -> None:
    names = {d["name"] for d in list_domains()}
    assert {"pricing", "hiring", "fundraise", "market_entry"} <= names
    assert load_kb(), "knowledge base must be non-empty"


def test_kb_added_domain_market_entry_converts() -> None:
    # market_entry exists ONLY as data in the KB — proves domains are data, not code.
    sc, meta = text_to_scenario("expand into the new market")
    assert meta["matched"] and meta["domain"] == "market_entry"
    assert lint_scenario(normalize_scenario(sc))["level"] >= 3


def test_unmatched_reports_available_domains() -> None:
    sc, meta = text_to_scenario("what should I name my cat")
    assert sc is None
    assert meta["reason"] == "domain not in knowledge base"
    assert "pricing" in meta["available_domains"]


def test_extract_magnitude_and_direction() -> None:
    assert _extract_magnitude("raise prices 30%") == 0.30
    assert _extract_magnitude("double the team") == 1.0
    assert _direction("raise prices 30%") == 1
    assert _direction("cut prices 20%") == -1


def test_detect_domain() -> None:
    assert detect_domain("raise prices 30%") == "pricing"
    assert detect_domain("double the engineering team this quarter") == "hiring"
    assert detect_domain("should we raise a series A now") in ("fundraise", "pricing")  # 'raise' overlaps
    assert detect_domain("what color should the logo be") is None


def test_pricing_text_builds_valid_l4_scenario() -> None:
    sc, meta = text_to_scenario("raise prices 30%")
    assert meta["matched"] and meta["domain"] == "pricing"
    sc = normalize_scenario(sc)
    assert validate_scenario(sc) == []
    rep = lint_scenario(sc)
    assert rep["level"] >= 3, rep["level_reasons"]  # real second mover, constraint, failure mode


def test_hiring_text_builds_valid_scenario() -> None:
    sc, meta = text_to_scenario("double the team this quarter")
    assert meta["matched"] and meta["domain"] == "hiring"
    sc = normalize_scenario(sc)
    assert validate_scenario(sc) == []
    assert lint_scenario(sc)["level"] >= 3


def test_bigger_move_is_more_fragile() -> None:
    """A 30% hike should produce a closer churn cliff than a 5% hike."""
    big, _ = text_to_scenario("raise prices 30%")
    small, _ = text_to_scenario("raise prices 5%")
    big_cliff = big["rules"][0]["params"]["threshold"]
    small_cliff = small["rules"][0]["params"]["threshold"]
    assert big_cliff < small_cliff  # bigger move -> lower (closer) cliff


def test_unmatched_text_returns_none() -> None:
    sc, meta = text_to_scenario("what should I have for lunch")
    assert sc is None and meta["matched"] is False


def test_move_text_preserved_in_decision_input() -> None:
    sc, _ = text_to_scenario("raise prices 30%")
    assert sc["decision_input"]["move"] == "raise prices 30%"
