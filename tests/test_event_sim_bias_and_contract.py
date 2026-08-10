"""
Observability as a World Model contract · bias metrics · known defects · held-out splits.

These cover the guarantees that keep the project honest as it moves toward changing the
model: a node cannot exist without declaring whether it can be seen; the timing bias is
measured with a metric designed for event simulation rather than a generic fit score; a
measured defect is stated on the product surface; and a structural hypothesis cannot be
adopted on an in-sample result.
"""

from __future__ import annotations

import copy
import unittest

from event_sim.cross_event import (
    BIAS_METRIC_DEFINITIONS,
    MIN_EVENTS_FOR_HELD_OUT,
    STRUCTURAL_HYPOTHESES,
    DataSplitError,
    bias_metrics,
    declare_split,
    evaluate_hypothesis,
)
from event_sim.evidence import EvidenceValidationError, validate_module
from event_sim.model_health import known_defects, model_health, render_model_health
from event_sim.registry import get_module
from event_sim.schemas import OBSERVABILITY_ORDER, WorldModule
from event_sim.scenarios.port_disruption import build_world_slice


def _finding(episode: str, kind: str, error: int, *, evidence: str = "observed") -> dict:
    return {
        "episode": episode, "test": f"{kind} test", "kind": kind,
        "observed_turn": 10, "simulated_turn": 10 + error, "error_turns": error,
        "evidence": evidence, "inside_envelope": None, "share_beyond": None, "note": "",
    }


class TestObservabilityIsPartOfTheContract(unittest.TestCase):
    """A node that does not declare whether it can be seen must not load."""

    def _module(self) -> WorldModule:
        return WorldModule.from_dict(get_module("port_disruption").to_dict())

    def test_shipped_module_satisfies_the_contract(self) -> None:
        self.assertEqual(validate_module(get_module("port_disruption"), raise_on_error=False), [])

    def test_missing_observability_class_is_rejected(self) -> None:
        module = self._module()
        module.variables[0].observability_class = "probably_fine"  # type: ignore[assignment]
        errors = validate_module(module, raise_on_error=False)
        self.assertTrue(any("observability_class must be one of" in e for e in errors))

    def test_unjustified_classification_is_rejected(self) -> None:
        """Declaring a variable latent without saying why is not a declaration."""
        module = self._module()
        module.variables[0].observability_note = ""
        with self.assertRaises(EvidenceValidationError) as ctx:
            validate_module(module)
        self.assertIn("observability_note", str(ctx.exception))

    def test_every_class_in_the_taxonomy_is_accepted(self) -> None:
        for observability in OBSERVABILITY_ORDER:
            with self.subTest(observability=observability):
                module = self._module()
                for var in module.variables:
                    var.observability_class = observability
                    var.observability_note = "justified for this test"
                self.assertEqual(validate_module(module, raise_on_error=False), [])

    def test_a_new_module_cannot_default_its_way_past_the_contract(self) -> None:
        """A variable dict with no observability fields must fail, not silently pass."""
        module = WorldModule.from_dict({
            "id": "tiny", "domain": "test",
            "variables": [
                {"id": "a", "baseline": 1.0, "scale": 1.0, "dynamics": {"response": 0.5}},
                {"id": "b", "baseline": 1.0, "scale": 1.0, "dynamics": {"response": 0.5}},
            ],
            "edges": [{"source": "a", "target": "b", "polarity": "positive",
                       "effect": 0.5, "status": "expert_assumption"}],
        })
        errors = validate_module(module, raise_on_error=False)
        self.assertTrue(any("observability_note" in e for e in errors))


