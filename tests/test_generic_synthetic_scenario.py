from __future__ import annotations

"""
Generic synthetic scenario tests + backward-compat checks for legacy turn-record fields.
"""

import math
from typing import Any
from unittest.mock import patch

from simulation.loop import SimulationLoop


def _generic_scenario() -> dict[str, Any]:
    return {
        "description": "Generic synthetic scenario for provenance/backcompat tests",
        "initial_state": {"x": 10.0, "y": -5.0, "z": 0.0, "flow_a": 0.0},
        "initial_agents": [
            {"name": "agent1", "role": "Actor", "objectives": {"x": 0.5, "y": 0.5}},
        ],
        "relations": [],
        "allowed_actions": ["increase_x", "increase_y"],
        "action_tradeoffs": {
            "increase_x": {"x": 2.0},
            "increase_y": {"y": 1.5},
        },
        "causal_links": [
            {"from": "x", "to": "z", "polarity": "positive", "strength": 0.4},
            {"from": "y", "to": "flow_a", "polarity": "negative", "strength": 0.3},
        ],
        "governance": {"strictness_level": 1},
        "variable_specs": {
            "x": {"min": -100, "max": 100},
            "y": {"min": -100, "max": 100},
            "z": {"min": -100, "max": 100},
            "flow_a": {"min": -100, "max": 100, "behavior_type": "FLOW"},
        },
    }


def test_generic_scenario_transition_provenance_and_no_nans() -> None:
    """
    Run a few dry-run steps and assert:
    - No NaN/Inf in world variables.
    - Each provenance entry has a transition_provenance block.
    - When a non-zero delta_applied exists, final_variable_changes is non-empty.
    """
    scenario = _generic_scenario()

    with patch("config.settings.ENABLE_UNCERTAINTY", False), patch(
        "core.world_model.ENABLE_UNCERTAINTY", False
    ):
        loop = SimulationLoop(scenario_data=scenario, dry_run=True)
        result = loop.run(steps=3, return_provenance=True, silent=True)

    final = result["final"]
    vars_final = final.get("variables") or final.get("global_state") or {}
    for v in vars_final.values():
        if isinstance(v, float):
            assert not (math.isnan(v) or math.isinf(v)), "world variables must not contain NaN/Inf"

    provenance = result["provenance"]
    assert isinstance(provenance, list) and provenance

    for entry in provenance:
        tp = entry.get("transition_provenance")
        assert isinstance(tp, dict), "expected transition_provenance dict on each entry"
        tr = entry.get("turn_record") or {}
        delta_applied = tr.get("delta_applied") or {}
        final_changes = tp.get("final_variable_changes") or []
        if delta_applied:
            assert final_changes, "final_variable_changes must be non-empty when delta_applied is non-zero"


def test_legacy_turn_record_fields_and_transition_provenance_alignment() -> None:
    """
    Backward-compatibility guard:
    - Legacy turn_record fields remain populated.
    - TransitionProvenance.constrained_delta matches turn_record.delta_applied.
    """
    scenario = _generic_scenario()

    with patch("config.settings.ENABLE_UNCERTAINTY", False), patch(
        "core.world_model.ENABLE_UNCERTAINTY", False
    ):
        loop = SimulationLoop(scenario_data=scenario, dry_run=True)
        result = loop.run(steps=2, return_provenance=True, silent=True)

    provenance = result["provenance"]
    last = provenance[-1]
    tr = last.get("turn_record") or {}

    # Legacy turn_record fields
    for key in (
        "delta_applied",
        "delta_after_merge",
        "self_effect_per_agent",
        "propagation_trace",
        "pre_state",
        "post_state",
    ):
        assert key in tr, f"turn_record missing legacy field {key!r}"

    for key in ("variable_changes", "events_triggered", "rule_activations", "shock"):
        assert key in last, f"provenance entry missing top-level field {key!r}"

    tp = last.get("transition_provenance")
    assert isinstance(tp, dict)

    constrained_delta = tp.get("constrained_delta") or {}
    delta_applied = tr.get("delta_applied") or {}
    assert constrained_delta == delta_applied, "constrained_delta must match turn_record.delta_applied"

