from __future__ import annotations

"""
Propagation-aware planning fidelity tests.

These tests verify that TransitionKernel planning (`transition_planning`) uses
the same deterministic physics core as execution and that secondary effects
from causal propagation are aligned in a simple synthetic scenario.
"""

import math
from typing import Any

from core.transition_kernel import TransitionOptions, transition_planning
from schemas.delta_schema import Delta
from simulation.loop import SimulationLoop


def _propagation_scenario() -> dict[str, Any]:
    """
    Minimal generic scenario with a small causal chain:
    x -> y (positive), x -> z (negative).
    """
    return {
        "description": "Propagation test scenario (generic)",
        "initial_state": {"x": 0.0, "y": 0.0, "z": 0.0},
        "initial_agents": [
            {"name": "agent1", "role": "Actor", "objectives": {"x": 1.0}},
        ],
        "relations": [],
        "allowed_actions": ["increase_x"],
        "action_tradeoffs": {
            "increase_x": {"x": 10.0},
        },
        "causal_links": [
            {"from": "x", "to": "y", "polarity": "positive", "strength": 0.5},
            {"from": "x", "to": "z", "polarity": "negative", "strength": 0.25},
        ],
        "governance": {"strictness_level": 1},
        # Simple variable_specs so propagation has metadata but no domain semantics.
        "variable_specs": {
            "x": {"min": -100, "max": 100},
            "y": {"min": -100, "max": 100},
            "z": {"min": -100, "max": 100},
        },
    }


def test_transition_planning_propagation_matches_execution_structure() -> None:
    """
    Run transition_planning over a synthetic causal graph and compare with execution:
    - Both paths should produce non-zero secondary effects on y and z.
    - Signs of secondary effects must match between planning and execution.
    - Magnitudes should be within a loose tolerance (same deterministic core).
    """
    scenario = _propagation_scenario()
    base_snapshot = {
        "variables": dict(scenario["initial_state"]),
        "global_state": dict(scenario["initial_state"]),
        "causal_links": list(scenario["causal_links"]),
        "turn": 0,
        "variable_specs": dict(scenario["variable_specs"]),
    }
    delta_dict = {
        "numeric_updates": {"x": 10.0},
        "entity_updates": {},
        "new_entities": {},
        "relation_updates": [],
        "meta_proposals": [],
        "rationale": "test propagation",
        "effects_duration": None,
        "mitigation": None,
        "action_type": "increase_x",
    }

    # Planning path: deterministic physics via transition_planning
    options = TransitionOptions(
        mode="planning",
        enable_noise=False,
        enable_propagation=True,
        max_prop_hops=3,
    )
    planned_snapshot, prov = transition_planning(
        base_snapshot,
        delta_dict,
        causal_links=list(scenario["causal_links"]),
        variable_specs=dict(scenario["variable_specs"]),
        options=options,
    )
    planning_changes = prov.get("variable_changes") or []

    # Execution path: dry-run SimulationLoop with uncertainty disabled
    from unittest.mock import patch

    with patch("config.settings.ENABLE_UNCERTAINTY", False), patch(
        "core.world_model.ENABLE_UNCERTAINTY", False
    ):
        loop = SimulationLoop(scenario_data=scenario, dry_run=True)
        loop.step()
        final_snap = loop.world.snapshot()
        # Outcome from world.apply_delta is stored on the last provenance entry (Phase 2 wiring)
        last = loop._provenance[-1]
        outcome = last.get("outcome") or {}
        exec_changes = outcome.get("variable_changes") or []

    def _to_map(changes: list[dict[str, Any]]) -> dict[str, float]:
        out: dict[str, float] = {}
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            var = ch.get("var")
            delta = ch.get("delta")
            if isinstance(var, str) and isinstance(delta, (int, float)):
                out[var] = float(delta)
        return out

    planning_map = _to_map(planning_changes)
    exec_map = _to_map(exec_changes)

    # Both paths must have propagated to y and z (non-zero effects).
    for var in ("y", "z"):
        assert var in planning_map, f"planning missing secondary effect for {var}"
        assert var in exec_map, f"execution missing secondary effect for {var}"
        assert not math.isclose(planning_map[var], 0.0, abs_tol=1e-9)
        assert not math.isclose(exec_map[var], 0.0, abs_tol=1e-9)
        # Signs must match between planning and execution.
        assert planning_map[var] * exec_map[var] > 0, f"sign mismatch for {var}"
        # Magnitudes should be within a loose tolerance (same physics core).
        assert math.isclose(planning_map[var], exec_map[var], rel_tol=0.25), (
            f"magnitude mismatch for {var}: planning={planning_map[var]}, exec={exec_map[var]}"
        )