class TestBiasMetrics(unittest.TestCase):
    def test_definitions_are_published_with_the_numbers(self) -> None:
        result = bias_metrics([_finding("e1", "peak", -3)])
        self.assertEqual(result["definitions"], BIAS_METRIC_DEFINITIONS)

    def test_peak_and_recovery_are_reported_separately(self) -> None:
        result = bias_metrics([
            _finding("e1", "peak", -9),
            _finding("e2", "recovery_to_baseline", -6),
        ])
        self.assertEqual(result["peak_timing_bias"]["median"], -9)
        self.assertEqual(result["recovery_bias"]["median"], -6)
        self.assertEqual(result["combined_timing_bias"]["n"], 2)

    def test_consistent_negative_bias_across_events_is_systematic(self) -> None:
        result = bias_metrics([
            _finding("e1", "peak", -9),
            _finding("e2", "recovery_to_baseline", -6),
        ])
        combined = result["combined_timing_bias"]
        self.assertTrue(combined["all_same_sign"])
        self.assertTrue(combined["systematic"])
        self.assertEqual(combined["verdict"], "systematically early")

    def test_mixed_signs_are_not_called_systematic(self) -> None:
        """Random model error changes sign between events; that must not read as a bias."""
        result = bias_metrics([
            _finding("e1", "peak", -9),
            _finding("e2", "peak", +7),
        ])
        combined = result["combined_timing_bias"]
        self.assertFalse(combined["all_same_sign"])
        self.assertFalse(combined["systematic"])
        self.assertEqual(combined["verdict"], "no consistent bias")

    def test_one_event_is_never_systematic(self) -> None:
        result = bias_metrics([_finding("e1", "peak", -9), _finding("e1", "peak", -8)])
        self.assertFalse(result["combined_timing_bias"]["systematic"])

    def test_unscored_findings_are_excluded(self) -> None:
        result = bias_metrics([
            _finding("e1", "peak", -9),
            _finding("e2", "recovery_to_baseline", -20, evidence="reported"),
        ])
        self.assertEqual(result["combined_timing_bias"]["n"], 1)

    def test_no_findings_reports_untested(self) -> None:
        result = bias_metrics([])
        self.assertEqual(result["combined_timing_bias"]["verdict"], "untested")
        self.assertIsNone(result["combined_timing_bias"]["median"])


class TestKnownDefects(unittest.TestCase):
    def _replays(self, e1_error: int, e2_error: int) -> list[dict]:
        return [
            {"episode": "e1",
             "evaluation": {"variables": [{"variable": "shipping_delay", "trajectory": {
                 "direction_match": True,
                 "peak_timing_error_turns": e1_error,
                 "observed_peak": {"turn": 10}, "simulated_peak": {"turn": 10 + e1_error},
             }}]},
             "milestones": {}},
            {"episode": "e2",
             "evaluation": {},
             "milestones": {"milestones": [{
                 "scored": True, "status": "observed", "kind": "recovery_to_baseline",
                 "milestone": "m", "observed_turn": 11, "timing_error_turns": e2_error,
                 "simulated": {"median": 11 + e2_error},
             }]}},
        ]

    def test_defect_requires_two_events(self) -> None:
        self.assertEqual(known_defects(self._replays(-9, -6)[:1]), [])

    def test_consistent_early_bias_is_reported_as_a_defect(self) -> None:
        defects = known_defects(self._replays(-9, -6))
        self.assertEqual(len(defects), 1)
        defect = defects[0]
        self.assertEqual(defect["id"], "recovery_dynamics_too_fast")
        self.assertIn("NOT fixed", defect["status"])
        self.assertTrue(defect["why_not_fixed"])
        self.assertTrue(defect["safe_to_use_for"])

    def test_no_defect_when_errors_disagree(self) -> None:
        self.assertEqual(known_defects(self._replays(-9, +6)), [])

    def test_defect_appears_in_model_health_and_its_rendering(self) -> None:
        health = model_health(build_world_slice(), replays=self._replays(-9, -6))
        self.assertTrue(health["known_defects"])
        text = render_model_health(health)
        self.assertIn("KNOWN MODEL DEFECT", text)
        self.assertIn("still safe for", text.lower())

    def test_clean_model_reports_no_defects(self) -> None:
        health = model_health(build_world_slice(), replays=self._replays(0, 0))
        self.assertEqual(health["known_defects"], [])


