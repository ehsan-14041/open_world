"""Tests: scenario loads and validates (gulf_standoff, existing scenarios)."""

from __future__ import annotations

import json
from pathlib import Path

from schemas.scenario_schema import validate_scenario, normalize_scenario


def test_gulf_standoff_loads() -> None:
    path = Path(__file__).parent.parent / "config" / "scenarios" / "gulf_standoff.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    errors = validate_scenario(data)
    assert errors == []
    norm = normalize_scenario(data)
    assert "variable_specs" in norm
    assert "tension" in norm.get("variable_specs", {})
    assert "enable_meta_actions" in norm


def test_demo_scenario_loads() -> None:
    path = Path(__file__).parent.parent / "config" / "scenarios" / "demo_scenario.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    errors = validate_scenario(data)
    assert errors == []
