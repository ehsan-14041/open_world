"""End-to-end test for operations /api/brief path."""

from __future__ import annotations

import importlib.util
import json
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


def test_ops_brief_e2e(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_app, "_get_snapshot_dir", lambda: tmp_path)

    presets_path = Path(__file__).resolve().parent.parent / "config" / "ops_presets.json"
    preset = json.loads(presets_path.read_text(encoding="utf-8"))[1]

    body = {
        "ops_profile": preset["profile"],
        "decision_id": "increase_safety_stock",
        "compare_decision_id": "expedite_reorder",
        "steps": 4,
        "dry_run": True,
        "save_snapshot": True,
        "save_to_journal": False,
    }
    r = client.post("/api/brief", json=body)
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data["ok"]
    assert data["brief"]["what_likely_happens"] is not None or data["brief"]["recommended_action"]
    assert data["outcomes"]["service_level_headline"]
    assert data["outcomes"]["cost_headline"]
    assert data["turn_trace"]
    assert data.get("snapshot_id")
    assert (tmp_path / f"snapshot_{data['snapshot_id']}.json").exists()
    assert data["outcomes"].get("disclaimer")
    assert data["outcomes"].get("calculation_explanation")
    assert data.get("decision_comparison")

    from simulation.loop import SimulationLoop
    from adapters.ops_scenario_builder import build_scenario, get_decision_template

    profile = preset["profile"]
    template = get_decision_template("increase_safety_stock")
    scenario = build_scenario(profile, template)
    loop = SimulationLoop(scenario_data=scenario, dry_run=True)
    result = loop.run(steps=4, return_provenance=True, silent=True)
    prov = result.get("provenance") or []
    assert prov, "expected provenance from simulation"
    first_turn = prov[0]
    chosen = (first_turn.get("turn_record") or {}).get("chosen_actions") or []
    action_ids = [c.get("action_id") for c in chosen if isinstance(c, dict)]
    assert "decision_increase_safety_stock" in action_ids
    assert first_turn.get("forced_product_decision") is True


def test_brief_with_assumption_overrides(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_app, "_get_snapshot_dir", lambda: tmp_path)
    preset = json.loads(
        (Path(__file__).resolve().parent.parent / "config" / "ops_presets.json").read_text(encoding="utf-8")
    )[0]
    body = {
        "ops_profile": preset["profile"],
        "decision_id": "increase_safety_stock",
        "assumption_overrides": {"reorder_quantity": 5000},
        "steps": 4,
        "dry_run": True,
        "save_snapshot": False,
    }
    r = client.post("/api/brief", json=body)
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"]
    assert data.get("assumptions_used")
    assert any(a["value"] == 5000 for a in data["assumptions_used"])


def test_brief_saves_journal(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ui_app, "_get_snapshot_dir", lambda: tmp_path)
    journal_dir = tmp_path / "decisions"
    journal_dir.mkdir(parents=True)
    import core.decision_journal as dj

    monkeypatch.setattr(dj, "_JOURNAL_DIR", journal_dir)

    preset = json.loads(
        (Path(__file__).resolve().parent.parent / "config" / "ops_presets.json").read_text(encoding="utf-8")
    )[0]
    body = {
        "ops_profile": preset["profile"],
        "decision_id": "expedite_reorder",
        "steps": 4,
        "dry_run": True,
        "save_snapshot": False,
        "save_to_journal": True,
    }
    r = client.post("/api/brief", json=body)
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("journal_id")
    assert data.get("check_in_due_days") == 30
