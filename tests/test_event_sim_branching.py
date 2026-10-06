"""
Branching worlds, identical fork state, intervention comparison, and trajectory analysis.

The product claim under test: "both branches begin from exactly the same checkpoint, and
any later difference is attributable to the intervention". These tests fail if branches
share state, if the fork state differs, or if a branch mutates its parent.
"""

from __future__ import annotations

import unittest

from event_sim import comparison, sweep
from event_sim.engine import Intervention, SimulationConfig, build_simulation
from event_sim.scenarios.port_disruption import (
    OUTCOME_VARIABLE,
    build_baseline,
    build_event,
    build_world_slice,
    redirect_cargo_intervention,
    run_vertical_slice,
)


class TestIdenticalCheckpointStart(unittest.TestCase):
    """A fork must resume from the parent's exact state at the fork turn."""

    def test_branch_starts_from_identical_state(self) -> None:
        parent = build_baseline(turns=14)
        parent.run(turns=4)
        state_at_fork = parent.state()

        branch = parent.fork(4, branch_id="b", label="branch")
        self.assertEqual(branch.state(), state_at_fork)
        self.assertEqual(branch.world.turn, 4)
        self.assertEqual(branch.fork_turn, 4)
        self.assertEqual(branch.parent_id, parent.branch_id)

    def test_branch_inherits_lagged_history_not_just_current_state(self) -> None:
        """
        Restoring only the current values would silently reset every in-flight lagged
        effect. The branch must inherit the deviation history too.
        """
        parent = build_baseline(turns=16)
        parent.run(turns=5)
        branch = parent.fork(5, branch_id="b")
        self.assertEqual(len(branch._dev_history), len(parent._dev_history))  # noqa: SLF001
        self.assertEqual(branch._dev_history, parent._dev_history)            # noqa: SLF001

        # With no intervention, the branch must reproduce the parent exactly going forward.
        parent.run()
        branch.run()
        self.assertEqual(branch.state(), parent.state())

    def test_fork_at_unreached_turn_is_rejected(self) -> None:
        parent = build_baseline(turns=10)
        parent.run(turns=2)
        with self.assertRaises(ValueError):
            parent.fork(7, branch_id="b")


class TestBranchIsolation(unittest.TestCase):
    """Branches must not share mutable state with their parent or with each other."""

    def test_running_a_branch_does_not_move_the_parent(self) -> None:
        parent = build_baseline(turns=14)
        parent.run(turns=3)
        parent_state_before = parent.state()
        parent_turn_before = parent.world.turn
        parent_traj_len = len(parent.trajectory)

        branch = parent.fork(3, branch_id="b", interventions=[
            redirect_cargo_intervention(parent.slice, share=0.5, start_turn=4, duration=10)
        ])
        branch.run()

        self.assertEqual(parent.state(), parent_state_before)
        self.assertEqual(parent.world.turn, parent_turn_before)
        self.assertEqual(len(parent.trajectory), parent_traj_len)

    def test_parent_and_branch_do_not_share_objects(self) -> None:
        parent = build_baseline(turns=12)
        parent.run(turns=3)
        branch = parent.fork(3, branch_id="b")

        self.assertIsNot(branch.world, parent.world)
        self.assertIsNot(branch.world.variables, parent.world.variables)
        self.assertIsNot(branch.trajectory, parent.trajectory)
        self.assertIsNot(branch.provenance, parent.provenance)
        self.assertIsNot(branch.checkpoints, parent.checkpoints)

        branch.world.variables["port_capacity"] = -1.0
        self.assertNotEqual(parent.world.variables["port_capacity"], -1.0)

    def test_two_branches_from_one_checkpoint_are_independent(self) -> None:
        parent = build_baseline(turns=16)
        parent.run(turns=3)
        b1 = parent.fork(3, branch_id="b1")
        b2 = parent.fork(3, branch_id="b2", interventions=[
            redirect_cargo_intervention(parent.slice, share=0.4, start_turn=4, duration=12)
        ])
        self.assertEqual(b1.state(), b2.state())  # same start
        b1.run()
        b2.run()
        self.assertNotEqual(b1.state(), b2.state())  # different ends
        # While the intervention is active, the intervened world must hold more capacity.
        self.assertGreater(b2.series("port_capacity")[6], b1.series("port_capacity")[6])
        # And the downstream consequence must persist past the intervention window.
        self.assertGreater(b2.state()["service_level"], b1.state()["service_level"])

    def test_branch_provenance_is_truncated_to_the_fork(self) -> None:
        parent = build_baseline(turns=12)
        parent.run(turns=4)
        branch = parent.fork(4, branch_id="b")
        self.assertEqual([p["turn"] for p in branch.provenance], [1, 2, 3, 4])
        branch.run()
        self.assertEqual([p["turn"] for p in branch.provenance], list(range(1, 13)))


