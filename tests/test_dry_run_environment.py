"""Tests: dry-run 3 turns with environment agent enabled (rule-based fallback)."""

from __future__ import annotations

import json
from pathlib import Path

from simulation.loop import SimulationLoop


def test_dry_run_environment_agent() -> None:
    """Dry-run 3 turns with environment agent enabled. Uses rule-based fallback."""
    scenario_path = Path(__file__).parent.parent / "config" / "scenarios" / "gulf_standoff.json"
    loop = SimulationLoop(
        scenario_path=str(scenario_path),
        dry_run=True,
        enable_environment_agent=True,
    )
    result = loop.run(steps=3, silent=True)
    assert result is not None
    variables = result.get("variables") or result.get("global_state") or {}
    assert isinstance(variables, dict)
    assert len(loop._provenance) == 3
    # Environment agent may have proposed events (check provenance has environment_proposed key)
    for entry in loop._provenance:
        assert "turn" in entry
        assert "environment_proposed" in entry or "proposals" in entry


def test_existing_scenario_still_runs() -> None:
    """Existing demo scenario runs unchanged."""
    scenario_path = Path(__file__).parent.parent / "config" / "scenarios" / "demo_scenario.json"
    loop = SimulationLoop(
        scenario_path=str(scenario_path),
        dry_run=True,
    )
    result = loop.run(steps=2, silent=True)
    assert result is not None
    variables = result.get("variables") or result.get("global_state") or {}
    assert "cash" in variables or "growth" in variables or len(variables) > 0
