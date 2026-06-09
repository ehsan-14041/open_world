"""Tests for operations preset outlook tags."""

from __future__ import annotations

import json
from pathlib import Path


def test_presets_have_outlook_tags() -> None:
    path = Path(__file__).resolve().parent.parent / "config" / "ops_presets.json"
    presets = json.loads(path.read_text(encoding="utf-8"))
    assert len(presets) >= 5
    outlooks = {p["outlook"] for p in presets}
    assert "stable" in outlooks
    assert "strained" in outlooks
    assert "uncertain" in outlooks


def test_presets_have_ops_profile_fields() -> None:
    path = Path(__file__).resolve().parent.parent / "config" / "ops_presets.json"
    presets = json.loads(path.read_text(encoding="utf-8"))
    for p in presets:
        profile = p["profile"]
        assert profile.get("business_unit_type")
        assert profile.get("inventory_on_hand") is not None
        assert profile.get("fill_rate") is not None
