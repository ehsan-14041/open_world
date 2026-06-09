"""Flask route availability tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

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


def test_home_page(client) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert b"Enterprise Operations Decision Simulator" in r.data or b"Simulate one operational decision" in r.data


def test_graph_page(client) -> None:
    r = client.get("/graph")
    assert r.status_code == 200


def test_ops_presets_api(client) -> None:
    r = client.get("/api/ops_presets")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"]
    assert len(data["presets"]) >= 5


def test_ops_decisions_api(client) -> None:
    r = client.get("/api/ops_decisions")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"]
    assert len(data["decisions"]) == 12


def test_health(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["service"] == "enterprise_ops_decision_simulator"


def test_product_mode_blocks_advanced(client) -> None:
    if not ui_app.PRODUCT_MODE:
        pytest.skip("product_mode disabled")
    r = client.get("/advanced")
    assert r.status_code == 403


def test_ops_decisions_include_editable_assumptions(client) -> None:
    r = client.get("/api/ops_decisions")
    data = r.get_json()
    stock = next(d for d in data["decisions"] if d["id"] == "increase_safety_stock")
    assert stock.get("editable_assumptions")
    assert stock["editable_assumptions"][0]["key"] == "reorder_quantity"


def test_journal_check_ins_api(client) -> None:
    r = client.get("/api/journal/check-ins")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"]
    assert "check_ins" in data
