"""
Historical replay: observation provenance, hindsight leakage, determinism, evaluation
metrics, envelope coverage, and calibration provenance.

The central guarantees under test:
  - a replay cannot be initialised with information published after the knowledge cutoff;
  - a replay uses the *same* engine as forward simulation, not special historical physics;
  - evaluation refuses to score against non-observed values;
  - calibration never overwrites a prior and refuses unidentifiable parameters.
"""

from __future__ import annotations

import copy
import json
import unittest

from event_sim.historical import (
    HindsightLeakageError,
    HistoricalEpisode,
    InsufficientObservationsError,
    available_episodes,
    build_replay_slice,
    calibrate_edge,
    calibrate_episode,
    check_identifiability,
    evaluate_replay,
    load_episode,
    load_observations,
    observation_metadata,
    replay_episode,
    validate_no_hindsight,
)
from event_sim.historical.calibration import MIN_OBSERVATIONS, write_calibration_records
from event_sim.historical.evaluation import envelope_coverage, trajectory_metrics
from event_sim.schemas import EventDefinition, HistoricalObservation

EPISODE_ID = "yantian_2021"


class TestEpisodeAndObservationProvenance(unittest.TestCase):
    def test_episode_is_registered(self) -> None:
        ids = {e["id"] for e in available_episodes()}
        self.assertIn(EPISODE_ID, ids)

    def test_episode_declares_its_epistemic_boundaries(self) -> None:
        episode = load_episode(EPISODE_ID)
        self.assertTrue(episode.knowledge_cutoff)
        self.assertTrue(episode.start_date)
        self.assertTrue(episode.evaluation_window.get("from"))
        self.assertTrue(episode.why_this_event, "an episode must justify its own selection")

    def test_every_observation_carries_source_provenance(self) -> None:
        """No anonymous numbers."""
        observations = load_observations(EPISODE_ID)
        self.assertTrue(observations)
        for obs in observations:
            with self.subTest(variable=obs.variable, turn=obs.turn):
                self.assertTrue(obs.source, "observation has no source id")
                self.assertTrue(obs.unit, "observation has no unit")
                self.assertTrue(obs.date, "observation has no date")
                self.assertTrue(obs.available_at, "observation has no publication date")

    def test_observation_sources_resolve_in_the_registry(self) -> None:
        from event_sim.evidence import get_source

        for obs in load_observations(EPISODE_ID):
            with self.subTest(source=obs.source):
                get_source(obs.source)  # raises if unknown

    def test_observations_preserve_original_units(self) -> None:
        for obs in load_observations(EPISODE_ID):
            if obs.variable == "shipping_delay":
                self.assertEqual(obs.unit, "days")

    def test_context_points_are_not_scoreable(self) -> None:
        """The model must never be graded against its own initial condition."""
        observations = load_observations(EPISODE_ID)
        context = [o for o in observations if o.status == "context"]
        self.assertTrue(context, "the baseline point should be recorded as context")
        for obs in context:
            self.assertFalse(obs.is_scoreable())

    def test_observation_metadata_declares_unobserved_variables(self) -> None:
        meta = observation_metadata(EPISODE_ID)
        self.assertTrue(meta["turn_mapping_rule"])
        missing = {item["variable"] for item in meta["not_observed"]}
        self.assertIn("service_level", missing)
        for item in meta["not_observed"]:
            self.assertTrue(item["reason"])


