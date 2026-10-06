"""
Evidence layer: source validation, broken references, status-vs-provenance rules,
proxy mappings, unit transformations, evidence strength and the gap report.

The point of these tests is that the evidence layer must *refuse* things. A layer that
accepts every claim is decoration; most of what follows asserts a rejection.
"""

from __future__ import annotations

import copy
import unittest

from event_sim.evidence import (
    EvidenceRegistryError,
    all_mappings,
    all_sources,
    data_requirements,
    evidence_gap_report,
    evidence_strength,
    get_mapping,
    get_source,
    mappings_for_variable,
    resolve_source_ids,
    source_summary,
    structural_influence,
    validate_edge_provenance,
    validate_slice_provenance,
    weighted_coverage,
)
from event_sim.evidence.coverage import merge_influence
from event_sim.evidence.registry import SOURCES_PATH
from event_sim.evidence.schema import (
    CalibrationRecord,
    EvidenceSource,
    FittingProvenance,
    ProxyMapping,
)
from event_sim.evidence import transforms
from event_sim.schemas import CausalEdgeEvidence, EffectRange, Evidence, Lag
from event_sim.scenarios.port_disruption import build_world_slice


def _edge(**kwargs) -> CausalEdgeEvidence:
    defaults = dict(
        source="port_capacity", target="shipping_delay", polarity="negative",
        effect=EffectRange(0.6, 0.9, 1.3), status="expert_assumption", lag=Lag(0, 1),
    )
    defaults.update(kwargs)
    return CausalEdgeEvidence(**defaults)  # type: ignore[arg-type]


class TestEvidenceSourceValidation(unittest.TestCase):
    def test_registry_loads_shipped_sources(self) -> None:
        sources = all_sources()
        self.assertTrue(sources, "sources.json should not be empty")
        self.assertTrue(SOURCES_PATH.is_file())
        for source in sources:
            with self.subTest(source=source.id):
                self.assertTrue(source.title)
                self.assertTrue(source.is_citable(), f"{source.id} has no url/doi/publisher")
                self.assertTrue(source.accessed_at, f"{source.id} records no access date")

    def test_every_shipped_source_is_checkable(self) -> None:
        """A source nobody can go and verify is not evidence."""
        for source in all_sources():
            with self.subTest(source=source.id):
                self.assertTrue(source.url or source.doi)

    def test_unknown_source_id_raises(self) -> None:
        with self.assertRaises(EvidenceRegistryError):
            get_source("source_that_does_not_exist")

    def test_source_summary_is_serialisable(self) -> None:
        import json

        json.dumps(source_summary())

    def test_reference_resolution_accepts_both_spellings(self) -> None:
        known = all_sources()[0].id
        self.assertEqual(resolve_source_ids([f"source:{known}"])[0].id, known)
        self.assertEqual(resolve_source_ids([known])[0].id, known)

    def test_broken_evidence_reference_raises(self) -> None:
        with self.assertRaises(EvidenceRegistryError):
            resolve_source_ids(["source:nope_not_here"])


