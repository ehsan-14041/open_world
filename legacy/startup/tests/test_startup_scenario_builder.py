"""Tests for startup scenario builder."""

from __future__ import annotations

import json
from pathlib import Path

from adapters.startup_scenario_builder import (
    apply_assumption_overrides,
    build_scenario,
    get_decision_template,
    get_editable_assumptions,
    load_decision_templates,
)
from schemas.scenario_schema import validate_scenario
from schemas.startup_schema import normalize_startup_profile


def _sample_profile(**overrides) -> dict:
    base = normalize_startup_profile({
        "startup_name": "TestCo",
        "startup_type": "b2b_saas",
        "stage": "seed",
        "cash": 100000,
        "monthly_burn": 10000,
        "runway_months": 10,
        "mrr": 8000,
        "growth_rate": 12,
        "churn": 4,
    })
    base.update(overrides)
    return base


def test_build_scenario_valid_for_each_archetype() -> None:
    for stype in ("b2b_saas", "ai_saas", "marketplace", "mobile_app", "agency", "consumer_subscription"):
        sc = build_scenario(_sample_profile(startup_type=stype), get_decision_template("hire_engineer"))
        errors = validate_scenario(sc)
        assert errors == [], f"{stype}: {errors}"
        assert sc["initial_state"]["cash"] == 100000
        assert sc.get("startup_profile")


def test_build_scenario_maps_variables() -> None:
    sc = build_scenario(_sample_profile(), get_decision_template("cut_burn"))
    state = sc["initial_state"]
    assert state["mrr"] == 8000
    assert state["burn_rate"] == 10000
    assert state["runway_months"] == 10
    assert sc.get("decision_input", {}).get("move")


def test_editable_assumptions_for_hire() -> None:
    tmpl = get_decision_template("hire_engineer")
    assert tmpl is not None
    specs = get_editable_assumptions(tmpl)
    assert any(s["key"] == "monthly_hire_cost" for s in specs)
    assert specs[0]["value"] == 8000


def test_assumption_overrides_change_tradeoff() -> None:
    tmpl = get_decision_template("hire_engineer")
    assert tmpl is not None
    sc = build_scenario(
        _sample_profile(),
        tmpl,
        assumption_overrides={"monthly_hire_cost": 12000},
    )
    action = sc["action_tradeoffs"]["decision_hire_engineer"]
    assert action["burn_rate"] == 12000
    used = sc.get("assumptions_used") or []
    assert any(a["key"] == "monthly_hire_cost" and a["value"] == 12000 for a in used)


def test_apply_assumption_overrides_cut_burn_absolute() -> None:
    tmpl = get_decision_template("cut_burn")
    assert tmpl is not None
    hint, used = apply_assumption_overrides(
        tmpl["tradeoff_hint"], "cut_burn", {"monthly_savings": 7000}
    )
    assert hint["burn_rate"] == -7000
    assert any(a["value"] == 7000 for a in used)


def test_presets_file_loads() -> None:
    path = Path(__file__).resolve().parent.parent / "config" / "startup_presets.json"
    presets = json.loads(path.read_text(encoding="utf-8"))
    assert len(presets) >= 5
    for p in presets:
        profile = normalize_startup_profile(p["profile"])
        sc = build_scenario(profile, get_decision_template("hire_engineer"))
        assert not validate_scenario(sc)