class TestInterventionComparison(unittest.TestCase):
    """Comparing two worlds must isolate the intervention as the only difference."""

    def setUp(self) -> None:
        self.payload = run_vertical_slice(turns=18, include_sweep=False)
        self.diff = self.payload["comparison"]

    def test_worlds_are_identical_at_the_fork(self) -> None:
        self.assertTrue(self.diff["identical_at_fork"])
        self.assertTrue(self.diff["same_assumptions"])

    def test_intervention_is_the_only_difference(self) -> None:
        a = self.payload["worlds"]["world_a"]
        b = self.payload["worlds"]["world_b"]
        self.assertEqual(a["config"]["axis_settings"], b["config"]["axis_settings"])
        self.assertEqual(a["events"], b["events"])
        self.assertEqual(a["interventions"], [])
        self.assertEqual([i["id"] for i in b["interventions"]], ["redirect_cargo"])

    def test_comparison_reports_direction_and_magnitude(self) -> None:
        rows = {r["variable"]: r for r in self.diff["variables"]}
        self.assertGreater(rows["port_capacity"]["peak_difference"], 0)   # capacity restored
        self.assertGreater(rows["freight_cost"]["peak_difference"], 0)    # at a cost premium
        self.assertLess(rows["shipping_delay"]["peak_difference"], 0)     # delay reduced
        self.assertIn("port_capacity", self.diff["material_differences"])

    def test_comparison_summary_is_deterministic_text(self) -> None:
        again = comparison.summarize(self.diff)
        self.assertEqual(again, self.payload["comparison_summary"])
        self.assertTrue(all(isinstance(line, str) for line in again))

    def test_comparing_worlds_from_different_slices_is_rejected(self) -> None:
        slice_a = build_world_slice()
        slice_b = build_world_slice()
        slice_b.id = "other_slice"
        sim_a = build_simulation(slice_a, config=SimulationConfig(turns=4), events=[build_event()])
        sim_b = build_simulation(slice_b, config=SimulationConfig(turns=4), events=[build_event()])
        sim_a.run()
        sim_b.run()
        with self.assertRaises(ValueError):
            comparison.compare(sim_a, sim_b)


class TestSweepAndTrajectories(unittest.TestCase):
    """Sweeps must be a designed grid, reported as counts of tested worlds."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.slice = build_world_slice()
        cls.worlds = sweep.run_sweep(cls.slice, events=[build_event()], turns=18)
        cls.trajectories = sweep.group_trajectories(
            cls.worlds, sweep.port_disruption_rules(cls.slice)
        )

    def test_sweep_covers_the_full_assumption_grid(self) -> None:
        expected = 1
        for axis in self.slice.axes:
            expected *= len(axis.settings)
        self.assertEqual(len(self.worlds), expected)
        keys = {tuple(sorted(w["config"]["axis_settings"].items())) for w in self.worlds}
        self.assertEqual(len(keys), expected, "grid must contain no duplicate worlds")

    def test_every_world_is_reproducible_and_attributable(self) -> None:
        for world in self.worlds:
            self.assertTrue(world["fingerprint"])
            self.assertEqual(
                set(world["config"]["axis_settings"]), {a.id for a in self.slice.axes}
            )

    def test_trajectories_partition_the_tested_worlds(self) -> None:
        total = sum(t.world_count for t in self.trajectories)
        self.assertEqual(total, len(self.worlds))
        self.assertTrue(all(t.conditions for t in self.trajectories))

    def test_trajectories_report_counts_not_probabilities(self) -> None:
        for traj in self.trajectories:
            payload = traj.to_dict()
            self.assertIn("world_count", payload)
            self.assertNotIn("probability", payload)
            self.assertNotIn("likelihood", payload)

    def test_pivotal_assumptions_rank_axes_by_outcome_span(self) -> None:
        pivotal = sweep.pivotal_assumptions(
            self.worlds, outcome_variable=OUTCOME_VARIABLE, trajectories=self.trajectories
        )
        axes = pivotal["axes"]
        self.assertEqual({a["axis"] for a in axes}, {a.id for a in self.slice.axes})
        influences = [a["influence"] for a in axes]
        self.assertEqual(influences, sorted(influences, reverse=True))
        self.assertTrue(all(a["rank"] in {"HIGH", "MEDIUM", "LOW"} for a in axes))
        for axis in axes:
            self.assertGreaterEqual(axis["best_outcome"], axis["worst_outcome"])

    def test_recovery_rate_influences_the_outcome(self) -> None:
        """A sanity check that the sweep is measuring something real."""
        pivotal = sweep.pivotal_assumptions(self.worlds, outcome_variable=OUTCOME_VARIABLE)
        recovery = next(a for a in pivotal["axes"] if a["axis"] == "recovery_rate")
        self.assertGreater(recovery["influence"], 0.0)
        self.assertEqual(recovery["best_setting"], "fast")
        self.assertEqual(recovery["worst_setting"], "slow")

    def test_envelope_is_a_range_across_tested_worlds(self) -> None:
        env = sweep.envelope(self.worlds, OUTCOME_VARIABLE)
        self.assertEqual(env["world_count"], len(self.worlds))
        for low, median, high in zip(env["low"], env["median"], env["high"]):
            self.assertLessEqual(low, median)
            self.assertLessEqual(median, high)


if __name__ == "__main__":
    unittest.main()
