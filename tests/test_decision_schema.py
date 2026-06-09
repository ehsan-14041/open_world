"""Tests for structured decision input schema and adapter."""

from __future__ import annotations

import pytest

from schemas.decision_schema import (
    VALID_HORIZONS,
    validate_decision_input,
    decision_to_scenario_text,
    normalize_decision_input,
)


def test_validate_requires_move() -> None:
    errors = validate_decision_input({})
    assert any("move" in e for e in errors)


def test_validate_rejects_non_object() -> None:
    errors = validate_decision_input("not a dict")
    assert errors == ["decision_input must be a JSON object"]


def test_validate_accepts_minimal_valid() -> None:
    assert validate_decision_input({"move": "Raise prices 30%"}) == []


def test_validate_horizon_must_be_allowed() -> None:
    errors = validate_decision_input({"move": "Pivot", "horizon_months": 18})
    assert any("horizon_months" in e for e in errors)
    assert list(VALID_HORIZONS) == [3, 6, 12, 24]
    assert validate_decision_input({"move": "Pivot", "horizon_months": 24}) == []


def test_validate_actors_must_be_strings() -> None:
    errors = validate_decision_input({"move": "Hire", "actors": ["ok", ""]})
    assert any("actors[1]" in e for e in errors)


def test_decision_to_scenario_text_includes_all_fields() -> None:
    d = {
        "move": "Raise prices 30%",
        "actors": ["existing customers", "sales team"],
        "constraints": {"runway_months": 9, "budget": "$500K"},
        "horizon_months": 6,
        "context": "B2B SaaS with 18 months runway.",
    }
    text = decision_to_scenario_text(d)
    assert "Raise prices 30%" in text
    assert "existing customers" in text
    assert "runway: 9 months" in text
    assert "6 months" in text
    assert "B2B SaaS" in text


def test_normalize_decision_input_cleans_and_defaults() -> None:
    raw = {
        "move": "  Cut prices 20%  ",
        "actors": ["  customers ", ""],
        "constraints": {"budget": " $1M ", "team_size": "8", "runway_months": "12"},
        "horizon_months": 99,
        "context": "  background  ",
    }
    out = normalize_decision_input(raw)
    assert out["move"] == "Cut prices 20%"
    assert out["actors"] == ["customers"]
    assert out["constraints"]["budget"] == "$1M"
    assert out["constraints"]["team_size"] == 8
    assert out["constraints"]["runway_months"] == 12
    assert out["horizon_months"] == 6  # invalid horizon reset to default
    assert out["context"] == "background"