class TestStatusProvenanceRules(unittest.TestCase):
    """A status must be backed by the provenance it implies."""

    def test_assumption_statuses_need_nothing(self) -> None:
        for status in ("expert_assumption", "user_assumption", "ai_hypothesis"):
            with self.subTest(status=status):
                self.assertEqual(validate_edge_provenance(_edge(status=status)), [])

    def test_literature_backed_with_no_source_is_rejected(self) -> None:
        errors = validate_edge_provenance(_edge(status="literature_backed", evidence=[]))
        self.assertTrue(errors)
        self.assertIn("resolvable source reference", errors[0])

    def test_literature_backed_with_broken_reference_is_rejected(self) -> None:
        edge = _edge(
            status="literature_backed",
            evidence=[Evidence(type="academic_study", reference="source:ghost_study")],
        )
        errors = validate_edge_provenance(edge)
        self.assertTrue(any("Unknown evidence source" in e for e in errors))

    def test_literature_backed_with_a_real_source_is_accepted(self) -> None:
        known = next(s for s in all_sources() if s.type in ("technical_report", "press_release"))
        edge = _edge(
            status="literature_backed",
            evidence=[Evidence(type=known.type, reference=f"source:{known.id}")],
        )
        self.assertEqual(validate_edge_provenance(edge), [])

    def test_empirical_without_fitting_provenance_is_rejected(self) -> None:
        known = next(s for s in all_sources() if s.type in ("press_release", "industry_index",
                                                            "dataset", "official_statistics"))
        edge = _edge(status="empirical",
                     evidence=[Evidence(type="dataset", reference=f"source:{known.id}")])
        errors = validate_edge_provenance(edge, fitting=None)
        self.assertTrue(any("FittingProvenance" in e for e in errors))

    def test_empirical_with_zero_observations_is_rejected(self) -> None:
        known = all_sources()[0]
        edge = _edge(status="empirical",
                     evidence=[Evidence(type="dataset", reference=f"source:{known.id}")])
        fitting = FittingProvenance(method="ridge_levels", n_observations=0)
        errors = validate_edge_provenance(edge, fitting=fitting)
        self.assertTrue(any("zero observations" in e for e in errors))

    def test_historically_calibrated_without_a_calibration_record_is_rejected(self) -> None:
        known = all_sources()[0]
        edge = _edge(status="historically_calibrated",
                     evidence=[Evidence(type=known.type, reference=f"source:{known.id}")])
        errors = validate_edge_provenance(edge)
        self.assertTrue(any("calibration record" in e for e in errors))

    def test_shipped_slice_passes_provenance_validation(self) -> None:
        """Every edge in the shipped module honestly declares what it is."""
        self.assertEqual(validate_slice_provenance(build_world_slice().edges), [])


class TestProxyMappings(unittest.TestCase):
    def test_shipped_mappings_load(self) -> None:
        mappings = all_mappings()
        self.assertTrue(mappings)
        for mapping in mappings:
            with self.subTest(mapping=mapping.id):
                self.assertTrue(mapping.simulation_variable)
                self.assertTrue(mapping.rationale)
                for source_id in mapping.source_ids:
                    get_source(source_id)  # must resolve

    def test_proxy_mapping_must_state_limitations(self) -> None:
        """A proxy whose cost is unstated is not understood well enough to use."""
        for mapping in all_mappings():
            if mapping.mapping_type == "proxy":
                with self.subTest(mapping=mapping.id):
                    self.assertTrue(mapping.limitations)

    def test_proxy_without_limitations_is_rejected_on_load(self) -> None:
        bad = ProxyMapping(id="bad", source_metric="x", simulation_variable="shipping_delay",
                           mapping_type="proxy", limitations="")
        self.assertEqual(bad.limitations, "")  # the registry check is what enforces it
        from event_sim.evidence import registry

        original = registry._read_json
        try:
            registry._read_json = lambda path, key: (  # type: ignore[assignment]
                [bad.to_dict()] if key == "mappings" else original(path, key)
            )
            registry.clear_cache()
            with self.assertRaises(EvidenceRegistryError):
                registry.all_mappings()
        finally:
            registry._read_json = original  # type: ignore[assignment]
            registry.clear_cache()

    def test_delay_mapping_declares_its_geography_and_frequency_problems(self) -> None:
        mapping = get_mapping("map_delay_from_si_global")
        self.assertEqual(mapping.simulation_variable, "shipping_delay")
        self.assertEqual(mapping.mapping_type, "proxy")
        for expected in ("GEOGRAPHY", "FREQUENCY", "CONFOUNDING"):
            self.assertIn(expected, mapping.limitations)

    def test_mappings_for_variable(self) -> None:
        self.assertTrue(mappings_for_variable("shipping_delay"))
        self.assertEqual(mappings_for_variable("nonexistent_variable"), [])


