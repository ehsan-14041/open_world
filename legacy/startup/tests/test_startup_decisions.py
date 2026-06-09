"""Tests for startup decision templates."""

from __future__ import annotations

import json
from pathlib import Path

from adapters.startup_scenario_builder import load_decision_templates


def test_startup_decisions_has_twelve_templates() -> None:
    path = Path(__file__).resolve().parent.parent / "config" / "startup_decisions.json"
    decisions = json.loads(path.read_text(encoding="utf-8"))
    assert len(decisions) == 12
    ids = {d["id"] for d in decisions}
    assert "hire_engineer" in ids
    assert "raise_seed" in ids
    assert "improve_retention" in ids


def test_each_decision_has_required_fields() -> None:
    for d in load_decision_templates():
        assert d.get("id")
        assert d.get("label_en")
        assert d.get("move_en")
        assert d.get("horizon_months")