class TestNoHindsightLeakage(unittest.TestCase):
    def test_shipped_episode_passes_the_cutoff_check(self) -> None:
        episode = load_episode(EPISODE_ID)
        report = validate_no_hindsight(episode, load_observations(EPISODE_ID))
        self.assertEqual(report["violations"], [])
        self.assertTrue(report["initial_state_checked"])
        for entry in report["initial_state_checked"]:
            self.assertTrue(entry["ok"])

    def test_initialising_from_a_later_publication_is_rejected(self) -> None:
        """
        The subtle case: the April figure *describes* a pre-event month but was published
        after the event began. Using it is still leakage.
        """
        episode = load_episode(EPISODE_ID)
        leaky = copy.deepcopy(episode)
        leaky.initial_state["shipping_delay"] = 5.68
        leaky.initial_state_provenance["shipping_delay"] = {
            "value": 5.68, "refers_to_period": "2021-04", "available_at": "2021-05-31",
            "source_id": "si_glp_2021_04",
        }
        with self.assertRaises(HindsightLeakageError) as ctx:
            validate_no_hindsight(leaky, [])
        self.assertIn("hindsight leakage", str(ctx.exception))

    def test_initial_state_without_provenance_is_rejected(self) -> None:
        episode = copy.deepcopy(load_episode(EPISODE_ID))
        episode.initial_state["freight_cost"] = 120.0
        with self.assertRaises(HindsightLeakageError):
            validate_no_hindsight(episode, [])

    def test_episode_without_a_cutoff_is_rejected(self) -> None:
        episode = copy.deepcopy(load_episode(EPISODE_ID))
        episode.knowledge_cutoff = ""
        with self.assertRaises(HindsightLeakageError):
            validate_no_hindsight(episode, [])

    def test_replay_runs_the_hindsight_check_by_default(self) -> None:
        episode = copy.deepcopy(load_episode(EPISODE_ID))
        episode.initial_state_provenance["shipping_delay"]["available_at"] = "2021-06-30"
        with self.assertRaises(HindsightLeakageError):
            replay_episode(episode)

    def test_outcome_observations_are_expected_after_the_cutoff(self) -> None:
        """Outcomes are supposed to postdate the cutoff; that is not leakage."""
        episode = load_episode(EPISODE_ID)
        report = validate_no_hindsight(episode, load_observations(EPISODE_ID))
        later = [o for o in report["observations"] if o["published_after_cutoff"]]
        self.assertTrue(later)


class TestReplayDeterminismAndEngineReuse(unittest.TestCase):
    def test_replay_is_deterministic(self) -> None:
        episode = load_episode(EPISODE_ID)
        a = replay_episode(episode)
        b = replay_episode(episode)
        self.assertEqual(a["envelope"], b["envelope"])
        self.assertEqual(
            [w["fingerprint"] for w in a["worlds"]],
            [w["fingerprint"] for w in b["worlds"]],
        )

    def test_replay_uses_the_same_engine_as_forward_simulation(self) -> None:
        """No special historical physics: same slice, same sweep, same fingerprints."""
        from event_sim import sweep

        episode = load_episode(EPISODE_ID)
        slice_ = build_replay_slice(episode)
        direct = sweep.run_sweep(slice_, events=episode.all_events(), turns=episode.turns)
        replayed = replay_episode(episode)
        self.assertEqual(
            [w["fingerprint"] for w in direct],
            [w["fingerprint"] for w in replayed["worlds"]],
        )

    def test_replay_baseline_comes_from_the_historical_initial_state(self) -> None:
        episode = load_episode(EPISODE_ID)
        slice_ = build_replay_slice(episode)
        delay = slice_.variable("shipping_delay")
        self.assertAlmostEqual(delay.baseline, 6.16)
        # Untouched variables keep the module default.
        self.assertAlmostEqual(slice_.variable("port_capacity").baseline, 100.0)

    def test_injected_event_phases_drive_capacity(self) -> None:
        episode = load_episode(EPISODE_ID)
        replay = replay_episode(episode)
        capacity = replay["worlds"][0]["series"]["port_capacity"]
        self.assertAlmostEqual(capacity[0], 100.0)
        self.assertAlmostEqual(capacity[1], 30.0)   # phase 1: ~30% of normal
        self.assertAlmostEqual(capacity[3], 70.0)   # phase 2: partial reopening
        self.assertGreater(capacity[6], 70.0)       # released, recovering

    def test_turn_dates_are_derived_from_the_start_date(self) -> None:
        episode = load_episode(EPISODE_ID)
        self.assertEqual(episode.turn_to_date(0), "2021-05-25")
        self.assertEqual(episode.turn_to_date(1), "2021-06-01")


class TestReplayEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.episode = load_episode(EPISODE_ID)
        cls.observations = load_observations(EPISODE_ID)
        cls.replay = replay_episode(cls.episode)
        cls.evaluation = evaluate_replay(cls.replay, cls.observations)

    def test_only_observed_points_are_scored(self) -> None:
        scoreable = [o for o in self.observations if o.is_scoreable()]
        self.assertEqual(self.evaluation["scored_points"], len(scoreable))
        self.assertTrue(self.evaluation["skipped_records"])

    def test_unevaluated_variables_are_declared(self) -> None:
        """A replay that silently ignores six of eight variables would be misleading."""
        self.assertEqual(self.evaluation["evaluated_variables"], ["shipping_delay"])
        self.assertIn("service_level", self.evaluation["unevaluated_variables"])
        self.assertIn("Only 1 of", self.evaluation["warning"])

    def test_metrics_are_per_variable_not_a_single_r2(self) -> None:
        row = self.evaluation["variables"][0]
        metrics = row["trajectory"]
        for key in ("direction_match", "peak_timing_error_turns", "peak_magnitude_error",
                    "mae", "normalized_mae", "correlation",
                    "observed_recovery_turn", "simulated_recovery_turn"):
            self.assertIn(key, metrics)
        self.assertNotIn("r2", metrics)

    def test_envelope_coverage_reports_where_it_escaped(self) -> None:
        row = self.evaluation["variables"][0]
        self.assertIsNotNone(row["coverage_rate"])
        if row["outside"]:
            self.assertIsNotNone(row["first_divergence_turn"])
            for point in row["outside"]:
                self.assertIn(point["direction"], {"above", "below"})
                self.assertGreater(point["distance"], 0)

    def test_coverage_is_never_presented_as_a_probability(self) -> None:
        row = self.evaluation["variables"][0]
        self.assertIn("not a probability", row["interpretation"])
        self.assertNotIn("probability", self.evaluation)

    def test_evaluation_refuses_to_score_without_observed_data(self) -> None:
        with self.assertRaises(InsufficientObservationsError):
            evaluate_replay(self.replay, [])

    def test_evaluation_refuses_non_observed_records(self) -> None:
        assumed = [HistoricalObservation(variable="shipping_delay", turn=1, value=7.0,
                                         status="expert_assumption")]
        with self.assertRaises(InsufficientObservationsError):
            evaluate_replay(self.replay, assumed)

    def test_a_series_inside_its_own_envelope_scores_full_coverage(self) -> None:
        """Sanity check on the metric itself, with an explicitly synthetic series."""
        env = self.replay["envelope"]["shipping_delay"]
        synthetic = [
            HistoricalObservation(variable="shipping_delay", turn=t, value=env["median"][t],
                                  status="observed", source="synthetic")
            for t in range(1, 6)
        ]
        coverage = envelope_coverage(env, synthetic)
        self.assertEqual(coverage["coverage_rate"], 1.0)
        self.assertIsNone(coverage["first_divergence_turn"])

    def test_peak_and_direction_metrics_are_computed_from_observations(self) -> None:
        env = self.replay["envelope"]["shipping_delay"]
        rising = [
            HistoricalObservation(variable="shipping_delay", turn=t, value=6.0 + t,
                                  status="observed", source="synthetic")
            for t in range(0, 5)
        ]
        metrics = trajectory_metrics(env, rising, baseline=6.0)
        self.assertEqual(metrics["direction_observed"], "up")
        self.assertEqual(metrics["observed_peak"]["turn"], 4)
        self.assertEqual(metrics["scored_points"], 5)

    def test_tolerance_widens_the_band(self) -> None:
        strict = evaluate_replay(self.replay, self.observations, tolerance=0.0)
        loose = evaluate_replay(self.replay, self.observations, tolerance=5.0)
        self.assertGreaterEqual(loose["overall_coverage_rate"], strict["overall_coverage_rate"])


