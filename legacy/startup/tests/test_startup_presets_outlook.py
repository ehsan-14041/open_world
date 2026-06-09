"""Preset credibility: healthy, strained, and uncertain outlook coverage."""

from __future__ import annotations

import json
from pathlib import Path


def test_presets_cover_three_outlooks() -> None:
    path = Path(__file__).resolve().parent.parent / "config" / "startup_presets.json"
    presets = json.loads(path.read_text(encoding="utf-8"))
    outlooks = {p.get("outlook") for p in presets}
    assert {"healthy", "strained", "uncertain"}.issubset(outlooks)


def test_first_preset_is_healthy_demo() -> None:
    path = Path(__file__).resolve().parent.parent / "config" / "startup_presets.json"
    presets = json.loads(path.read_text(encoding="utf-8"))
    assert presets[0].get("outlook") == "healthy"
    assert presets[0].get("id") == "ai_saas_runway"