class TestUnitTransformations(unittest.TestCase):
    def test_identity(self) -> None:
        self.assertEqual(transforms.get("identity")(4.2), 4.2)

    def test_normalize_against_baseline(self) -> None:
        fn = transforms.get("normalize_against_baseline")
        self.assertAlmostEqual(fn(0.30, baseline=1.0, scale=100.0), 30.0)
        self.assertAlmostEqual(fn(1.0, baseline=1.0, scale=100.0), 100.0)

    def test_percent_change_from_baseline(self) -> None:
        fn = transforms.get("percent_change_from_baseline")
        self.assertAlmostEqual(fn(110.0, baseline=100.0, scale=100.0), 110.0)
        self.assertAlmostEqual(fn(90.0, baseline=100.0, scale=100.0), 90.0)

    def test_index_to_relative_deviation(self) -> None:
        fn = transforms.get("index_to_relative_deviation")
        self.assertAlmostEqual(fn(30.0, baseline=100.0, scale=100.0), -0.7)

    def test_zero_baseline_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            transforms.get("normalize_against_baseline")(1.0, baseline=0.0)
        with self.assertRaises(ValueError):
            transforms.get("index_to_relative_deviation")(1.0, baseline=0.0, scale=0.0)

    def test_apply_preserves_the_raw_value_and_unit(self) -> None:
        """Raw source data must never be overwritten by its normalised form."""
        record = transforms.apply(
            "normalize_against_baseline", 0.30,
            raw_unit="share of normal", target_unit="index",
            baseline=1.0, scale=100.0,
        )
        self.assertEqual(record["raw_value"], 0.30)
        self.assertEqual(record["raw_unit"], "share of normal")
        self.assertEqual(record["value"], 30.0)
        self.assertEqual(record["transformation"], "normalize_against_baseline")
        self.assertEqual(record["parameters"], {"baseline": 1.0, "scale": 100.0})

    def test_unknown_transformation_raises(self) -> None:
        with self.assertRaises(KeyError):
            transforms.get("make_the_numbers_agree")


class TestEvidenceStrengthAndCoverage(unittest.TestCase):
    def test_strength_is_derived_not_assigned(self) -> None:
        result = evidence_strength(_edge(status="expert_assumption"))
        self.assertEqual(result["label"], "low")
        self.assertIn("status_points", result["components"])
        self.assertIn("score >=", result["rule"])

    def test_strength_rises_with_real_sources(self) -> None:
        weak = evidence_strength(_edge(status="expert_assumption"))["score"]
        known = [s for s in all_sources()][:2]
        strong = evidence_strength(_edge(
            status="empirical",
            source="port_capacity", target="order_backlog",  # avoid proxy-mapped variables
            evidence=[Evidence(type=s.type, reference=f"source:{s.id}") for s in known],
        ))
        self.assertGreater(strong["score"], weak)
        self.assertEqual(strong["label"], "high")

    def test_proxy_usage_reduces_strength(self) -> None:
        known = all_sources()[0]
        ev = [Evidence(type=known.type, reference=f"source:{known.id}")]
        # shipping_delay carries a proxy mapping; order_backlog's mapping is also a proxy,
        # so compare against a variable pair with no proxy mapping at all.
        with_proxy = evidence_strength(_edge(status="empirical", target="shipping_delay", evidence=ev))
        without = evidence_strength(_edge(status="empirical", source="inventory_availability",
                                          target="service_level", evidence=ev))
        self.assertTrue(with_proxy["components"]["proxy_mappings"])
        self.assertFalse(without["components"]["proxy_mappings"])
        self.assertLess(with_proxy["score"], without["score"])

    def test_weighted_coverage_differs_from_unweighted(self) -> None:
        slice_ = build_world_slice()
        coverage = weighted_coverage(slice_.edges, merge_influence(slice_))
        self.assertIn("weighted", coverage)
        self.assertIn("weighting_method", coverage["weighted"])
        self.assertAlmostEqual(sum(coverage["weighted"]["shares"].values()), 1.0, places=6)

    def test_weighted_coverage_stops_a_trivial_edge_dominating(self) -> None:
        """A well-sourced but inconsequential edge must not make the model look grounded."""
        slice_ = build_world_slice()
        influence = merge_influence(slice_)
        least = min(influence, key=lambda k: influence[k]["influence"])
        edges = copy.deepcopy(slice_.edges)
        for edge in edges:
            if edge.id == least:
                edge.status = "empirical"
        coverage = weighted_coverage(edges, influence)
        unweighted = coverage["shares"]["observed_empirical"]
        weighted = coverage["weighted"]["shares"]["observed_empirical"]
        self.assertLess(weighted, unweighted)

    def test_structural_influence_is_normalised(self) -> None:
        values = structural_influence(build_world_slice())
        self.assertAlmostEqual(max(values.values()), 1.0)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in values.values()))


