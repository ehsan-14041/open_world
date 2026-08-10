"""
World module library, evidence layer, world builder, and the historical-replay scaffolding.

The evidence rules are the point of this file: a module must not be able to claim
provenance it does not carry, and a slice must disclose what it excluded and what it is
missing.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from event_sim.evidence import (
    EvidenceValidationError,
    evidence_coverage,
    missing_evidence,
    validate_module,
)
from event_sim.historical import evaluation, replay
from event_sim.registry import (
    ModuleNotFoundError,
    WORLD_MODELS_DIR,
    available_modules,
    get_module,
    load_module_file,
)
from event_sim.schemas import (
    EVIDENCE_STATUS_ORDER,
    CausalEdgeEvidence,
    EffectRange,
    Evidence,
    EventDefinition,
    HistoricalObservation,
    Lag,
    WorldModule,
)
from event_sim.world_builder import build_slice, describe_slice


class TestModuleLibrary(unittest.TestCase):
    def test_every_shipped_module_validates(self) -> None:
        paths = list(WORLD_MODELS_DIR.glob("*/*.json"))
        self.assertTrue(paths, "world_models library should not be empty")
        for path in paths:
            with self.subTest(module=path.name):
                module = load_module_file(path)
                self.assertEqual(validate_module(module, raise_on_error=False), [])

    def test_registry_lists_port_disruption(self) -> None:
        ids = {m["id"] for m in available_modules()}
        self.assertIn("port_disruption", ids)

    def test_unknown_module_is_rejected(self) -> None:
        with self.assertRaises(ModuleNotFoundError):
            get_module("world_peace")

    def test_module_round_trips_through_json(self) -> None:
        module = get_module("port_disruption")
        again = WorldModule.from_dict(json.loads(json.dumps(module.to_dict())))
        self.assertEqual(again.to_dict(), module.to_dict())

    def test_module_declares_no_fabricated_sources(self) -> None:
        """
        The shipped module must not carry invented citations. Every edge is either
        unsourced (and therefore an assumption) or carries a real reference string.
        """
        module = get_module("port_disruption")
        for edge in module.edges:
            with self.subTest(edge=edge.id):
                if edge.evidence:
                    self.assertTrue(all(e.reference for e in edge.evidence))
                else:
                    self.assertIn(edge.status, {"expert_assumption", "user_assumption", "ai_hypothesis"})


class TestEvidenceRules(unittest.TestCase):
    def _module(self) -> WorldModule:
        return WorldModule.from_dict(get_module("port_disruption").to_dict())

    def test_strong_status_without_a_source_is_rejected(self) -> None:
        for status in ("observed", "empirical", "literature_backed", "historically_calibrated"):
            with self.subTest(status=status):
                module = self._module()
                module.edges[0].status = status
                module.edges[0].evidence = []
                with self.assertRaises(EvidenceValidationError):
                    validate_module(module)

    def test_strong_status_with_a_source_is_accepted(self) -> None:
        module = self._module()
        module.edges[0].status = "literature_backed"
        module.edges[0].evidence = [Evidence(type="empirical_study", reference="Example et al.", year=2024)]
        self.assertEqual(validate_module(module, raise_on_error=False), [])

    def test_edge_to_unknown_variable_is_rejected(self) -> None:
        module = self._module()
        module.edges.append(CausalEdgeEvidence(
            source="port_capacity", target="sea_level", polarity="positive",
            effect=EffectRange(0.1, 0.2, 0.3), status="expert_assumption", lag=Lag(0, 0),
        ))
        errors = validate_module(module, raise_on_error=False)
        self.assertTrue(any("unknown target" in e for e in errors))

    def test_inverted_effect_range_is_rejected(self) -> None:
        module = self._module()
        module.edges[0].effect = EffectRange(low=0.9, central=0.5, high=0.2)
        errors = validate_module(module, raise_on_error=False)
        self.assertTrue(any("effect.low" in e for e in errors))

    def test_every_status_in_the_ladder_is_recognised(self) -> None:
        for status in EVIDENCE_STATUS_ORDER:
            edge = CausalEdgeEvidence(
                source="a", target="b", polarity="positive",
                effect=EffectRange(0.1, 0.2, 0.3), status=status,
                evidence=[Evidence(type="dataset", reference="x")],
            )
            coverage = evidence_coverage([edge])
            self.assertEqual(coverage["edge_count"], 1)
            self.assertEqual(sum(coverage["by_group"].values()), 1)

    def test_polarity_drives_the_sign_not_the_range(self) -> None:
        edge = CausalEdgeEvidence(
            source="a", target="b", polarity="negative",
            effect=EffectRange(0.2, 0.5, 0.9), status="expert_assumption",
        )
        self.assertLess(edge.coefficient("central"), 0)
        self.assertEqual(edge.coefficient("low"), -0.2)
        self.assertEqual(edge.coefficient("high"), -0.9)

    def test_missing_evidence_lists_unsourced_edges_worst_first(self) -> None:
        module = get_module("port_disruption")
        gaps = missing_evidence(module.edges)
        self.assertEqual(len(gaps), len(module.edges))  # nothing is sourced yet
        spans = [g["effect_span"] for g in gaps]
        self.assertEqual(spans, sorted(spans, reverse=True))


class TestWorldSlice(unittest.TestCase):
    def test_slice_reports_what_it_included_and_excluded(self) -> None:
        slice_ = build_slice(["port_disruption"], question="test")
        self.assertEqual(slice_.included_systems, ["supply_chain/port_disruption"])
        self.assertEqual(len(slice_.variables), 8)
        self.assertEqual(len(slice_.edges), 9)
        self.assertIsInstance(slice_.excluded_systems, list)

    def test_narrowing_a_slice_drops_dangling_edges_and_records_them(self) -> None:
        keep = ["port_capacity", "shipping_delay", "freight_cost"]
        slice_ = build_slice(["port_disruption"], include_variables=keep)
        self.assertEqual({v.id for v in slice_.variables}, set(keep))
        for edge in slice_.edges:
            self.assertIn(edge.source, keep)
            self.assertIn(edge.target, keep)
        self.assertTrue(any(e.startswith("variable:") for e in slice_.excluded_systems))

    def test_slice_carries_assumptions_and_missing_evidence(self) -> None:
        slice_ = build_slice(["port_disruption"])
        self.assertTrue(slice_.assumptions)
        self.assertTrue(slice_.missing_evidence)
        kinds = {a["kind"] for a in slice_.assumptions}
        self.assertEqual(kinds, {"causal_edge", "variable_dynamics", "assumption_axis"})

    def test_variable_specs_feed_the_shared_bounds_enforcer(self) -> None:
        """Specs must be consumable by model.valuespec (reused, not reimplemented)."""
        from model.valuespec import clamp_state_to_specs

        slice_ = build_slice(["port_disruption"])
        specs = slice_.variable_specs()
        clamped = clamp_state_to_specs({"service_level": 5.0, "port_capacity": -20.0}, specs)
        self.assertLessEqual(clamped["service_level"], 1.0)
        self.assertGreaterEqual(clamped["port_capacity"], 0.0)

    def test_describe_slice_is_json_serialisable(self) -> None:
        payload = describe_slice(build_slice(["port_disruption"]))
        json.dumps(payload)  # must not raise
        self.assertIn("coverage", payload)
        self.assertIn("excluded_systems", payload)

    def test_slice_requires_at_least_one_module(self) -> None:
        with self.assertRaises(ValueError):
            build_slice([])

    def test_slices_do_not_share_state_with_the_cached_module(self) -> None:
        """
        Regression: modules are cached process-wide. If a slice handed out the registry's
        own edge objects, tuning a slice (a calibration trial, a replay baseline override,
        a user editing an assumption) would silently rewrite the shipped module for every
        later run in the process.
        """
        first = build_slice(["port_disruption"])
        original_effect = first.edges[0].effect.central
        original_baseline = first.variables[0].baseline

        first.edges[0].effect.central = 99.0
        first.variables[0].baseline = -1234.0

        second = build_slice(["port_disruption"])
        self.assertEqual(second.edges[0].effect.central, original_effect)
        self.assertEqual(second.variables[0].baseline, original_baseline)
        self.assertEqual(get_module("port_disruption").edges[0].effect.central, original_effect)


class TestHistoricalScaffolding(unittest.TestCase):
    """The replay architecture must exist and must refuse to fake a validation result."""

    def test_shipped_historical_data_carries_full_provenance(self) -> None:
        """
        This directory is no longer empty (yantian_2021 was added), so the guarantee under
        test changed from 'nothing is shipped' to 'nothing is shipped without provenance'.
        """
        episodes = replay.available_episodes()
        self.assertTrue(episodes)
        self.assertTrue((replay.EVENTS_DIR / "README.md").is_file())
        self.assertTrue((replay.OBSERVATIONS_DIR / "README.md").is_file())
        for summary in episodes:
            with self.subTest(episode=summary["id"]):
                self.assertTrue(summary["knowledge_cutoff"], "episode must declare a cutoff")
                episode = replay.load_episode(str(summary["id"]))
                self.assertTrue(episode.why_this_event)
                for obs in replay.load_observations(episode.id):
                    self.assertTrue(obs.source)
                    self.assertTrue(obs.available_at)

    def test_missing_episode_fails_loudly(self) -> None:
        with self.assertRaises(FileNotFoundError):
            replay.load_episode("an_episode_that_was_never_added")

    def test_evaluation_refuses_to_score_without_observed_data(self) -> None:
        with self.assertRaises(evaluation.InsufficientObservationsError):
            evaluation.evaluate_replay({"envelope": {}}, [])

    def test_evaluation_skips_non_observed_points(self) -> None:
        assumed = [HistoricalObservation(variable="x", turn=1, value=1.0, status="expert_assumption")]
        with self.assertRaises(evaluation.InsufficientObservationsError):
            evaluation.evaluate_replay({"envelope": {}}, assumed)

    def test_replay_runs_a_synthetic_episode_end_to_end(self) -> None:
        """Architecture check with an explicitly synthetic episode — not historical data."""
        episode = replay.HistoricalEpisode(
            id="synthetic_check",
            title="Synthetic architecture check (not a historical event)",
            modules=["port_disruption"],
            event=EventDefinition(
                id="synthetic", targets={"port_capacity": -50.0},
                start_turn=1, duration=3, status="user_assumption",
            ),
            turns=8,
            # A cutoff is mandatory: a replay with no declared knowledge boundary cannot be
            # shown to be free of hindsight, and replay_episode now refuses to run one.
            start_date="2020-01-06",
            knowledge_cutoff="2020-01-06",
        )
        result = replay.replay_episode(episode)
        self.assertEqual(result["world_count"], 27)
        env = result["envelope"]["service_level"]
        self.assertEqual(len(env["low"]), 9)
        for low, high in zip(env["low"], env["high"]):
            self.assertLessEqual(low, high)

        observed = [
            HistoricalObservation(variable="service_level", turn=t, value=env["median"][t],
                                  status="observed", source="synthetic")
            for t in range(1, 8)
        ]
        scored = evaluation.evaluate_replay(result, observed)
        self.assertEqual(scored["overall_coverage_rate"], 1.0)  # median is inside its own envelope
        self.assertEqual(scored["skipped_records"], [])


if __name__ == "__main__":
    unittest.main()
