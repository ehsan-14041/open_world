"""
ANTAQ ingestion: acquisition state, raw immutability, schema-agnostic profiling, and the
semantic gate that blocks derivation.

**No ANTAQ data was obtained** — every ANTAQ host disallows this crawler — so these tests
cover the pipeline's behaviour on a synthetic file of the right *shape*, plus the guarantees
that stop the standard from being lowered. Nothing here claims the real schema is known.
"""

from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from event_sim.cross_event import STRUCTURAL_HYPOTHESES
from event_sim.ingest import antaq
from event_sim.ingest.antaq import (
    COLUMN_HYPOTHESES,
    REQUIRED_SEMANTIC_CONFIRMATIONS,
    AntaqDataUnavailable,
    SemanticsNotConfirmed,
    discover_raw,
    profile_file,
    register,
    require_semantics,
    semantics_confirmed,
    sniff_delimiter,
    status,
    verify_manifest,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPLAYS = _PROJECT_ROOT / "docs" / "replays"

#: A file of the right SHAPE, used only to exercise the profiler. Column names are the
#: unverified hypotheses — using them here does not assert they are real.
SYNTHETIC_ROWS = [
    "IDAtracacao;Porto Atracacao;Data Chegada;Data Atracacao;Data Desatracacao;Berco",
    "1001;Santos;01/03/2019 08:00:00;02/03/2019 06:00:00;03/03/2019 18:00:00;B1",
    "1002;Santos;01/03/2019 12:00:00;03/03/2019 09:00:00;04/03/2019 20:00:00;B2",
    "1003;Santos;02/03/2019 04:00:00;;;B1",
]


def _make_zip(directory: Path, name: str = "2019Atracacao.zip") -> Path:
    path = directory / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("2019Atracacao.txt", "\n".join(SYNTHETIC_ROWS))
    return path


class TestAcquisitionState(unittest.TestCase):
    """The honest current state: no data, and the reason recorded."""

    def test_no_antaq_data_is_present(self) -> None:
        self.assertEqual(discover_raw(), [], "no ANTAQ file should have been obtained")

    def test_status_reports_the_publisher_policy_blocker(self) -> None:
        state = status()
        self.assertEqual(state["raw_artifacts"], 0)
        self.assertFalse(state["can_profile"])
        self.assertFalse(state["can_derive_waiting_time"])
        self.assertIn("robots.txt", state["blocker"])

    def test_register_refuses_with_no_files(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(AntaqDataUnavailable):
                register(raw_dir=Path(tmp))

    def test_scaffold_exists_and_documents_why_it_is_empty(self) -> None:
        root = _PROJECT_ROOT / "data" / "external" / "antaq"
        for sub in ("raw", "derived", "metadata"):
            self.assertTrue((root / sub).is_dir(), f"{sub}/ should exist")
        readme = " ".join((root / "README.md").read_text(encoding="utf-8").split())
        self.assertIn("ClaudeBot", readme)
        self.assertIn("a crawler policy, **not** a licence restriction", readme)

    def test_acquisition_doc_gives_actionable_human_instructions(self) -> None:
        text = (REPLAYS / "ANTAQ_ACQUISITION.md").read_text(encoding="utf-8")
        for expected in ("estatistica.antaq.gov.br/ea/sense/download.html",
                         "2017", "2024", "data/external/antaq/raw",
                         "Disallow: /"):
            self.assertIn(expected, text)

    def test_acquisition_doc_does_not_claim_an_audit_happened(self) -> None:
        text = " ".join((REPLAYS / "ANTAQ_ACQUISITION.md").read_text(encoding="utf-8").split())
        self.assertIn("no antaq data was obtained", text.lower())
        self.assertIn("No schema audit, queue reconstruction", text)

    def test_no_data_audit_report_was_fabricated(self) -> None:
        self.assertFalse((REPLAYS / "ANTAQ_DATA_AUDIT.md").exists())
        self.assertFalse((REPLAYS / "ANTAQ_EVENT3_QUALIFICATION.md").exists())
        self.assertFalse((REPLAYS / "ANTAQ_EVENT3_FREEZE.md").exists())


class TestRawImmutabilityAndProvenance(unittest.TestCase):
    def test_register_records_checksums_and_verifies(self) -> None:
        with TemporaryDirectory() as tmp:
            raw = Path(tmp)
            _make_zip(raw)
            manifest = register(retrieved_by="tester", retrieved_at="2026-08-10", raw_dir=raw)
            self.assertEqual(len(manifest["artifacts"]), 1)
            record = manifest["artifacts"][0]
            self.assertEqual(len(record["sha256"]), 64)
            self.assertEqual(record["retrieved_by"], "tester")
            self.assertTrue(manifest["raw_is_immutable"])

    def test_checksums_are_deterministic(self) -> None:
        with TemporaryDirectory() as tmp:
            raw = Path(tmp)
            _make_zip(raw)
            first = discover_raw(raw)[0].sha256
            second = discover_raw(raw)[0].sha256
            self.assertEqual(first, second)

    def test_mutating_a_raw_file_is_detected(self) -> None:
        """Derived results are only trustworthy if the raw layer provably never moved."""
        with TemporaryDirectory() as tmp:
            raw = Path(tmp)
            path = _make_zip(raw)
            manifest = register(raw_dir=raw)
            self.assertEqual(verify_manifest(manifest), [], "unmodified file must verify")

            tampered = json.loads(json.dumps(manifest))
            tampered["artifacts"][0]["sha256"] = "0" * 64
            drift = verify_manifest(tampered)
            self.assertEqual(len(drift), 1)
            self.assertIn("raw layer was mutated", drift[0])

            path.unlink()
            self.assertIn("MISSING", verify_manifest(manifest)[0])

    def test_license_note_distinguishes_policy_from_licence(self) -> None:
        with TemporaryDirectory() as tmp:
            raw = Path(tmp)
            _make_zip(raw)
            note = discover_raw(raw)[0].license_note
            self.assertIn("crawler policy, not a licence restriction", note)


class TestSchemaAgnosticProfiling(unittest.TestCase):
    """The profiler describes; it must not interpret."""

    def test_delimiter_is_sniffed_not_assumed(self) -> None:
        self.assertEqual(sniff_delimiter("a;b;c;d"), ";")
        self.assertEqual(sniff_delimiter("a,b,c,d"), ",")
        self.assertEqual(sniff_delimiter("a\tb\tc"), "\t")

    def test_profile_reports_columns_without_asserting_meaning(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _make_zip(Path(tmp))
            reports = profile_file(path)
            self.assertEqual(len(reports), 1)
            report = reports[0]
            self.assertEqual(report["delimiter"], ";")
            self.assertEqual(report["rows_sampled"], 3)
            for column in report["columns"]:
                with self.subTest(column=column["column"]):
                    self.assertIsNone(column["inferred_meaning"])
                    self.assertIsNone(column["documented_meaning"])
                    self.assertIn("data dictionary", column["note"])

    def test_hypotheses_are_labelled_unverified(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _make_zip(Path(tmp))
            columns = {c["column"]: c for c in profile_file(path)[0]["columns"]}
            arrival = columns["Data Chegada"]
            self.assertIn("possible", arrival["unverified_hypothesis"])
            self.assertIn("arrival WHERE?", arrival["unverified_hypothesis"])

    def test_arrival_hypothesis_flags_the_critical_ambiguity(self) -> None:
        """The whole question is what 'arrival' marks; the code must say so, not assume."""
        self.assertIn("CRITICAL", COLUMN_HYPOTHESES["Data Chegada"])

    def test_missingness_is_measured(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _make_zip(Path(tmp))
            columns = {c["column"]: c for c in profile_file(path)[0]["columns"]}
            self.assertGreater(columns["Data Atracacao"]["missing_fraction"], 0.0)
            self.assertEqual(columns["IDAtracacao"]["missing_fraction"], 0.0)

    def test_datetime_and_numeric_shapes_are_detected(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _make_zip(Path(tmp))
            columns = {c["column"]: c for c in profile_file(path)[0]["columns"]}
            self.assertTrue(columns["Data Chegada"]["looks_datetime"])
            self.assertTrue(columns["IDAtracacao"]["looks_numeric"])


class TestSemanticGate(unittest.TestCase):
    """No waiting time, and no queue, until a human confirms what the timestamps mean."""

    def test_semantics_are_not_confirmed(self) -> None:
        self.assertTrue(semantics_confirmed({}))

    def test_derivation_is_blocked(self) -> None:
        with self.assertRaises(SemanticsNotConfirmed) as ctx:
            require_semantics({})
        message = str(ctx.exception)
        self.assertIn("not a queue measurement until the publisher says what they mean", message)

    def test_partial_confirmation_still_blocks(self) -> None:
        partial = {"arrival_column": "Data Chegada", "berthing_column": "Data Atracacao"}
        missing = semantics_confirmed(partial)
        self.assertIn("arrival_meaning", missing)
        self.assertIn("source_of_truth", missing)
        with self.assertRaises(SemanticsNotConfirmed):
            require_semantics(partial)

    def test_full_confirmation_opens_the_gate(self) -> None:
        complete = {key: "x" for key in REQUIRED_SEMANTIC_CONFIRMATIONS}
        complete["confirmed_by"] = "a human, citing the ANTAQ data dictionary"
        self.assertEqual(semantics_confirmed(complete), [])
        require_semantics(complete)  # must not raise

    def test_gate_requires_a_cited_source(self) -> None:
        without_source = {key: "x" for key in REQUIRED_SEMANTIC_CONFIRMATIONS}
        without_source["source_of_truth"] = ""
        without_source["confirmed_by"] = "someone"
        self.assertIn("source_of_truth", semantics_confirmed(without_source))


class TestDetectionProtocolPreRegistered(unittest.TestCase):
    def test_protocol_exists_and_predeclares_thresholds(self) -> None:
        text = (REPLAYS / "ANTAQ_EVENT_DETECTION_PROTOCOL.md").read_text(encoding="utf-8")
        for expected in ("robust_z", "3.0", "0.6", "52-week", "median and MAD"):
            self.assertIn(expected, text)

    def test_protocol_was_written_before_any_data(self) -> None:
        text = (REPLAYS / "ANTAQ_EVENT_DETECTION_PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn("before any ANTAQ file existed", text)
        self.assertIn("Detection has **not** been run", text)

    def test_protocol_forbids_using_h1_output(self) -> None:
        text = (REPLAYS / "ANTAQ_EVENT_DETECTION_PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn("H1 output is not consulted", text)
        self.assertIn("Known event dates are not used", text)

    def test_ranking_contains_no_model_performance_dimension(self) -> None:
        text = (REPLAYS / "ANTAQ_EVENT_DETECTION_PROTOCOL.md").read_text(encoding="utf-8").lower()
        for banned in ("h1 fit", "baseline fit", "expected h1 improvement"):
            self.assertNotIn(banned, text)

    def test_historical_labelling_comes_after_detection(self) -> None:
        text = (REPLAYS / "ANTAQ_EVENT_DETECTION_PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn("Only afterwards: historical identification", text)
        self.assertIn("as dates produced by the data", text)

    def test_arrival_side_events_cannot_become_capacity_shocks(self) -> None:
        text = (REPLAYS / "ANTAQ_EVENT_DETECTION_PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn("encoding an arrival surge as capacity loss is fabrication", text)

    def test_throughput_drop_alone_is_not_capacity_loss(self) -> None:
        text = (REPLAYS / "ANTAQ_EVENT_DETECTION_PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn("Throughput is endogenous", text)

    def test_queue_and_waiting_time_are_kept_distinct(self) -> None:
        text = (REPLAYS / "ANTAQ_EVENT_DETECTION_PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn("different observables and are never conflated", text)

    def test_stock_series_is_not_summed_when_aggregated(self) -> None:
        text = (REPLAYS / "ANTAQ_EVENT_DETECTION_PROTOCOL.md").read_text(encoding="utf-8")
        self.assertIn("a stock cannot be summed", text)


class TestIngestIsIndependentOfTheSimulator(unittest.TestCase):
    def test_ingest_does_not_import_the_engine(self) -> None:
        """Detection must not be able to see model output, even accidentally."""
        import ast

        for path in sorted((_PROJECT_ROOT / "event_sim" / "ingest").rglob("*.py")):
            with self.subTest(module=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                names = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        names.update(a.name for a in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names.add(node.module)
                for banned in ("event_sim.engine", "event_sim.sweep", "event_sim.historical",
                               "event_sim.h1_report", "event_sim.cross_event"):
                    self.assertNotIn(banned, names)


class TestNothingAdvancedWithoutData(unittest.TestCase):
    def test_h1_lifecycle_unchanged(self) -> None:
        h1 = next(h for h in STRUCTURAL_HYPOTHESES if h["id"] == "H1")
        self.assertEqual(h1["status"], "experimental_no_effect")

    def test_previous_verdict_preserved(self) -> None:
        h1 = next(h for h in STRUCTURAL_HYPOTHESES if h["id"] == "H1")
        self.assertIn("criterion 1", h1["evidence"])

    def test_no_heldout_protocol_or_results_exist(self) -> None:
        self.assertFalse((REPLAYS / "H1_HELDOUT_PROTOCOL.md").exists())
        self.assertFalse((REPLAYS / "H1_HELDOUT_RESULTS.md").exists())

    def test_freeze_still_verifies(self) -> None:
        from event_sim.freeze import module_hash

        self.assertEqual(
            module_hash("port_disruption"),
            "d4670fb108c2e9a3c45d33455a652578e7a72bfce69f88ed44c6b355ead13f5b",
        )
        self.assertEqual(
            module_hash("port_disruption_h1_queue_experimental"),
            "324a8bf1d67d56ad082b9c7540f7d155466af50ad71359c1b4836ef79f8f3889",
        )

    def test_eligibility_contract_unchanged(self) -> None:
        text = (REPLAYS / "EVENT3_ELIGIBILITY_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("Minimum total to qualify: 11 of 18", text)
        self.assertIn("before any candidate was searched", text.lower())

    def test_ops_product_unaffected(self) -> None:
        from adapters.ops_scenario_builder import build_scenario, get_decision_template
        from schemas.ops_schema import normalize_ops_profile
        from schemas.scenario_schema import validate_scenario

        profile = normalize_ops_profile({
            "business_unit_type": "distribution", "inventory_on_hand": 8200,
            "weekly_demand": 1100, "fill_rate": 0.89, "lead_time_days": 16,
        })
        self.assertEqual(
            validate_scenario(build_scenario(profile, get_decision_template("increase_safety_stock"))),
            [],
        )


if __name__ == "__main__":
    unittest.main()


class TestManifestLeakRegression(unittest.TestCase):
    """
    Regression for a real incident: a unit test called register(raw_dir=<tempdir>) and the
    manifest was written to the REPOSITORY's metadata directory — fake provenance claiming
    a synthetic 398-byte zip, retrieved_by "tester", in a temp directory that no longer
    existed. Fabricated provenance is worse than no provenance.
    """

    def test_registering_a_foreign_raw_dir_does_not_touch_repo_metadata(self) -> None:
        from event_sim.ingest.antaq import MANIFEST_PATH

        self.assertFalse(MANIFEST_PATH.exists(), "precondition: repo manifest absent")
        with TemporaryDirectory() as tmp:
            raw = Path(tmp)
            _make_zip(raw)
            manifest = register(raw_dir=raw)
            self.assertFalse(MANIFEST_PATH.exists(),
                             "registering a temp dir must never write repo provenance")
            self.assertTrue((raw / "manifest.json").is_file(),
                            "the manifest belongs next to the files it describes")
            self.assertIn("raw_dir", manifest)

    def test_status_flags_a_manifest_whose_files_are_gone(self) -> None:
        from event_sim.ingest import antaq as mod

        with TemporaryDirectory() as tmp:
            fake_manifest = Path(tmp) / "manifest.json"
            fake_manifest.write_text(json.dumps({
                "artifacts": [{"path": str(Path(tmp) / "ghost.zip"),
                               "filename": "ghost.zip", "sha256": "0" * 64}],
            }), encoding="utf-8")
            original = mod.MANIFEST_PATH
            try:
                mod.MANIFEST_PATH = fake_manifest
                self.assertTrue(mod.status()["stale_manifest"],
                                "a manifest referencing missing files is fabricated provenance")
            finally:
                mod.MANIFEST_PATH = original

    def test_repo_metadata_holds_no_manifest_while_raw_is_empty(self) -> None:
        from event_sim.ingest.antaq import MANIFEST_PATH, discover_raw

        if not discover_raw():
            self.assertFalse(MANIFEST_PATH.exists(),
                             "no raw data may coexist with a provenance manifest")


class TestAcquisitionBlockerEvidence(unittest.TestCase):
    """
    The self-acquisition round must prove its negative: every legitimate route named, each
    with its distinct failure, and no data or audit fabricated on the way.
    """

    def test_blocker_report_exists_with_the_full_route_table(self) -> None:
        text = (REPLAYS / "ANTAQ_ACQUISITION_BLOCKER.md").read_text(encoding="utf-8")
        for expected in ("NXDOMAIN", "Erro na conexão", "ClaudeBot", "401",
                         "estatistico.zip", "MetadadosMovimentacao.zip", "ODbL"):
            self.assertIn(expected, text)

    def test_blocker_distinguishes_dead_host_from_policy_block(self) -> None:
        text = (REPLAYS / "ANTAQ_ACQUISITION_BLOCKER.md").read_text(encoding="utf-8")
        self.assertIn("no longer exists in DNS", text)
        self.assertIn("disallows this agent by name", text)

    def test_blocker_records_what_was_not_done(self) -> None:
        text = (REPLAYS / "ANTAQ_ACQUISITION_BLOCKER.md").read_text(encoding="utf-8")
        self.assertIn("No User-Agent spoofing", text)
        self.assertIn("changing the tool does not change who is asking", text)

    def test_still_no_data_and_no_fabricated_audit(self) -> None:
        self.assertEqual(discover_raw(), [])
        self.assertFalse((REPLAYS / "ANTAQ_DATA_AUDIT.md").exists())
        self.assertFalse((REPLAYS / "ANTAQ_SEMANTICS_BINDING.md").exists())
        from event_sim.ingest.antaq import MANIFEST_PATH
        self.assertFalse(MANIFEST_PATH.exists())

    def test_catalog_source_registered_with_dead_endpoint_warning(self) -> None:
        from event_sim.evidence import get_source
        source = get_source("dadosgov_antaq_ea")
        self.assertTrue(source.redistributable)
        self.assertIn("ODbL", source.license)
        self.assertIn("NXDOMAIN", source.notes)
        self.assertIn("No data was obtained from this source", source.notes)