class TestEvidenceGapReport(unittest.TestCase):
    def setUp(self) -> None:
        self.slice = build_world_slice()
        self.report = evidence_gap_report(self.slice)

    def test_every_edge_appears_with_influence_and_evidence(self) -> None:
        self.assertEqual(len(self.report["gaps"]), len(self.slice.edges))
        for row in self.report["gaps"]:
            self.assertIn(row["influence_rank"], {"HIGH", "MEDIUM", "LOW", ""})
            self.assertIn(row["evidence"], {"HIGH", "MEDIUM", "LOW"})

    def test_gaps_are_sorted_by_priority(self) -> None:
        priorities = [r["priority"] for r in self.report["gaps"]]
        self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_high_influence_low_evidence_is_detected(self) -> None:
        """The core product output: what matters most and is least known."""
        critical = self.report["high_influence_low_evidence"]
        self.assertTrue(critical, "the all-assumption model must surface at least one priority")
        for row in critical:
            self.assertEqual(row["influence_rank"], "HIGH")
            self.assertEqual(row["evidence"], "LOW")

    def test_well_evidenced_edges_drop_out_of_the_priority_list(self) -> None:
        slice_ = build_world_slice()
        critical_edge = self.report["high_influence_low_evidence"][0]["edge"]
        known = all_sources()[:2]
        for edge in slice_.edges:
            if edge.id == critical_edge:
                edge.status = "empirical"
                edge.evidence = [Evidence(type=s.type, reference=f"source:{s.id}") for s in known]
        after = evidence_gap_report(slice_)
        row = next(r for r in after["gaps"] if r["edge"] == critical_edge)
        self.assertLess(row["priority"], self.report["gaps"][0]["priority"])

    def test_data_requirements_tie_to_specific_edges(self) -> None:
        """No generic 'collect more data' recommendations."""
        requirements = data_requirements(self.report, self.slice)
        self.assertTrue(requirements)
        edge_ids = {e.id for e in self.slice.edges}
        for req in requirements:
            self.assertIn(req["edge"], edge_ids)
            self.assertTrue(req["collect"])
            self.assertTrue(req["why"])
            for item in req["collect"]:
                self.assertIn(item["variable"], {v.id for v in self.slice.variables})


class TestCalibrationRecordSchema(unittest.TestCase):
    def test_prior_is_preserved_alongside_the_calibrated_value(self) -> None:
        record = CalibrationRecord(
            edge_id="a->b", calibration_event_id="ev", method="grid",
            prior_range={"low": 0.6, "central": 0.9, "high": 1.3},
            calibrated_range={"low": 0.45, "central": 0.75, "high": 1.15},
        )
        payload = record.to_dict()
        self.assertEqual(payload["prior_range"]["central"], 0.9)
        self.assertEqual(payload["calibrated_range"]["central"], 0.75)
        self.assertAlmostEqual(payload["movement"], 0.15)

    def test_round_trips_through_json(self) -> None:
        import json

        record = CalibrationRecord(
            edge_id="a->b", calibration_event_id="ev", method="grid",
            prior_range={"central": 1.0}, calibrated_range={"central": 1.2},
            warnings=["short series"],
        )
        again = CalibrationRecord.from_dict(json.loads(json.dumps(record.to_dict())))
        self.assertEqual(again.edge_id, record.edge_id)
        self.assertEqual(again.warnings, ["short series"])

    def test_evidence_source_round_trips(self) -> None:
        import json

        source = EvidenceSource(id="s1", type="dataset", title="T", url="https://example.org",
                                accessed_at="2026-08-08")
        again = EvidenceSource.from_dict(json.loads(json.dumps(source.to_dict())))
        self.assertEqual(again.id, "s1")
        self.assertTrue(again.is_citable())


if __name__ == "__main__":
    unittest.main()
