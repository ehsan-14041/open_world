"""
Benchmark #2 and cross-event falsification.

The guarantees under test:
  - the world model was NOT modified while adding the second benchmark (frozen model);
  - the Baltimore replay's capacity recovery is a model OUTPUT, not an injected input, so
    the milestone comparison is a real test;
  - observability classification is declared for every node;
  - milestone (timing) evaluation works and reports how extreme the observed value was;
  - the cross-event diagnosis detects a repeated failure and does not overstate it.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from event_sim.cross_event import (
    STRUCTURAL_HYPOTHESES,
    cross_event_diagnosis,
    timing_findings,
)
from event_sim.historical import (
    available_episodes,
    load_episode,
    load_milestones,
    load_observations,
    milestone_evaluation,
    replay_episode,
    validate_no_hindsight,
)
from event_sim.model_health import model_health, observability_profile, render_model_health
from event_sim.registry import get_module
from event_sim.schemas import OBSERVABILITY_ORDER, ObservedMilestone
from event_sim.scenarios.port_disruption import build_world_slice

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
EPISODE = "baltimore_2024"


class TestModelStillFrozen(unittest.TestCase):
    """
    The instruction for this iteration was: do not change the model. These tests pin the
    dynamics so a later 'small tweak to make the replay fit' cannot pass silently.
    """

    #: Coefficients, lags and polarities as shipped before benchmark #2 was added.
    FROZEN_EDGES = {
        "port_capacity->shipping_delay": ("negative", 0.6, 0.9, 1.3, 0, 1),
        "port_capacity->order_backlog": ("negative", 0.4, 0.65, 0.95, 1, 1),
        "order_backlog->shipping_delay": ("positive", 0.1, 0.2, 0.35, 1, 2),
        "shipping_delay->freight_cost": ("positive", 0.25, 0.45, 0.7, 0, 1),
        "shipping_delay->inventory_availability": ("negative", 0.3, 0.5, 0.75, 1, 2),
        "inventory_availability->service_level": ("positive", 0.4, 0.65, 0.9, 0, 1),
        "inventory_availability->production_capacity": ("positive", 0.25, 0.45, 0.7, 1, 2),
        "production_capacity->service_level": ("positive", 0.15, 0.3, 0.5, 1, 2),
        "freight_cost->consumer_price_pressure": ("positive", 0.1, 0.2, 0.35, 2, 4),
    }

    #: Variable dynamics as shipped.
    FROZEN_VARIABLES = {
        "port_capacity": (100.0, 100.0, 0.55),
        "shipping_delay": (4.0, 10.0, 0.5),
        "freight_cost": (100.0, 100.0, 0.35),
        "order_backlog": (100.0, 100.0, 0.4),
        "inventory_availability": (100.0, 100.0, 0.3),
        "production_capacity": (100.0, 100.0, 0.35),
        "service_level": (0.95, 0.5, 0.45),
        "consumer_price_pressure": (100.0, 100.0, 0.2),
    }

    def test_no_coefficient_lag_or_polarity_changed(self) -> None:
        module = get_module("port_disruption")
        self.assertEqual(len(module.edges), len(self.FROZEN_EDGES))
        for edge in module.edges:
            with self.subTest(edge=edge.id):
                expected = self.FROZEN_EDGES[edge.id]
                actual = (edge.polarity, edge.effect.low, edge.effect.central,
                          edge.effect.high, edge.lag.min, edge.lag.max)
                self.assertEqual(actual, expected)

    def test_no_variable_dynamics_changed(self) -> None:
        module = get_module("port_disruption")
        for var in module.variables:
            with self.subTest(variable=var.id):
                expected = self.FROZEN_VARIABLES[var.id]
                self.assertEqual((var.baseline, var.scale, var.response), expected)

    def test_topology_unchanged(self) -> None:
        """No node or edge was added to make the replay fit."""
        module = get_module("port_disruption")
        self.assertEqual({v.id for v in module.variables}, set(self.FROZEN_VARIABLES))
        self.assertEqual({e.id for e in module.edges}, set(self.FROZEN_EDGES))

    def test_all_edges_remain_expert_assumption(self) -> None:
        for edge in get_module("port_disruption").edges:
            with self.subTest(edge=edge.id):
                self.assertEqual(edge.status, "expert_assumption")


class TestObservabilityClassification(unittest.TestCase):
    """Every node must declare whether the real world can be seen for it."""

    def test_every_variable_declares_an_observability_class(self) -> None:
        for var in get_module("port_disruption").variables:
            with self.subTest(variable=var.id):
                self.assertIn(var.observability_class, OBSERVABILITY_ORDER)
                self.assertTrue(var.observability_note, "classification needs a justification")

    def test_the_headline_outcome_is_latent(self) -> None:
        """
        service_level is what the product reports and what nobody can measure publicly.
        Pinning it here keeps that uncomfortable fact visible.
        """
        slice_ = build_world_slice()
        self.assertEqual(slice_.variable("service_level").observability_class, "latent")

    def test_profile_counts_and_rates(self) -> None:
        profile = observability_profile(build_world_slice().variables)
        self.assertEqual(sum(profile["counts"].values()), profile["variable_count"])
        self.assertAlmostEqual(sum(profile["shares"].values()), 1.0, places=9)
        self.assertEqual(profile["counts"]["latent"], 3)
        self.assertIn(profile["rating"], {"GOOD", "MEDIUM", "POOR", "FAILED"})
        self.assertIn(profile["proxy_dependence"], {"LOW", "MEDIUM", "HIGH"})

    def test_classification_survives_json_round_trip(self) -> None:
        module = get_module("port_disruption")
        from event_sim.schemas import WorldModule

        again = WorldModule.from_dict(json.loads(json.dumps(module.to_dict())))
        for original, restored in zip(module.variables, again.variables):
            self.assertEqual(restored.observability_class, original.observability_class)

    def test_classification_does_not_affect_dynamics(self) -> None:
        """Observability is metadata: identical trajectories with or without it."""
        from event_sim.engine import SimulationConfig, build_simulation
        from event_sim.schemas import EventDefinition

        slice_ = build_world_slice()
        event = EventDefinition(id="e", targets={"port_capacity": -70.0}, start_turn=1, duration=4)
        before = build_simulation(slice_, config=SimulationConfig(turns=10), events=[event]).run()
        for var in slice_.variables:
            var.observability_class = "latent"
            var.observability_note = "mutated for this test"
        after = build_simulation(slice_, config=SimulationConfig(turns=10), events=[event]).run()
        self.assertEqual(before["final_state"], after["final_state"])


class TestBaltimoreEpisode(unittest.TestCase):
    def test_episode_is_registered_with_a_cutoff(self) -> None:
        ids = {e["id"] for e in available_episodes()}
        self.assertIn(EPISODE, ids)
        episode = load_episode(EPISODE)
        self.assertEqual(episode.knowledge_cutoff, "2024-03-26")
        self.assertTrue(episode.why_this_event)

    def test_no_hindsight_leakage(self) -> None:
        episode = load_episode(EPISODE)
        report = validate_no_hindsight(episode, load_observations(EPISODE))
        self.assertEqual(report["violations"], [])

    def test_recovery_path_is_a_model_output_not_an_injected_input(self) -> None:
        """
        The whole point of benchmark #2: only the initiating shock is injected, for one
        week. If the restoration were injected, the milestone test would be circular.
        """
        episode = load_episode(EPISODE)
        self.assertEqual(episode.additional_events, [])
        self.assertEqual(episode.event.duration, 1)
        self.assertEqual(episode.event.start_turn, 1)

        replay = replay_episode(episode)
        capacity = replay["worlds"][0]["series"]["port_capacity"]
        self.assertAlmostEqual(capacity[0], 100.0)
        self.assertAlmostEqual(capacity[1], 0.0)      # the injected week
        self.assertGreater(capacity[2], 0.0)          # everything after is the model's own
        self.assertGreater(capacity[-1], capacity[2])

    def test_milestones_carry_provenance(self) -> None:
        milestones = load_milestones(EPISODE)
        self.assertTrue(milestones)
        for milestone in milestones:
            with self.subTest(milestone=milestone.id):
                self.assertTrue(milestone.source)
                self.assertTrue(milestone.date)
                self.assertTrue(milestone.note)

    def test_reported_milestone_is_not_scored(self) -> None:
        """An expectation published before the fact is not an observation."""
        milestones = {m.id: m for m in load_milestones(EPISODE)}
        self.assertTrue(milestones["full_channel_restored"].is_scoreable())
        self.assertFalse(milestones["normal_operations"].is_scoreable())

    def test_the_yantian_proxy_was_not_reused(self) -> None:
        """
        Reapplying the discredited global delay proxy to a second event would reproduce the
        first event's confounding instead of testing the model independently.
        """
        observations = load_observations(EPISODE)
        self.assertEqual(observations, [])
        raw = json.loads(
            (_PROJECT_ROOT / "event_sim" / "historical" / "observations" / f"{EPISODE}.json")
            .read_text(encoding="utf-8")
        )
        reasons = {item["variable"]: item["reason"] for item in raw["_not_observed"]}
        self.assertIn("shipping_delay", reasons)
        self.assertIn("deliberately NOT reused", reasons["shipping_delay"])


class TestMilestoneEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.episode = load_episode(EPISODE)
        cls.replay = replay_episode(cls.episode)
        cls.result = milestone_evaluation(cls.replay, load_milestones(EPISODE))

    def test_model_reaches_the_milestone_too_early(self) -> None:
        row = next(r for r in self.result["milestones"] if r["milestone"] == "full_channel_restored")
        self.assertEqual(row["observed_turn"], 11)
        self.assertLess(row["timing_error_turns"], 0, "model should be early, not late")
        self.assertIsNotNone(row["simulated"])

    def test_reports_how_extreme_the_observed_value_was(self) -> None:
        """'Inside the envelope' is a weak claim without knowing where inside."""
        row = next(r for r in self.result["milestones"] if r["milestone"] == "full_channel_restored")
        share = row["share_of_worlds_at_or_beyond_observed"]
        self.assertGreater(share, 0.0)
        self.assertLessEqual(share, 1.0)

    def test_only_observed_milestones_are_scored(self) -> None:
        self.assertEqual(self.result["scored_count"], 1)
        reported = next(r for r in self.result["milestones"] if r["milestone"] == "normal_operations")
        self.assertFalse(reported["scored"])

    def test_reported_milestone_falls_outside_the_envelope(self) -> None:
        reported = next(r for r in self.result["milestones"] if r["milestone"] == "normal_operations")
        self.assertFalse(reported["observed_inside_envelope"])
        self.assertEqual(reported["verdict"], "simulated too early")

    def test_timing_framing_is_not_probabilistic(self) -> None:
        self.assertIn("not a confidence interval", self.result["framing"])

    def test_synthetic_series_hitting_the_milestone_on_time_scores_zero_error(self) -> None:
        """Sanity check on the metric itself."""
        milestone = ObservedMilestone(
            id="peak_check", variable="port_capacity", kind="peak", observed_turn=1,
            status="observed",
        )
        result = milestone_evaluation(self.replay, [milestone])
        row = result["milestones"][0]
        self.assertEqual(row["timing_error_turns"], 0)


class TestCrossEventDiagnosis(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "replay_cli", _PROJECT_ROOT / "scripts" / "replay_port_event.py"
        )
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)
        cls.diag = cross_event_diagnosis(["yantian_2021", EPISODE], cls.cli.run_pipeline)

    def test_both_events_run_against_the_same_frozen_model(self) -> None:
        self.assertTrue(self.diag["model_frozen"])
        self.assertEqual(set(self.diag["episodes"]), {"yantian_2021", EPISODE})

    def test_the_failure_pattern_repeats(self) -> None:
        self.assertTrue(self.diag["pattern_repeats"])
        self.assertEqual(len(self.diag["episodes_showing_early_bias"]), 2)

    def test_every_timing_error_has_the_same_sign(self) -> None:
        """The finding: the model is too fast on both events, never too slow."""
        self.assertGreater(self.diag["tests_too_early"], 0)
        self.assertEqual(self.diag["tests_too_late"], 0)

    def test_diagnosis_does_not_overstate_the_result(self) -> None:
        """
        The hard observed Baltimore milestone is INSIDE the envelope. The report must not
        call that a falsification.
        """
        report = self.cli.render_cross_event(self.diag)
        self.assertIn("not yet a strict falsification", report)
        self.assertIn("INSIDE the simulated envelope", report)
        self.assertIn("Two events is a pattern, not a proof", report)

    def test_structural_hypotheses_are_declared_but_not_adopted(self) -> None:
        report = self.cli.render_cross_event(self.diag)
        self.assertIn("None of these has been implemented", report)
        for hypothesis in STRUCTURAL_HYPOTHESES:
            self.assertIn(hypothesis["name"], report)
            self.assertTrue(hypothesis["test"], "a hypothesis needs a stated test")

    def test_timing_findings_are_collected_from_both_metric_families(self) -> None:
        kinds = {f["kind"] for f in timing_findings(self.diag["results"])}
        self.assertIn("peak", kinds)                 # from the level series
        self.assertIn("recovery_to_baseline", kinds)  # from the milestones

    def test_diagnosis_is_deterministic(self) -> None:
        again = cross_event_diagnosis(["yantian_2021", EPISODE], self.cli.run_pipeline)
        self.assertEqual(
            self.cli.render_cross_event(again), self.cli.render_cross_event(self.diag)
        )

    def test_written_report_exists_and_states_the_frozen_model(self) -> None:
        path = _PROJECT_ROOT / "docs" / "replays" / "CROSS_EVENT_DIAGNOSIS.md"
        self.assertTrue(path.is_file(), "run scripts/replay_port_event.py --cross-event --write-report")
        text = path.read_text(encoding="utf-8")
        self.assertIn("frozen", text)
        self.assertIn("A reopened port is not a cleared queue", text)


class TestModelHealth(unittest.TestCase):
    def test_health_reports_every_axis(self) -> None:
        health = model_health(build_world_slice())
        for key in ("evidence_coverage", "observability", "proxy_dependence",
                    "historical_validation", "critical_uncertainty"):
            self.assertIn(key, health)

    def test_untested_model_is_untested_not_good(self) -> None:
        """An unvalidated model must never read as validated."""
        health = model_health(build_world_slice(), replays=[])
        self.assertEqual(health["historical_validation"]["rating"], "UNTESTED")

    def test_replay_results_drive_the_validation_ratings(self) -> None:
        replays = [{
            "episode": "e1",
            "evaluation": {"variables": [{
                "coverage_rate": 0.0,
                "trajectory": {"direction_match": True, "peak_timing_error_turns": -9},
            }]},
            "milestones": {"milestones": [
                {"scored": True, "timing_error_turns": -6, "simulated": {}},
            ]},
        }]
        health = model_health(build_world_slice(), replays=replays)
        validation = health["historical_validation"]
        self.assertEqual(validation["directional_validity"], "GOOD")
        self.assertEqual(validation["timing_validity"], "FAILED")
        self.assertEqual(validation["magnitude_validity"], "FAILED")
        self.assertEqual(validation["rating"], "FAILED")

    def test_every_rating_has_a_stated_rule(self) -> None:
        health = model_health(build_world_slice())
        self.assertTrue(health["evidence_coverage"]["rule"])
        self.assertTrue(health["observability"]["rule"])
        self.assertTrue(health["historical_validation"]["rule"])
        self.assertIn("none is assigned by a model", health["framing"])

    def test_render_is_plain_text(self) -> None:
        text = render_model_health(model_health(build_world_slice()))
        self.assertIn("MODEL HEALTH", text)
        self.assertIn("Observability", text)


if __name__ == "__main__":
    unittest.main()
