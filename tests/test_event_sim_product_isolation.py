"""
Product-surface separation and the HTTP demo surface.

The Enterprise Operations Decision Simulator must be unaffected by the Event Simulator.
These tests assert that structurally (no imports either way, no shared routes, engine
defaults untouched) rather than only behaviourally, so a future accidental coupling fails
here instead of in production.

The Ops product's own behavioural regression lives in tests/test_ops_brief_e2e.py and
tests/test_ops_decisions.py; this file adds the isolation guarantees.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class TestOpsProductIsolation(unittest.TestCase):
    def test_ops_product_modules_do_not_import_event_sim(self) -> None:
        ops_paths = [
            _PROJECT_ROOT / "adapters" / "ops_scenario_builder.py",
            _PROJECT_ROOT / "ui" / "ops_outcomes.py",
            _PROJECT_ROOT / "ui" / "decision_brief.py",
            _PROJECT_ROOT / "schemas" / "ops_schema.py",
            _PROJECT_ROOT / "schemas" / "decision_schema.py",
            _PROJECT_ROOT / "simulation" / "loop.py",
        ]
        for path in ops_paths:
            with self.subTest(module=path.name):
                self.assertFalse(
                    any(name.startswith("event_sim") for name in _imports(path)),
                    f"{path.name} must not depend on the Event Simulator",
                )

    def test_event_sim_does_not_import_the_ops_product(self) -> None:
        forbidden = ("adapters.ops_scenario_builder", "ui.ops_outcomes", "ui.decision_brief",
                     "schemas.ops_schema", "schemas.decision_schema")
        for path in sorted((_PROJECT_ROOT / "event_sim").rglob("*.py")):
            with self.subTest(module=str(path.relative_to(_PROJECT_ROOT))):
                names = _imports(path)
                for bad in forbidden:
                    self.assertNotIn(bad, names)

    def test_event_sim_contains_no_llm_dependency(self) -> None:
        """LLMs must not be the physics: nothing in event_sim may reach a model client."""
        llm_markers = ("core.llm_client", "core.llm_service", "openai", "anthropic",
                       "core.oracle", "core.narrative_engine", "core.agent_generator")
        for path in sorted((_PROJECT_ROOT / "event_sim").rglob("*.py")):
            with self.subTest(module=str(path.relative_to(_PROJECT_ROOT))):
                names = _imports(path)
                for marker in llm_markers:
                    self.assertNotIn(marker, names, f"{path.name} must not import {marker}")

    def test_event_sim_does_not_mutate_engine_defaults(self) -> None:
        """Importing the Event Simulator must not change global engine configuration."""
        import config.settings as settings

        before = (settings.ENABLE_UNCERTAINTY, settings.RANDOM_SEED, settings.PRODUCT_MODE)
        import event_sim  # noqa: F401
        from event_sim.scenarios import port_disruption

        port_disruption.build_baseline(turns=3).run()
        after = (settings.ENABLE_UNCERTAINTY, settings.RANDOM_SEED, settings.PRODUCT_MODE)
        self.assertEqual(before, after)

    def test_ops_scenario_builder_still_produces_a_valid_scenario(self) -> None:
        """Direct regression on the Ops path, run alongside the Event Simulator."""
        from adapters.ops_scenario_builder import build_scenario, get_decision_template
        from schemas.ops_schema import normalize_ops_profile
        from schemas.scenario_schema import validate_scenario

        from event_sim.scenarios import port_disruption

        port_disruption.build_baseline(turns=4).run()  # event sim runs first

        profile = normalize_ops_profile({
            "business_unit_type": "distribution",
            "inventory_on_hand": 8200,
            "weekly_demand": 1100,
            "fill_rate": 0.89,
            "lead_time_days": 16,
        })
        template = get_decision_template("increase_safety_stock")
        scenario = build_scenario(profile, template)
        self.assertEqual(validate_scenario(scenario), [])
        self.assertIn("initial_state", scenario)
        self.assertTrue(scenario["causal_links"])


class TestEventSimHttpSurface(unittest.TestCase):
    """The demo surface: separate routes, and hidden in the buyer-facing product SKU."""

    def setUp(self) -> None:
        from flask import Flask

        from event_sim.api import register_routes

        app = Flask(__name__, template_folder=str(_PROJECT_ROOT / "templates"))
        register_routes(app)
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_demo_page_renders(self) -> None:
        resp = self.client.get("/event-sim")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        self.assertIn("executable world model", body)
        self.assertIn("not a forecast", body)

    def test_modules_and_slice_endpoints(self) -> None:
        modules = self.client.get("/api/event_sim/modules").get_json()
        self.assertTrue(modules["ok"])
        self.assertIn("port_disruption", {m["id"] for m in modules["modules"]})

        slice_ = self.client.get("/api/event_sim/slice").get_json()
        self.assertTrue(slice_["ok"])
        self.assertIn("excluded_systems", slice_["slice"])
        self.assertIn("coverage", slice_["slice"])

    def test_run_endpoint_returns_both_worlds_and_a_sweep(self) -> None:
        resp = self.client.post("/api/event_sim/run", json={"turns": 12, "include_sweep": True})
        payload = resp.get_json()
        self.assertTrue(payload["ok"])
        result = payload["result"]
        self.assertIn("world_a", result["worlds"])
        self.assertIn("world_b", result["worlds"])
        self.assertTrue(result["comparison"]["identical_at_fork"])
        self.assertEqual(result["sweep"]["world_count"], 27)
        self.assertTrue(result["causal_trace_text"])

    def test_run_endpoint_is_reproducible_across_requests(self) -> None:
        body = {"turns": 10, "include_sweep": False, "seed": 3}
        first = self.client.post("/api/event_sim/run", json=body).get_json()["result"]
        second = self.client.post("/api/event_sim/run", json=body).get_json()["result"]
        self.assertEqual(first["worlds"]["world_a"], second["worlds"]["world_a"])
        self.assertEqual(first["worlds"]["world_b"], second["worlds"]["world_b"])

    def test_trace_endpoint_rejects_unknown_variables(self) -> None:
        resp = self.client.post("/api/event_sim/trace", json={"variable": "gdp"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("available", resp.get_json())

    def test_trace_endpoint_returns_a_provenance_chain(self) -> None:
        resp = self.client.post(
            "/api/event_sim/trace", json={"variable": "service_level", "turns": 14, "turn": 14}
        )
        payload = resp.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["trace"]["drivers"])
        self.assertIn("port_capacity", [s["variable"] for s in payload["dominant_path"]])

    def test_historical_endpoint_lists_episodes_with_cutoffs(self) -> None:
        payload = self.client.get("/api/event_sim/historical").get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["episodes"], "yantian_2021 should be registered")
        for episode in payload["episodes"]:
            self.assertTrue(episode["knowledge_cutoff"])

    def test_replay_endpoint_returns_evaluation_with_declared_gaps(self) -> None:
        payload = self.client.get("/api/event_sim/replay/yantian_2021").get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["hindsight_check"]["initial_state_checked"])
        self.assertEqual(payload["evaluation"]["evaluated_variables"], ["shipping_delay"])
        self.assertIn("service_level", payload["evaluation"]["unevaluated_variables"])

    def test_unknown_replay_episode_returns_404(self) -> None:
        resp = self.client.get("/api/event_sim/replay/not_a_real_episode")
        self.assertEqual(resp.status_code, 404)

    def test_evidence_endpoint_exposes_gaps_and_weighted_coverage(self) -> None:
        payload = self.client.get("/api/event_sim/evidence").get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["sources"])
        self.assertEqual(payload["provenance_errors"], [])
        self.assertIn("weighted", payload["coverage"])
        self.assertTrue(payload["gaps"]["gaps"])
        self.assertTrue(payload["data_requirements"])

    def test_event_sim_routes_are_hidden_in_product_mode(self) -> None:
        """The enterprise SKU (OWE_PRODUCT_MODE=true) must not expose the experiment."""
        source = (_PROJECT_ROOT / "ui.py").read_text(encoding="utf-8")
        self.assertIn('"/event-sim"', source)
        self.assertIn('"/api/event_sim/"', source)
        engine_only = source.split("_ENGINE_ONLY_PATHS", 1)[1].split(")", 1)[0]
        self.assertIn("/event-sim", engine_only)

    def test_event_sim_claims_no_probabilities_anywhere(self) -> None:
        """Guard against the forbidden framing reappearing in the demo surface."""
        payload = self.client.post(
            "/api/event_sim/run", json={"turns": 10, "include_sweep": True}
        ).get_json()["result"]
        blob = repr(payload).lower()
        for banned in ("most likely future", "% probability", "probability that scenario"):
            self.assertNotIn(banned, blob)
        self.assertIn("not a prediction", repr(payload["worlds"]["world_a"]).lower())


if __name__ == "__main__":
    unittest.main()
