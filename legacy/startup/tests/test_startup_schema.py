"""Tests for startup profile schema."""

from __future__ import annotations

from schemas.startup_schema import validate_startup_profile, normalize_startup_profile


def test_validate_requires_type_and_stage() -> None:
    errors = validate_startup_profile({})
    assert any("startup_type" in e for e in errors)
    assert any("stage" in e for e in errors)


def test_validate_rejects_invalid_churn() -> None:
    errors = validate_startup_profile({
        "startup_type": "b2b_saas",
        "stage": "seed",
        "churn": 150,
    })
    assert any("churn" in e for e in errors)


def test_normalize_derives_runway_from_cash_and_burn() -> None:
    profile = normalize_startup_profile({
        "startup_type": "b2b_saas",
        "stage": "seed",
        "cash": 120000,
        "monthly_burn": 10000,
    })
    assert profile["runway_months"] == 12
    assert profile["monthly_burn"] == 10000


def test_normalize_derives_burn_from_runway() -> None:
    profile = normalize_startup_profile({
        "startup_type": "ai_saas",
        "stage": "pre_seed",
        "cash": 60000,
        "runway_months": 6,
    })
    assert profile["monthly_burn"] == 10000
