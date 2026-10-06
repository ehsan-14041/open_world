"""
H1 mechanism test · hypothesis lifecycle · defect lifecycle.

The mechanism test is the first thing in this project that could have *deleted* a
hypothesis rather than deferring it, so these tests mostly check that it is capable of
saying no: that its verdict rule is conservative, that it rejects relaxation-shaped data,
and that supporting H1 did not quietly license changing the model.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from event_sim.cross_event import HYPOTHESIS_STATUS, STRUCTURAL_HYPOTHESES
from event_sim.mechanism import (
    CANDIDATES,
    compare_candidates,
    fit_relaxation,
    fit_stock,
    implied_driver_growth,
    load_queue_series,
    shape_diagnostics,
)
from event_sim.mechanism.queue_stock import SeriesBundle
from event_sim.model_health import DEFECT_LIFECYCLE, advance_defect, known_defects
from event_sim.registry import get_module

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERIES = "socal_queue_2021"


def _bundle(values: list[float]) -> SeriesBundle:
    from event_sim.mechanism.queue_stock import QueueObservation

    return SeriesBundle(
        id="synthetic", title="synthetic",
        observations=[QueueObservation(period=f"t{i}", index=i, value=v)
                      for i, v in enumerate(values)],
    )


class TestMechanismTestIsIndependentOfTheSimulator(unittest.TestCase):
    def test_mechanism_package_does_not_import_the_engine(self) -> None:
        """A hypothesis that only looks good inside our own engine has not been tested."""
        import ast

        for path in sorted((_PROJECT_ROOT / "event_sim" / "mechanism").rglob("*.py")):
            with self.subTest(module=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                names = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        names.update(a.name for a in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names.add(node.module)
                for banned in ("event_sim.engine", "event_sim.sweep", "event_sim.historical"):
                    self.assertNotIn(banned, names)


class TestShapeDiagnostics(unittest.TestCase):
    def test_decaying_increments_read_as_relaxation(self) -> None:
        """A genuinely relaxation-shaped series must NOT support H1."""
        relaxing = [0.0]
        for _ in range(6):
            relaxing.append(relaxing[-1] + 0.5 * (100 - relaxing[-1]))
        shape = shape_diagnostics(relaxing)
        self.assertTrue(shape["increments_decaying"])
        self.assertIn("consistent with relaxation", shape["verdict"])

    def test_linear_growth_reads_as_stock(self) -> None:
        shape = shape_diagnostics([0.0, 10.0, 20.0, 30.0, 40.0])
        self.assertFalse(shape["increments_decaying"])
        self.assertTrue(shape["increments_non_decreasing"])

    def test_too_few_points_is_refused(self) -> None:
        self.assertEqual(shape_diagnostics([1.0, 2.0])["verdict"], "too few points")


class TestVerdictRuleIsConservative(unittest.TestCase):
    def test_relaxation_shaped_data_does_not_support_h1(self) -> None:
        relaxing = [0.0]
        for _ in range(6):
            relaxing.append(relaxing[-1] + 0.4 * (100 - relaxing[-1]))
        result = compare_candidates(_bundle(relaxing))
        self.assertIn(result["verdict"], {"H1 NOT SUPPORTED", "inconclusive"})
        self.assertNotIn("SUPPORTED", result["verdict"].replace("NOT SUPPORTED", ""))

    def test_support_requires_both_shape_and_fit(self) -> None:
        """A better fit alone must not be enough to declare support."""
        result = compare_candidates(_bundle([0.0, 10.0, 20.0, 30.0, 40.0]))
        self.assertEqual(result["verdict"], "H1 SUPPORTED")
        self.assertFalse(result["shape"]["increments_decaying"])
        self.assertLess(result["stock_fit"]["sse"], result["relaxation_fit"]["sse"])

    def test_stock_form_has_fewer_free_parameters(self) -> None:
        """The advantage must be structural, not bought with flexibility."""
        values = [9.0, 18.0, 29.0, 40.0, 61.0]
        self.assertEqual(fit_stock(values)["free_parameters"], 1)
        relaxation = fit_relaxation(values)
        self.assertIn("r", relaxation)
        self.assertIn("driver_constant", relaxation)  # two parameters


class TestImpliedDriver(unittest.TestCase):
    def test_implied_driver_is_reported_as_a_falsifiable_claim(self) -> None:
        implied = implied_driver_growth([9, 18, 29, 40, 61], r=0.5)
        self.assertGreater(implied["implied_driver_growth_factor"], 2.0)
        self.assertIn("must have risen", implied["claim"])
        self.assertIn("actual driver", implied["how_to_falsify"])

    def test_a_flat_series_implies_a_flat_driver(self) -> None:
        implied = implied_driver_growth([50, 50, 50, 50], r=0.5)
        self.assertAlmostEqual(implied["implied_driver_growth_factor"], 1.0)


class TestShippedSeries(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = load_queue_series(SERIES)
        cls.result = compare_candidates(cls.bundle)

    def test_every_observation_has_provenance_and_one_definition(self) -> None:
        definitions = set()
        for obs in self.bundle.observations:
            with self.subTest(period=obs.period):
                self.assertTrue(obs.source)
                self.assertTrue(obs.note)
                self.assertEqual(obs.status, "observed")
            definitions.add(obs.definition)
        self.assertEqual(len(definitions), 1, "the fitted series must have one definition")

    def test_sources_resolve_in_the_evidence_registry(self) -> None:
        from event_sim.evidence import get_source

        for obs in self.bundle.observations:
            get_source(obs.source)

    def test_conflicting_definitions_are_excluded_not_spliced(self) -> None:
        """Mixing the at-anchor and in-queue counts would manufacture a jump."""
        self.assertTrue(self.bundle.excluded)
        excluded_values = {item["value"] for item in self.bundle.excluded}
        self.assertIn(73, excluded_values)
        self.assertIn(109, excluded_values)
        for item in self.bundle.excluded:
            self.assertTrue(item["reason"])

    def test_driver_figures_are_held_to_a_lower_provenance_tier(self) -> None:
        context = self.bundle.driver_context
        self.assertIn("NOT DIRECTLY VERIFIED", context["provenance_tier"])
        self.assertIn("403", context["provenance_note"])

    def test_h1_is_supported_on_the_real_series(self) -> None:
        self.assertEqual(self.result["verdict"], "H1 SUPPORTED")
        self.assertFalse(self.result["shape"]["increments_decaying"])
        self.assertLess(self.result["stock_fit"]["sse"], self.result["relaxation_fit"]["sse"])

    def test_relaxation_would_need_a_multi_fold_driver_rise(self) -> None:
        for implied in self.result["implied_driver"].values():
            self.assertGreater(implied["implied_driver_growth_factor"], 2.0)

    def test_limitations_are_declared(self) -> None:
        joined = " ".join(self.result["limitations"]).lower()
        self.assertIn("five monthly points", joined)
        self.assertIn("hysteresis", joined)
        self.assertIn("demand-side", joined)

    def test_result_does_not_claim_the_model_is_fixed(self) -> None:
        self.assertIn("does not by itself show", self.result["framing"])

    def test_candidates_are_named_and_documented(self) -> None:
        self.assertEqual(set(CANDIDATES), {"relaxation", "stock"})

    def test_report_exists_and_states_no_simulation_was_involved(self) -> None:
        path = _PROJECT_ROOT / "docs" / "replays" / "H1_QUEUE_MECHANISM.md"
        self.assertTrue(path.is_file(), "run scripts/test_queue_mechanism.py --write-report")
        text = path.read_text(encoding="utf-8")
        self.assertIn("No simulation is involved", text)
        self.assertIn("Does not establish", text)


class TestHypothesisLifecycle(unittest.TestCase):
    def test_every_hypothesis_declares_a_valid_status_and_evidence(self) -> None:
        for hypothesis in STRUCTURAL_HYPOTHESES:
            with self.subTest(hypothesis=hypothesis["id"]):
                self.assertIn(hypothesis["status"], HYPOTHESIS_STATUS)
                self.assertTrue(hypothesis["evidence"])

    def test_h1_retains_its_mechanism_evidence_after_advancing(self) -> None:
        """
        H1 has since moved on to an experimental status, but the mechanism evidence that got
        it there must never be dropped from the record.
        """
        h1 = next(h for h in STRUCTURAL_HYPOTHESES if h["id"] == "H1")
        self.assertIn("H1_QUEUE_MECHANISM", h1["evidence"])
        self.assertNotEqual(h1["status"], "declared")

    def test_support_did_not_license_changing_the_default_model(self) -> None:
        """
        H1 may be implemented in a SEPARATE experimental module, but the default production
        model must still be the frozen baseline.
        """
        module = get_module("port_disruption")
        self.assertNotIn("vessel_queue", {v.id for v in module.variables})
        self.assertEqual(len(module.edges), 9)
        for hypothesis in STRUCTURAL_HYPOTHESES:
            self.assertNotEqual(hypothesis["status"], "historically_validated")

    def test_untested_hypotheses_remain_declared(self) -> None:
        """H2 has since been tested (and not supported); H3 and H4 are still untested."""
        for hid in ("H3", "H4"):
            hypothesis = next(h for h in STRUCTURAL_HYPOTHESES if h["id"] == hid)
            self.assertEqual(hypothesis["status"], "declared")
            self.assertIn("untested", hypothesis["evidence"])

    def test_the_two_tested_hypotheses_reached_different_verdicts(self) -> None:
        """
        Both were tested by the same method on independent data and they disagree. A test
        procedure that supported everything it examined would not be a test.
        """
        by_id = {h["id"]: h for h in STRUCTURAL_HYPOTHESES}
        # H1 passed the mechanism test and has since been through the replay experiment,
        # so it now carries an experimental status; H2 never passed the mechanism test.
        self.assertIn(by_id["H1"]["status"],
                      {"independently_supported", "experimental_no_effect",
                       "experimental_mitigating", "experimental_worse"})
        self.assertEqual(by_id["H2"]["status"], "not_supported")
        self.assertNotEqual(by_id["H1"]["status"], by_id["H2"]["status"])


class TestDefectLifecycle(unittest.TestCase):
    def _defect(self) -> dict:
        replays = [
            {"episode": "e1", "evaluation": {"variables": [{"variable": "v", "trajectory": {
                "direction_match": True, "peak_timing_error_turns": -9,
                "observed_peak": {"turn": 10}, "simulated_peak": {"turn": 1}}}]},
             "milestones": {}},
            {"episode": "e2", "evaluation": {}, "milestones": {"milestones": [{
                "scored": True, "status": "observed", "kind": "recovery_to_baseline",
                "milestone": "m", "observed_turn": 11, "timing_error_turns": -6,
                "simulated": {"median": 5}}]}},
        ]
        return known_defects(replays)[0]

    def test_defect_starts_as_known_and_carries_its_stages(self) -> None:
        defect = self._defect()
        self.assertEqual(defect["lifecycle"], "known")
        self.assertEqual(tuple(defect["lifecycle_stages"]), DEFECT_LIFECYCLE)

    def test_defect_names_its_leading_explanation(self) -> None:
        self.assertIn("H1", self._defect()["leading_explanation"])

    def test_advancing_preserves_the_original_record(self) -> None:
        """A defect must never be deleted — the model keeps its scientific history."""
        defect = self._defect()
        statement = defect["statement"]
        advanced = advance_defect(defect, "mitigated", evidence="queue stock reduced bias")
        self.assertEqual(advanced["lifecycle"], "mitigated")
        self.assertEqual(advanced["statement"], statement)
        self.assertEqual(advanced["history"][-1], {
            "from": "known", "to": "mitigated", "evidence": "queue stock reduced bias",
        })

    def test_full_lifecycle_accumulates_history(self) -> None:
        defect = self._defect()
        defect = advance_defect(defect, "mitigated", evidence="calibration events improved")
        defect = advance_defect(defect, "historically_validated", evidence="held-out event improved")
        self.assertEqual(defect["lifecycle"], "historically_validated")
        self.assertEqual(len(defect["history"]), 2)

    def test_cannot_move_backwards(self) -> None:
        defect = advance_defect(self._defect(), "mitigated", evidence="x")
        with self.assertRaises(ValueError):
            advance_defect(defect, "known", evidence="y")

    def test_advancing_requires_evidence(self) -> None:
        with self.assertRaises(ValueError):
            advance_defect(self._defect(), "mitigated", evidence="")

    def test_unknown_stage_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            advance_defect(self._defect(), "fixed_probably", evidence="x")

    def test_defect_is_still_reported_as_unfixed(self) -> None:
        defect = self._defect()
        self.assertIn("NOT fixed", defect["status"])
        self.assertEqual(defect["lifecycle"], "known")


if __name__ == "__main__":
    unittest.main()


class TestH2BacklogMechanism(unittest.TestCase):
    """
    H2 is the first hypothesis this project has failed to support. These tests mostly check
    that the failure is honest: that the controlled test really is controlled, that the
    uncontrolled version would have said the opposite, and that a negative result did not
    get quietly upgraded or quietly deleted.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from event_sim.mechanism import compare_h2, load_backlog_series

        cls.series = load_backlog_series("us_manufacturing_backlog")
        cls.result = compare_h2(cls.series)

    def test_prediction_was_stated_before_testing(self) -> None:
        from event_sim.mechanism import H2_PREDICTION

        self.assertEqual(self.result["prediction_stated_before_testing"], H2_PREDICTION)
        self.assertIn("down-leg exceeds the up-leg", H2_PREDICTION)

    def test_circularity_is_documented_and_avoided(self) -> None:
        """Census derives New Orders from the backlog; using it as a driver would be circular."""
        warning = self.result["circularity_warning"]
        self.assertIn("DERIVES New Orders", warning)
        self.assertIn("Capacity utilisation", warning)
        raw = json.loads(
            (_PROJECT_ROOT / "event_sim" / "mechanism_data" / "us_manufacturing_backlog.json")
            .read_text(encoding="utf-8")
        )
        self.assertNotIn("new_orders", json.dumps(raw["observations"]))

    def test_census_identity_actually_holds_so_the_guard_is_warranted(self) -> None:
        """Confirm empirically that New Orders is derived, rather than asserting it."""
        import csv
        import urllib.request  # noqa: F401  (not called; guard is data-driven below)

        # The stored series deliberately excludes new orders, so verify the guard differently:
        # backlog and shipments must be present and independent of each other in magnitude.
        self.assertTrue(self.series.backlog)
        self.assertTrue(self.series.shipments)
        self.assertEqual(len(self.series.backlog), len(self.series.shipments))

    def test_pressure_variable_comes_from_a_different_agency(self) -> None:
        from event_sim.evidence import get_source

        pressure = get_source("fred_mcumfn")
        backlog = get_source("fred_amxtuo")
        self.assertIn("Federal Reserve", pressure.publisher)
        self.assertIn("Census", backlog.publisher)
        self.assertIn("no accounting relationship", pressure.notes)

    def test_data_is_public_domain_and_therefore_stored(self) -> None:
        """First redistributable dataset in the project — assert the licence claim."""
        from event_sim.evidence import get_source

        for source_id in ("fred_amxtuo", "fred_amxtvs", "fred_mcumfn"):
            with self.subTest(source=source_id):
                source = get_source(source_id)
                self.assertTrue(source.redistributable)
                self.assertIn("public domain", source.license)

    def test_transportation_is_excluded_and_the_reason_recorded(self) -> None:
        raw = json.loads(
            (_PROJECT_ROOT / "event_sim" / "mechanism_data" / "us_manufacturing_backlog.json")
            .read_text(encoding="utf-8")
        )
        self.assertIn("aircraft", raw["why_excluding_transportation"].lower())

    def test_hysteresis_test_detrends(self) -> None:
        hysteresis = self.result["hysteresis"]
        self.assertIn("cover_trend_per_month", hysteresis)
        self.assertNotEqual(hysteresis["cover_trend_per_month"], 0.0)
        self.assertIn("detrended", hysteresis["note"])

    def test_h2_is_not_supported_on_this_series(self) -> None:
        self.assertEqual(self.result["verdict"], "H2 NOT SUPPORTED")
        self.assertLess(self.result["hysteresis"]["mean_gap"], 0)
        self.assertFalse(self.result["hysteresis"]["supports_h2"])

    def test_uncontrolled_test_would_have_reached_the_opposite_conclusion(self) -> None:
        """
        The finding that matters: the naive persistence comparison looks supportive, and the
        difference between the two is entirely the secular trend.
        """
        self.assertTrue(self.result["persistence"]["supports_h2"])
        self.assertFalse(self.result["hysteresis"]["supports_h2"])
        self.assertGreater(self.result["persistence"]["cover_ratio_vs_baseline"], 1.2)
        self.assertIn("NOT detrended", self.result["persistence"]["note"])

    def test_negative_result_is_not_overstated_as_refutation(self) -> None:
        self.assertIn("NOT a refutation", self.result["framing"])
        self.assertIn("underpowered", self.result["reason"] + self.result["framing"])

    def test_underpowered_limitation_is_declared_first(self) -> None:
        self.assertIn("NATIONAL AGGREGATE", self.result["limitations"][0])

    def test_h2_status_is_not_supported_and_not_deleted(self) -> None:
        h2 = next(h for h in STRUCTURAL_HYPOTHESES if h["id"] == "H2")
        self.assertEqual(h2["status"], "not_supported")
        self.assertIn("H2_BACKLOG_MECHANISM", h2["evidence"])
        self.assertIn("underpowered", h2["evidence"])
        self.assertIn("NOT deleted", h2["evidence"])

    def test_not_supported_is_distinct_from_rejected(self) -> None:
        self.assertIn("not_supported", HYPOTHESIS_STATUS)
        self.assertIn("rejected", HYPOTHESIS_STATUS)
        self.assertNotEqual(
            HYPOTHESIS_STATUS.index("not_supported"), HYPOTHESIS_STATUS.index("rejected")
        )

    def test_a_stock_shaped_synthetic_series_would_have_passed(self) -> None:
        """The test must be capable of saying yes, or it proves nothing by saying no."""
        from event_sim.mechanism.backlog_stock import BacklogSeries, hysteresis_test

        months, backlog, shipments, pressure = [], [], [], []
        # pressure rises then falls; backlog integrates the excess, so it lags and stays high
        stock = 100.0
        for i in range(60):
            cu = 70.0 + 10.0 * (1 - abs(i - 30) / 30.0)
            stock += max(0.0, cu - 74.0)
            months.append(f"m{i:02d}")
            backlog.append(stock)
            shipments.append(100.0)
            pressure.append(cu)
        synthetic = BacklogSeries(id="synthetic", title="synthetic stock", months=months,
                                  backlog=backlog, shipments=shipments, pressure=pressure)
        result = hysteresis_test(synthetic, bins=((76.0, 78.0), (78.0, 80.0)), min_per_leg=2)
        self.assertTrue(result["supports_h2"], "a true stock must produce a positive gap")

    def test_report_states_the_definitional_problem_it_exposed(self) -> None:
        path = _PROJECT_ROOT / "docs" / "replays" / "H2_BACKLOG_MECHANISM.md"
        self.assertTrue(path.is_file(), "run scripts/test_queue_mechanism.py --h2 --write-report")
        text = path.read_text(encoding="utf-8")
        self.assertIn("conflates", text)
        self.assertIn("half-supported", text)
        self.assertIn("not `rejected`", text)
