"""Ensure ops_profile path never uses the generic text-to-scenario pipeline."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("flask")

_root = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("ui_app", _root / "ui.py")
assert _spec and _spec.loader
ui_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui_app)
app = ui_app.app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_ops_brief_never_calls_parse_scenario_text(client) -> None:
    body = {
        "ops_profile": {
            "business_unit_type": "distribution",
            "inventory_on_hand": 12000,
            "weekly_demand": 800,
            "fill_rate": 0.94,
        },
        "decision_id": "increase_safety_stock",
        "dry_run": True,
        "save_snapshot": False,
        "save_to_journal": False,
    }

    def _boom(*_args, **_kwargs):
        raise AssertionError("parse_scenario_text must not run for ops_profile requests")

    with patch.object(ui_app, "parse_scenario_text", side_effect=_boom):
        r = client.post("/api/brief", json=body)
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["ok"]
    assert data["scenario"].get("ops_profile")
    assert "inventory_on_hand" in (data["scenario"].get("initial_state") or {})


def test_product_ui_does_not_import_legacy_startup() -> None:
    ui_source = (_root / "ui.py").read_text(encoding="utf-8")
    assert "startup_scenario_builder" not in ui_source
    assert "startup_outcomes" not in ui_source
    assert "startup_schema" not in ui_source


def test_ops_brief_requires_decision_id(client) -> None:
    body = {
        "ops_profile": {"business_unit_type": "distribution"},
        "dry_run": True,
    }
    r = client.post("/api/brief", json=body)
    assert r.status_code == 400
    assert "decision_id" in (r.get_json().get("error") or "").lower()
