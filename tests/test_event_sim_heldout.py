"""
Held-out validation infrastructure: freeze integrity, causal scope, endpoint gating,
dataset contract, measurement-risk registry, and the Outcome-B search record.

No held-out evaluation ran — no qualifying Event #3 was retrievable — so these tests cover
the machinery and, just as importantly, the guarantees that stop the standard from being
quietly lowered later.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from event_sim.causal_scope import (
    H1_SCOPE,
    SCOPE_CLASSES,
    CausalScope,
    Endpoint,
    ScopeError,
    assert_aggregatable,
    classify_endpoints,
    derive_downstream,
    split_by_role,
    verify_scope,
)
from event_sim.cross_event import HYPOTHESIS_STATUS, STRUCTURAL_HYPOTHESES, DataSplitError, declare_split
from event_sim.evidence import MEASUREMENT_RISKS, RISK_BY_ID, assess_mapping, validate_risk_ids
from event_sim.freeze import FROZEN_MODULES, module_hash, snapshot, verify
from event_sim.historical.dataset_contract import (
    DatasetRecord,
    DatasetRequirement,
    interpolation_allowed,
    validate_dataset,
)
from event_sim.protocol_lessons import LESSON_BY_ID, PROTOCOL_LESSONS, open_lessons
from event_sim.registry import get_module
from event_sim.world_builder import build_slice

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPLAYS = _PROJECT_ROOT / "docs" / "replays"

#: Recorded in H1_HELDOUT_FREEZE.md before Event #3 was searched for.
FROZEN_HASHES = {
    "port_disruption": "d4670fb108c2e9a3c45d33455a652578e7a72bfce69f88ed44c6b355ead13f5b",
    "port_disruption_h1_queue_experimental": "324a8bf1d67d56ad082b9c7540f7d155466af50ad71359c1b4836ef79f8f3889",
}


class TestFreezeHolds(unittest.TestCase):
    """The models must not have moved since the pre-search snapshot."""

    def test_module_hashes_match_the_freeze_document(self) -> None:
        for module_id, expected in FROZEN_HASHES.items():
            with self.subTest(module=module_id):
                self.assertEqual(module_hash(module_id), expected)

    def test_freeze_document_records_the_same_hashes(self) -> None:
        text = (REPLAYS / "H1_HELDOUT_FREEZE.md").read_text(encoding="utf-8")
        for expected in FROZEN_HASHES.values():
            self.assertIn(expected, text)

    def test_verify_detects_drift(self) -> None:
        tampered = {"modules": {"port_disruption": "0" * 64}, "evaluation_code": ""}
        self.assertTrue(verify(tampered))

    def test_verify_passes_against_its_own_snapshot(self) -> None:
        self.assertEqual(verify(snapshot()), [])

    def test_hash_is_semantic_not_textual(self) -> None:
        """Editing prose must not look like a model change, and vice versa."""
        from event_sim.schemas import WorldModule

        module = WorldModule.from_dict(get_module("port_disruption").to_dict())
        before = module_hash("port_disruption")
        module.description = "totally different prose"
        module.notes = "rewritten"
        from event_sim.freeze import _semantic_dict

        self.assertEqual(
            json.dumps(_semantic_dict(module), sort_keys=True),
            json.dumps(_semantic_dict(get_module("port_disruption")), sort_keys=True),
        )
        self.assertEqual(module_hash("port_disruption"), before)

    def test_a_real_dynamics_change_moves_the_hash(self) -> None:
        from event_sim.freeze import _semantic_dict
        from event_sim.schemas import WorldModule

        module = WorldModule.from_dict(get_module("port_disruption").to_dict())
        module.edges[0].effect.central += 0.01
        self.assertNotEqual(
            json.dumps(_semantic_dict(module), sort_keys=True),
            json.dumps(_semantic_dict(get_module("port_disruption")), sort_keys=True),
        )

    def test_both_models_are_covered(self) -> None:
        self.assertEqual(set(FROZEN_MODULES), set(FROZEN_HASHES))


class TestCausalScope(unittest.TestCase):
    def test_h1_scope_is_consistent_with_the_topology(self) -> None:
        slice_ = build_slice(["port_disruption_h1_queue_experimental"])
        self.assertEqual(verify_scope(H1_SCOPE, slice_), [])

    def test_shipping_delay_is_reachable_from_the_queue(self) -> None:
        slice_ = build_slice(["port_disruption_h1_queue_experimental"])
        self.assertIn("shipping_delay", derive_downstream(slice_, ["vessel_queue"]))

    def test_port_capacity_is_structurally_out_of_scope(self) -> None:
        """H1 sits downstream of capacity, so it cannot move a reopening date."""
        slice_ = build_slice(["port_disruption_h1_queue_experimental"])
        self.assertNotIn("port_capacity", derive_downstream(slice_, ["vessel_queue"]))
        self.assertEqual(H1_SCOPE.classify_variable("port_capacity"), "h1_insensitive")

    def test_scope_claim_inconsistent_with_topology_is_caught(self) -> None:
        slice_ = build_slice(["port_disruption_h1_queue_experimental"])
        bogus = CausalScope(hypothesis="X", direct=("vessel_queue",),
                            downstream=("port_capacity",), outside=("shipping_delay",))
        problems = verify_scope(bogus, slice_)
        self.assertEqual(len(problems), 2)

    def test_unknown_variable_is_uncertain_not_assumed_sensitive(self) -> None:
        self.assertEqual(H1_SCOPE.classify_variable("service_level"), "uncertain_scope")


class TestEndpointGating(unittest.TestCase):
    def _endpoints(self) -> list[Endpoint]:
        return [
            Endpoint(id="delay_peak", variable="shipping_delay", metric="peak_timing",
                     scope_class="h1_sensitive", frozen_at="2026-08-09T18:38:17Z"),
            Endpoint(id="queue_peak", variable="vessel_queue", metric="peak_timing",
                     scope_class="h1_sensitive", frozen_at="2026-08-09T18:38:17Z"),
            Endpoint(id="reopening", variable="port_capacity", metric="recovery_timing",
                     scope_class="h1_insensitive", frozen_at="2026-08-09T18:38:17Z"),
            Endpoint(id="service", variable="service_level", metric="recovery_timing",
                     scope_class="uncertain_scope", frozen_at="2026-08-09T18:38:17Z"),
        ]

    def test_classification_must_agree_with_declared_scope(self) -> None:
        self.assertEqual(classify_endpoints(self._endpoints(), H1_SCOPE), [])

    def test_post_hoc_reclassification_is_caught(self) -> None:
        """Moving the insensitive endpoint into the primary gate must fail."""
        endpoints = self._endpoints()
        endpoints[2].scope_class = "h1_sensitive"
        problems = classify_endpoints(endpoints, H1_SCOPE)
        self.assertTrue(any("reopening" in p for p in problems))

    def test_endpoint_without_a_freeze_timestamp_is_rejected(self) -> None:
        endpoints = self._endpoints()
        endpoints[0].frozen_at = ""
        self.assertTrue(any("freeze timestamp" in p for p in classify_endpoints(endpoints, H1_SCOPE)))

    def test_primary_gate_contains_only_sensitive_endpoints(self) -> None:
        groups = split_by_role(self._endpoints())
        self.assertEqual({e.variable for e in groups["h1_sensitive"]},
                         {"shipping_delay", "vessel_queue"})
        self.assertTrue(all(e.is_primary() for e in groups["h1_sensitive"]))

    def test_safety_gate_holds_the_insensitive_endpoint(self) -> None:
        groups = split_by_role(self._endpoints())
        self.assertEqual([e.id for e in groups["h1_insensitive"]], ["reopening"])
        self.assertTrue(groups["h1_insensitive"][0].is_safety())

    def test_uncertain_endpoints_are_neither_primary_nor_safety(self) -> None:
        endpoint = split_by_role(self._endpoints())["uncertain_scope"][0]
        self.assertFalse(endpoint.is_primary())
        self.assertFalse(endpoint.is_safety())

    def test_cannot_aggregate_across_causal_scopes(self) -> None:
        """The exact mistake the previous protocol made."""
        endpoints = self._endpoints()
        with self.assertRaises(ScopeError) as ctx:
            assert_aggregatable([endpoints[0], endpoints[2]])
        self.assertIn("causal scopes", str(ctx.exception))

    def test_cannot_aggregate_across_metric_semantics(self) -> None:
        endpoints = [
            Endpoint(id="a", variable="shipping_delay", metric="peak_timing",
                     scope_class="h1_sensitive", frozen_at="t"),
            Endpoint(id="b", variable="vessel_queue", metric="clearance_timing",
                     scope_class="h1_sensitive", frozen_at="t"),
        ]
        with self.assertRaises(ScopeError) as ctx:
            assert_aggregatable(endpoints)
        self.assertIn("metric semantics", str(ctx.exception))

    def test_aggregation_allowed_within_one_scope_and_metric(self) -> None:
        endpoints = [e for e in self._endpoints() if e.metric == "peak_timing"]
        assert_aggregatable(endpoints)  # must not raise

    def test_unknown_scope_class_is_rejected(self) -> None:
        with self.assertRaises(ScopeError):
            Endpoint.from_dict({"id": "x", "variable": "y", "scope_class": "probably_fine"})


class TestDatasetContract(unittest.TestCase):
    def _records(self, **overrides) -> list[DatasetRecord]:
        base = dict(event_id="e", location="port", metric="average_waiting_time",
                    unit="days", observation_type="observed", source_id="s",
                    definition_version="v1", quality="observed")
        base.update(overrides)
        values = [1.0, 1.1, 2.0, 4.0, 6.0, 5.0, 3.0, 2.0]
        dates = [f"2030-01-{d:02d}" for d in (1, 8, 15, 22, 29)] + \
                [f"2030-02-{d:02d}" for d in (5, 12, 19)]
        return [DatasetRecord(timestamp=d, value=v, **base) for d, v in zip(dates, values)]

    def test_a_well_shaped_series_qualifies(self) -> None:
        report = validate_dataset(self._records(), event_start="2030-01-15")
        self.assertTrue(report["qualifies"], report["failures"])
        self.assertEqual(report["h1_sensitive_series"], ["average_waiting_time"])

    def test_milestone_only_dataset_is_rejected(self) -> None:
        """The Baltimore failure mode, encoded."""
        records = [DatasetRecord(event_id="e", timestamp="2030-01-15", location="p",
                                 metric="port_capacity", value=0.0, unit="index",
                                 observation_type="observed", source_id="s")]
        report = validate_dataset(records, event_start="2030-01-15")
        self.assertFalse(report["qualifies"])
        self.assertTrue(any("no H1-sensitive series" in f for f in report["failures"]))

    def test_missing_pre_event_baseline_is_rejected(self) -> None:
        report = validate_dataset(self._records(), event_start="2029-12-01")
        self.assertFalse(report["qualifies"])
        self.assertTrue(any("pre-event" in f for f in report["failures"]))

    def test_definition_change_is_detected(self) -> None:
        """The San Pedro failure mode, encoded."""
        records = self._records()
        for record in records[4:]:
            record.definition_version = "v2"
        report = validate_dataset(records, event_start="2030-01-15")
        self.assertFalse(report["qualifies"])
        self.assertTrue(any("definition changes mid-series" in f for f in report["failures"]))

    def test_scheduled_values_are_rejected_as_outcomes(self) -> None:
        """The Panama failure mode, encoded."""
        records = self._records()
        records[3].observation_type = "scheduled"
        report = validate_dataset(records, event_start="2030-01-15")
        self.assertFalse(report["qualifies"])
        self.assertTrue(any("'scheduled', not observed" in f for f in report["failures"]))

    def test_no_observations_after_the_peak_is_rejected(self) -> None:
        records = self._records()[:5]  # ends at the peak
        report = validate_dataset(records, event_start="2030-01-15")
        self.assertFalse(report["qualifies"])
        self.assertTrue(any("after the peak" in f for f in report["failures"]))

    def test_large_gaps_may_not_be_interpolated(self) -> None:
        self.assertTrue(interpolation_allowed(1))
        self.assertFalse(interpolation_allowed(2))
        self.assertFalse(interpolation_allowed(8))
        self.assertFalse(interpolation_allowed(0))

    def test_requirement_is_serialisable_and_explicit(self) -> None:
        payload = DatasetRequirement().to_dict()
        self.assertIn("min_pre_event_observations", payload)
        self.assertIn("forbid_scheduled_as_outcome", payload)


class TestMeasurementRiskRegistry(unittest.TestCase):
    def test_every_known_failure_mode_is_registered(self) -> None:
        for risk_id in ("geographic_mismatch", "temporal_aggregation", "proxy_mismatch",
                        "scheduled_vs_observed", "definition_change",
                        "administrative_rationing", "circular_measurement",
                        "secular_trend", "aggregation_masking"):
            self.assertIn(risk_id, RISK_BY_ID)

    def test_each_risk_cites_where_it_was_encountered(self) -> None:
        for risk in MEASUREMENT_RISKS:
            with self.subTest(risk=risk.id):
                self.assertTrue(risk.encountered_in)
                self.assertTrue(risk.detection)
                self.assertTrue(risk.mitigation)

    def test_unknown_risk_id_is_rejected(self) -> None:
        self.assertTrue(validate_risk_ids(["not_a_real_risk"]))
        self.assertEqual(validate_risk_ids(["secular_trend"]), [])

    def test_global_monthly_proxy_mapping_is_flagged(self) -> None:
        from event_sim.evidence import get_mapping

        assessment = assess_mapping(get_mapping("map_delay_from_si_global"))
        for expected in ("geographic_mismatch", "temporal_aggregation", "proxy_mismatch"):
            self.assertIn(expected, assessment["suspected_undeclared"])


class TestProtocolLessons(unittest.TestCase):
    def test_the_aggregation_flaw_is_recorded(self) -> None:
        lesson = LESSON_BY_ID["mixed_causal_scope_aggregate"]
        self.assertIn("causal scope", lesson.issue)
        self.assertIn("experimental_no_effect", lesson.consequence)

    def test_no_lesson_rewrites_a_historical_verdict(self) -> None:
        for lesson in PROTOCOL_LESSONS:
            with self.subTest(lesson=lesson.id):
                self.assertTrue(lesson.verdict_unchanged)

    def test_the_blocked_heldout_is_recorded_as_open(self) -> None:
        self.assertIn("heldout_blocked_by_data_access", {l.id for l in open_lessons()})


class TestOutcomeBIsRecordedHonestly(unittest.TestCase):
    def test_search_record_and_decision_memo_exist(self) -> None:
        self.assertTrue((REPLAYS / "EVENT3_SEARCH_V2.md").is_file())
        self.assertTrue((REPLAYS / "EVENT3_DATA_DECISION.md").is_file())
        self.assertTrue((REPLAYS / "EVENT3_ELIGIBILITY_CONTRACT.md").is_file())

    def test_contract_was_written_before_the_search(self) -> None:
        contract = (REPLAYS / "EVENT3_ELIGIBILITY_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("before any candidate was searched", contract.lower())

    def test_contract_contains_no_model_performance_criterion(self) -> None:
        """Selection must be about data, never about how H1 scores."""
        contract = (REPLAYS / "EVENT3_ELIGIBILITY_CONTRACT.md").read_text(encoding="utf-8").lower()
        for banned in ("timing_bias", "mae", "correlation improves", "envelope coverage improves"):
            self.assertNotIn(banned, contract)

    def test_search_record_states_no_qualifying_candidate(self) -> None:
        text = (REPLAYS / "EVENT3_SEARCH_V2.md").read_text(encoding="utf-8")
        self.assertIn("No qualifying candidate", text)
        self.assertIn("H1 was not run on any candidate", text)

    def test_disqualified_events_are_named(self) -> None:
        text = (REPLAYS / "EVENT3_SEARCH_V2.md").read_text(encoding="utf-8")
        for used in ("San Pedro", "Yantian", "Baltimore"):
            self.assertIn(used, text)

    def test_no_heldout_results_report_was_fabricated(self) -> None:
        """No held-out evaluation ran, so no results report may exist."""
        self.assertFalse((REPLAYS / "H1_HELDOUT_RESULTS.md").exists())
        self.assertFalse((REPLAYS / "H1_HELDOUT_PROTOCOL.md").exists())


class TestLifecycleUnchangedWithoutAHeldOutEvent(unittest.TestCase):
    def test_h1_status_did_not_advance(self) -> None:
        h1 = next(h for h in STRUCTURAL_HYPOTHESES if h["id"] == "H1")
        self.assertEqual(h1["status"], "experimental_no_effect")
        for forbidden in ("heldout_supported", "historically_validated"):
            self.assertNotEqual(h1["status"], forbidden)

    def test_previous_verdict_text_is_preserved(self) -> None:
        h1 = next(h for h in STRUCTURAL_HYPOTHESES if h["id"] == "H1")
        self.assertIn("criterion 1", h1["evidence"])
        self.assertIn("H1_QUEUE_MECHANISM", h1["evidence"])

    def test_known_defect_stays_known(self) -> None:
        from event_sim.model_health import known_defects

        replays = [
            {"episode": "yantian_2021",
             "evaluation": {"variables": [{"variable": "shipping_delay", "trajectory": {
                 "direction_match": True, "peak_timing_error_turns": -9,
                 "observed_peak": {"turn": 12}, "simulated_peak": {"turn": 3}}}]},
             "milestones": {}},
            {"episode": "baltimore_2024", "evaluation": {},
             "milestones": {"milestones": [{
                 "scored": True, "status": "observed", "kind": "recovery_to_baseline",
                 "milestone": "m", "observed_turn": 11, "timing_error_turns": -6,
                 "simulated": {"median": 5}}]}},
        ]
        defect = known_defects(replays)[0]
        self.assertEqual(defect["lifecycle"], "known")
        self.assertIn("NOT YET", defect["experimental_mechanism"]["historical_validation"])

    def test_heldout_guard_still_refuses_two_events(self) -> None:
        with self.assertRaises(DataSplitError):
            declare_split(["yantian_2021"], ["baltimore_2024"])

    def test_heldout_statuses_exist_but_are_unused(self) -> None:
        used = {h["status"] for h in STRUCTURAL_HYPOTHESES}
        self.assertNotIn("historically_validated", used)


class TestOpsProductUnaffected(unittest.TestCase):
    def test_ops_scenario_still_builds(self) -> None:
        from adapters.ops_scenario_builder import build_scenario, get_decision_template
        from schemas.ops_schema import normalize_ops_profile
        from schemas.scenario_schema import validate_scenario

        profile = normalize_ops_profile({
            "business_unit_type": "distribution", "inventory_on_hand": 8200,
            "weekly_demand": 1100, "fill_rate": 0.89, "lead_time_days": 16,
        })
        scenario = build_scenario(profile, get_decision_template("increase_safety_stock"))
        self.assertEqual(validate_scenario(scenario), [])


if __name__ == "__main__":
    unittest.main()
