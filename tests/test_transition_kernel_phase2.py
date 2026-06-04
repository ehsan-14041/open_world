from __future__ import annotations

import unittest
from unittest.mock import patch

from core.transition_kernel import TransitionOptions, transition_planning
from schemas.delta_schema import Delta
from simulation.loop import SimulationLoop


def _minimal_deterministic_scenario() -> dict:
    return {
        "description": "TransitionKernel Phase 2 test scenario",
        "initial_state": {"x": 50.0, "y": 30.0},
        "initial_agents": [
            {"name": "agent1", "role": "Actor", "objectives": {"x": 0.6, "y": 0.4}},
        ],
        "relations": [],
        "allowed_actions": ["increase_x"],
        "action_tradeoffs": {
            "increase_x": {"x": 5.0},
        },
        "causal_links": [],
        "governance": {"strictness_level": 1},
    }


class TestTransitionKernelPhase2(unittest.TestCase):
    def test_planning_matches_execution_deterministic(self) -> None:
        scenario = _minimal_deterministic_scenario()
        base_snapshot = {
            "variables": dict(scenario["initial_state"]),
            "global_state": dict(scenario["initial_state"]),
            "causal_links": [],
            "turn": 0,
        }
        delta_dict = {
            "numeric_updates": {"x": 5.0},
            "entity_updates": {},
            "new_entities": {},
            "relation_updates": [],
            "meta_proposals": [],
            "rationale": "test",
            "effects_duration": None,
            "mitigation": None,
            "action_type": "increase_x",
        }

        options = TransitionOptions(mode="planning", enable_noise=False)
        planned_snapshot, _prov = transition_planning(
            base_snapshot,
            delta_dict,
            causal_links=[],
            variable_specs={},
            options=options,
        )
        vars_planning = planned_snapshot.get("variables") or planned_snapshot.get("global_state") or {}

        with patch("config.settings.ENABLE_UNCERTAINTY", False), patch(
            "core.world_model.ENABLE_UNCERTAINTY", False
        ):
            loop = SimulationLoop(scenario_data=scenario, dry_run=True)
            loop.step()
            final_snap = loop.world.snapshot()

        vars_execution = final_snap.get("variables") or final_snap.get("global_state") or {}
        self.assertIn("x", vars_planning)
        self.assertIn("x", vars_execution)
        self.assertAlmostEqual(
            float(vars_planning["x"]),
            float(vars_execution["x"]),
            msg="Planning vs execution mismatch for variable x in deterministic mode.",
        )

    def test_transition_provenance_attached_and_complete(self) -> None:
        scenario = _minimal_deterministic_scenario()
        with patch("config.settings.ENABLE_UNCERTAINTY", False), patch(
            "core.world_model.ENABLE_UNCERTAINTY", False
        ):
            loop = SimulationLoop(scenario_data=scenario, dry_run=True)
            loop.step()

        self.assertGreaterEqual(len(loop._provenance), 1)
        last = loop._provenance[-1]
        tp = last.get("transition_provenance")
        self.assertIsInstance(tp, dict)
        self.assertIn("proposed_delta", tp)
        self.assertIn("constrained_delta", tp)
        self.assertIn("final_variable_changes", tp)
        self.assertIn("effect_records", tp)

        constrained = tp.get("constrained_delta") or {}
        final_changes = tp.get("final_variable_changes") or []
        self.assertIsInstance(constrained, dict)
        self.assertIsInstance(final_changes, list)
        if constrained:
            self.assertGreater(
                len(final_changes),
                0,
                msg="final_variable_changes should not be empty when a constrained_delta was applied.",
            )


