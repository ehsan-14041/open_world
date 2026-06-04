"""
Deterministic regression guard: run same scenario twice with ENABLE_UNCERTAINTY=False
and fixed RANDOM_SEED; assert final world_state, delta_applied, and dashboard
aggregate_belief_error are identical. Fail loudly on mismatch.
"""

from __future__ import annotations

import random
import unittest
from unittest.mock import patch

from ui.dashboard_payload import build_dashboard_payload
from simulation.loop import SimulationLoop


def _minimal_deterministic_scenario() -> dict:
    """Minimal scenario for deterministic dry-run (no LLM)."""
    return {
        "description": "Determinism test scenario",
        "initial_state": {"x": 50.0, "y": 30.0},
        "initial_agents": [
            {"name": "agent1", "role": "Actor", "objectives": {"x": 0.6, "y": 0.4}},
        ],
        "relations": [],
        "allowed_actions": ["increase_x", "decrease_x", "increase_y", "decrease_y"],
        "action_tradeoffs": {
            "increase_x": {"x": 5.0},
            "decrease_x": {"x": -5.0},
            "increase_y": {"y": 3.0},
            "decrease_y": {"y": -3.0},
        },
        "causal_links": [],
        "governance": {"strictness_level": 1},
    }


def _agents_list_from_loop(loop: SimulationLoop) -> list[dict]:
    """Build agents_list for build_dashboard_payload from loop.agents."""
    out = []
    for a in loop.agents:
        name = getattr(a, "name", None)
        if not name:
            continue
        mem = getattr(a, "memory", None)
        beliefs = getattr(mem, "beliefs", None) if mem else None
        if not isinstance(beliefs, dict):
            beliefs = {}
        out.append({"name": name, "belief_state": beliefs})
    return out


class TestDeterminism(unittest.TestCase):
    """Deterministic regression: two runs must produce identical outputs."""

    def test_twenty_turns_deterministic_identical(self) -> None:
        """Run 20 turns with ENABLE_UNCERTAINTY=False and fixed seed, twice; assert identical."""
        scenario = _minimal_deterministic_scenario()
        steps = 20
        seed = 42

        # Patch so both runs use deterministic mode (no uncertainty, fixed seed)
        uncertainty_false = patch("config.settings.ENABLE_UNCERTAINTY", False)
        seed_42 = patch("config.settings.RANDOM_SEED", seed)
        # Also patch where world_model and action_interpreter read uncertainty
        wm_unc = patch("core.world_model.ENABLE_UNCERTAINTY", False)
        ai_unc = patch("core.action_interpreter.ENABLE_UNCERTAINTY", False)
        ai_seed = patch("core.action_interpreter.RANDOM_SEED", seed)

        with uncertainty_false, seed_42, wm_unc, ai_unc, ai_seed:
            random.seed(seed)
            loop_a = SimulationLoop(scenario_data=scenario, dry_run=True)
            result_a = loop_a.run(steps=steps, return_provenance=True, silent=True)
            self.assertIsInstance(result_a, dict)
            self.assertIn("final", result_a)
            self.assertIn("provenance", result_a)

            random.seed(seed)
            loop_b = SimulationLoop(scenario_data=scenario, dry_run=True)
            result_b = loop_b.run(steps=steps, return_provenance=True, silent=True)
            self.assertIsInstance(result_b, dict)
            self.assertIn("final", result_b)
            self.assertIn("provenance", result_b)

        # --- Assert: final world_state identical ---
        final_a = result_a["final"]
        final_b = result_b["final"]
        vars_a = final_a.get("variables") or final_a.get("global_state") or {}
        vars_b = final_b.get("variables") or final_b.get("global_state") or {}
        self.assertEqual(
            vars_a,
            vars_b,
            "DETERMINISM FAIL: final world_state (variables) must be identical between runs.",
        )

        # --- Assert: delta_applied for last turn identical ---
        prov_a = result_a["provenance"]
        prov_b = result_b["provenance"]
        self.assertGreaterEqual(len(prov_a), 1)
        self.assertGreaterEqual(len(prov_b), 1)
        last_a = prov_a[-1]
        last_b = prov_b[-1]
        tr_a = last_a.get("turn_record") or {}
        tr_b = last_b.get("turn_record") or {}
        delta_a = tr_a.get("delta_applied") or {}
        delta_b = tr_b.get("delta_applied") or {}
        self.assertEqual(
            delta_a,
            delta_b,
            "DETERMINISM FAIL: last turn delta_applied must be identical between runs.",
        )

        # --- Assert: dashboard aggregate_belief_error identical ---
        agents_list_a = _agents_list_from_loop(loop_a)
        agents_list_b = _agents_list_from_loop(loop_b)
        payload_a = build_dashboard_payload(
            final_a,
            last_a,
            scenario,
            agents_list_a,
            provenance_history=prov_a,
        )
        payload_b = build_dashboard_payload(
            final_b,
            last_b,
            scenario,
            agents_list_b,
            provenance_history=prov_b,
        )
        bam_a = payload_a.get("belief_alignment_metrics") or {}
        bam_b = payload_b.get("belief_alignment_metrics") or {}
        agg_a = bam_a.get("aggregate_belief_error")
        agg_b = bam_b.get("aggregate_belief_error")
        self.assertEqual(
            agg_a,
            agg_b,
            "DETERMINISM FAIL: dashboard aggregate_belief_error must be identical between runs.",
        )
