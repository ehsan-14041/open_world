"""Tests for operations profile schema."""

from __future__ import annotations

from schemas.ops_schema import validate_ops_profile, normalize_ops_profile


def test_validate_requires_business_unit_type() -> None:
    errors = validate_ops_profile({})
    assert any("business_unit_type" in e for e in errors)


def test_validate_rejects_invalid_fill_rate() -> None:
    errors = validate_ops_profile({
        "business_unit_type": "distribution",
        "fill_rate": 1.5,
    })
    assert any("fill_rate" in e for e in errors)


def test_normalize_derives_stockout_risk() -> None:
    profile = normalize_ops_profile({
        "business_unit_type": "distribution",
        "inventory_on_hand": 5000,
        "weekly_demand": 1000,
        "fill_rate": 0.85,
    })
    assert profile["stockout_risk"] > 0
    assert profile["planning_horizon_weeks"] == 8


def test_normalize_defaults_safety_stock() -> None:
    profile = normalize_ops_profile({
        "business_unit_type": "manufacturing",
        "inventory_on_hand": 10000,
        "weekly_demand": 500,
    })
    assert profile["safety_stock"] >= 500