class TestHeldOutSplit(unittest.TestCase):
    """The next step cannot begin dishonestly."""

    def test_two_events_are_refused(self) -> None:
        """With only Yantian and Baltimore there is no honest split; the guard must say so."""
        with self.assertRaises(DataSplitError) as ctx:
            declare_split(["yantian_2021"], ["baltimore_2024"])
        self.assertIn(str(MIN_EVENTS_FOR_HELD_OUT), str(ctx.exception))
        self.assertIn("EVENT3_SEARCH", str(ctx.exception))

    def test_leakage_is_refused(self) -> None:
        with self.assertRaises(DataSplitError) as ctx:
            declare_split(["a", "b"], ["b"], available=["a", "b", "c"])
        self.assertIn("leakage", str(ctx.exception))

    def test_empty_held_out_is_refused(self) -> None:
        with self.assertRaises(DataSplitError) as ctx:
            declare_split(["a", "b", "c"], [], available=["a", "b", "c"])
        self.assertIn("in-sample", str(ctx.exception))

    def test_unknown_event_is_refused(self) -> None:
        with self.assertRaises(DataSplitError):
            declare_split(["a", "b"], ["zzz"], available=["a", "b", "c"])

    def test_valid_split_is_recorded_as_declared_up_front(self) -> None:
        split = declare_split(["a", "b"], ["c"], available=["a", "b", "c"])
        self.assertEqual(split["held_out_events"], ["c"])
        self.assertTrue(split["declared_before_fitting"])
        self.assertIn("in-sample fit", split["rule"])

    def test_hypothesis_accepted_only_on_out_of_sample_improvement(self) -> None:
        split = declare_split(["a", "b"], ["c"], available=["a", "b", "c"])
        baseline = {"combined_timing_bias": {"median": -6}}
        better = {"combined_timing_bias": {"median": -2}}
        worse = {"combined_timing_bias": {"median": -9}}
        self.assertEqual(evaluate_hypothesis("H1", split, baseline, better)["verdict"], "accept")
        self.assertEqual(evaluate_hypothesis("H1", split, baseline, worse)["verdict"], "reject")

    def test_hypothesis_not_evaluable_without_scored_tests(self) -> None:
        split = declare_split(["a", "b"], ["c"], available=["a", "b", "c"])
        result = evaluate_hypothesis("H1", split, {}, {})
        self.assertEqual(result["verdict"], "not evaluable")

    def test_hypotheses_remain_declared_not_implemented(self) -> None:
        """No structural hypothesis may be adopted before a held-out event exists."""
        self.assertEqual(len(STRUCTURAL_HYPOTHESES), 4)
        module = get_module("port_disruption")
        self.assertNotIn("vessel_queue", {v.id for v in module.variables})
        for hypothesis in STRUCTURAL_HYPOTHESES:
            self.assertTrue(hypothesis["mechanism"])
            self.assertTrue(hypothesis["test"])


class TestEvent3SearchIsRecorded(unittest.TestCase):
    def test_search_record_exists_and_states_the_measurement_trap(self) -> None:
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "docs" / "replays" / "EVENT3_SEARCH.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for expected in ("booking slot", "measurement model", "outcome: not met",
                         "what event #3 must contain"):
            self.assertIn(expected, lowered)

    def test_panama_sources_are_registered_with_the_caution(self) -> None:
        from event_sim.evidence import get_source

        advisory = get_source("acp_advisory_a48_2023")
        self.assertIn("BOOKING SLOTS", advisory.notes)
        self.assertIn("not total daily transits", advisory.notes)
        eia = get_source("eia_panama_2024")
        self.assertTrue(eia.redistributable, "US government publications are public domain")


if __name__ == "__main__":
    unittest.main()
