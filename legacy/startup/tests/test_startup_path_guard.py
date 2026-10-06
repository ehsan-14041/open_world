"""Ensure startup_profile path never uses the generic text-to-scenario pipeline."""

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


def test_startup_brief_never_calls_parse_scenario_text(client) -> None:
    body = {
        "startup_profile": {
            "startup_type": "b2b_saas",
            "stage": "seed",
            "cash": 100000,
            "monthly_burn": 10000,
            "runway_months": 10,
        },
        "decision_id": "hire_engineer",
        "dry_run": True,
        "save_snapshot": False,
        "save_to_journal": False,
    }

    def _boom(*_args, **_kwargs):
        raise AssertionError("parse_scenario_text must not run for startup_profile requests")

    with patch.object(ui_app, "parse_scenario_text", side_effect=_boom):
        r = client.post("/api/brief", json=body)
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["ok"]
    assert data["scenario"].get("startup_profile")
    assert "cash" in (data["scenario"].get("initial_state") or {})


def test_startup_brief_requires_decision_id(client) -> None:
    body = {
        "startup_profile": {"startup_type": "b2b_saas", "stage": "seed"},
        "dry_run": True,
    }
    r = client.post("/api/brief", json=body)
    assert r.status_code == 400
    assert "decision_id" in (r.get_json().get("error") or "").lower()