class TestCalibration(unittest.TestCase):
    def setUp(self) -> None:
        self.episode = load_episode(EPISODE_ID)
        self.observations = load_observations(EPISODE_ID)

    def test_edges_without_observations_are_refused(self) -> None:
        outcome = calibrate_edge(self.episode, "inventory_availability->service_level",
                                 self.observations)
        self.assertFalse(outcome.identifiable)
        self.assertIn("no observations", outcome.reason)
        self.assertIsNone(outcome.record)

    def test_confounded_edges_are_refused(self) -> None:
        """Two edges into one target driven by the same shock cannot be separated."""
        outcome = calibrate_edge(self.episode, "port_capacity->shipping_delay", self.observations)
        self.assertFalse(outcome.identifiable)
        self.assertIn("cannot attribute movement", outcome.reason)

    def test_too_few_observations_blocks_calibration(self) -> None:
        slice_ = build_replay_slice(self.episode)
        edge = next(e for e in slice_.edges if e.id == "shipping_delay->freight_cost")
        few = [HistoricalObservation(variable="freight_cost", turn=t, value=100.0 + t,
                                     status="observed", source="synthetic")
               for t in range(MIN_OBSERVATIONS - 1)]
        identifiable, reason, _ = check_identifiability(edge, slice_, few)
        self.assertFalse(identifiable)
        self.assertIn("at least", reason)

    def test_whole_episode_calibration_reports_every_refusal(self) -> None:
        result = calibrate_episode(self.episode, self.observations)
        self.assertEqual(result["attempted"], 9)
        self.assertEqual(len(result["not_identifiable"]) + result["calibrated"], 9)
        for skip in result["not_identifiable"]:
            self.assertTrue(skip["reason"])

    def test_calibration_declares_its_in_sample_limitation(self) -> None:
        result = calibrate_episode(self.episode, self.observations)
        self.assertIn("in-sample", result["limitation"])
        self.assertIn("out-of-sample", result["limitation"])

    def test_calibration_never_rewrites_the_world_module(self) -> None:
        """The shipped module's coefficients must be untouched by a calibration run."""
        from event_sim.registry import clear_cache, get_module

        clear_cache()
        before = get_module("port_disruption").to_dict()
        calibrate_episode(self.episode, self.observations)
        clear_cache()
        self.assertEqual(get_module("port_disruption").to_dict(), before)

    def test_calibration_machinery_works_when_identifiable(self) -> None:
        """
        Machinery test on a deliberately simplified slice with a single parent, so the
        confounding guard does not fire. This validates the calibration CODE; it is not a
        claim about the port model, and the synthetic series is labelled as such.
        """
        episode = copy.deepcopy(self.episode)
        slice_ = build_replay_slice(episode)
        # keep only port_capacity -> shipping_delay so the target has one parent
        keep = "port_capacity->shipping_delay"
        edge = next(e for e in slice_.edges if e.id == keep)
        siblings = [e for e in slice_.edges_into("shipping_delay") if e.id != keep]
        self.assertTrue(siblings)  # confirms the real slice is confounded

        reduced = copy.deepcopy(slice_)
        reduced.edges = [e for e in reduced.edges if e.id == keep or e.target != "shipping_delay"]
        synthetic = [
            HistoricalObservation(variable="shipping_delay", turn=t, value=6.16 + t * 0.4,
                                  status="observed", source="synthetic_machinery_test")
            for t in range(1, 6)
        ]
        identifiable, reason, _ = check_identifiability(edge, reduced, synthetic)
        self.assertTrue(identifiable, reason)

    def test_calibration_record_preserves_the_prior(self) -> None:
        from event_sim.evidence.schema import CalibrationRecord

        record = CalibrationRecord(
            edge_id="port_capacity->shipping_delay", calibration_event_id=EPISODE_ID,
            method="grid", prior_range={"low": 0.6, "central": 0.9, "high": 1.3},
            calibrated_range={"low": 0.45, "central": 0.75, "high": 1.15},
        )
        self.assertEqual(record.prior_range["central"], 0.9)
        self.assertAlmostEqual(record.movement(), 0.15)

    def test_writing_records_appends_and_does_not_replace(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calibrations.json"
            write_calibration_records([{"edge_id": "a->b", "calibration_event_id": "e1"}], path=path)
            write_calibration_records([{"edge_id": "c->d", "calibration_event_id": "e2"}], path=path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["calibrations"]), 2)
            self.assertEqual(data["calibrations"][0]["edge_id"], "a->b")


class TestReplayCli(unittest.TestCase):
    def test_pipeline_runs_end_to_end_and_is_reproducible(self) -> None:
        import importlib.util
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "replay_cli", root / "scripts" / "replay_port_event.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        first = module.run_pipeline(EPISODE_ID)
        second = module.run_pipeline(EPISODE_ID)
        self.assertEqual(first["replay"]["envelope"], second["replay"]["envelope"])
        self.assertEqual(module.render_report(first), module.render_report(second))
        self.assertEqual(first["provenance_errors"], [])
        self.assertTrue(first["gaps"]["gaps"])
        self.assertTrue(first["data_requirements"])

    def test_report_states_its_limitations(self) -> None:
        from pathlib import Path

        report = Path(__file__).resolve().parent.parent / "docs" / "replays" / f"{EPISODE_ID}.md"
        self.assertTrue(report.is_file(), "run scripts/replay_port_event.py --write-report")
        text = report.read_text(encoding="utf-8")
        for expected in ("Knowledge cutoff", "Limitations", "in-sample", "global monthly aggregate"):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
