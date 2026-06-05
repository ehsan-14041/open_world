"""Tests for decision preset templates."""

from __future__ import annotations

import json
from pathlib import Path


def test_decision_presets_file_has_business_templates() -> None:
    path = Path(__file__).resolve().parent.parent / "config" / "decision_presets.json"
    presets = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(presets, list)
    assert len(presets) >= 5
    ids = {p["id"] for p in presets}
    assert {"pricing", "hiring", "expansion"}.issubset(ids)
    pricing = next(p for p in presets if p["id"] == "pricing")
    assert "revenue" in pricing["context_en"].lower() or "retention" in pricing["context_en"].lower()
    assert pricing["constraints"].get("runway_months")
