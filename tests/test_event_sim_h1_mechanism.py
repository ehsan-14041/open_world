"""
H1 experimental mechanism: conservation, counterfactual sanity, branching, isolation.

Every test here is SYNTHETIC — none uses a historical event. The point is to establish that
the queue mechanism is mechanically correct before it is allowed anywhere near a replay, and
that adding it did not disturb the frozen baseline or smuggle in H2.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from event_sim.engine import Intervention, SimulationConfig, build_simulation
from event_sim.evidence import validate_module
from event_sim.registry import get_module
from event_sim.schemas import EventDefinition
from event_sim.world_builder import build_slice

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE = "port_disruption"
EXPERIMENTAL = "port_disruption_h1_queue_experimental"


def _sim(*, turns=20, capacity_loss=-70.0, duration=6, axis_settings=None, interventions=None,
         module=EXPERIMENTAL, start_turn=1):
    slice_ = build_slice([module])
    events = []
    if capacity_loss:
        events.append(EventDefinition(id="shock", targets={"port_capacity": capacity_loss},
                                      start_turn=start_turn, duration=duration, shape="step"))
    sim = build_simulation(
        slice_,
        config=SimulationConfig(turns=turns, axis_settings=dict(axis_settings or {})),
        events=events, interventions=interventions or [],
    )
    sim.run()
    return sim


class TestBaselineRemainsFrozen(unittest.TestCase):
    def test_baseline_module_has_no_queue_and_original_shape(self) -> None:
        module = get_module(BASELINE)
        self.assertEqual(len(module.variables), 8)
        self.assertEqual(len(module.edges), 9)
        self.assertNotIn("vessel_queue", {v.id for v in module.variables})

    def test_baseline_has_no_stock_variables(self) -> None:
        for var in get_module(BASELINE).variables:
            with self.subTest(variable=var.id):
                self.assertEqual(var.kind, "relaxation")
                self.assertEqual(var.stock, {})

    def test_baseline_direct_capacity_to_delay_edge_still_present(self) -> None:
        edges = {e.id for e in get_module(BASELINE).edges}
        self.assertIn("port_capacity->shipping_delay", edges)

    def test_baseline_trajectory_is_unaffected_by_the_engine_change(self) -> None:
        """The stock code path must be a strict no-op for a module with no stocks."""
        sim = _sim(module=BASELINE, turns=12)
        for record in sim.trajectory:
            self.assertNotIn("stocks", record)
        self.assertAlmostEqual(sim.series("port_capacity")[1], 30.0)


class TestExperimentalModuleIsSeparate(unittest.TestCase):
    def test_both_modules_load_and_validate(self) -> None:
        for module_id in (BASELINE, EXPERIMENTAL):
            with self.subTest(module=module_id):
                self.assertEqual(validate_module(get_module(module_id), raise_on_error=False), [])

    def test_experimental_is_selectable_and_marked_experimental(self) -> None:
        raw = json.loads(
            (_PROJECT_ROOT / "world_models" / "supply_chain" / f"{EXPERIMENTAL}.json")
            .read_text(encoding="utf-8")
        )
        self.assertTrue(raw["experimental"])
        self.assertEqual(raw["derived_from"]["module"], BASELINE)
        self.assertIn("Do not use as the default model", raw["notes"])

    def test_vessel_queue_exists_only_in_the_experimental_module(self) -> None:
        self.assertNotIn("vessel_queue", {v.id for v in get_module(BASELINE).variables})
        self.assertIn("vessel_queue", {v.id for v in get_module(EXPERIMENTAL).variables})

    def test_experimental_changes_only_the_capacity_to_delay_path(self) -> None:
        """Every other edge must be identical to the baseline, coefficient for coefficient."""
        base = {e.id: e for e in get_module(BASELINE).edges}
        exp = {e.id: e for e in get_module(EXPERIMENTAL).edges}
        self.assertNotIn("port_capacity->shipping_delay", exp)
        self.assertIn("port_capacity->vessel_queue", exp)
        self.assertIn("vessel_queue->shipping_delay", exp)
        for edge_id, edge in base.items():
            if edge_id == "port_capacity->shipping_delay":
                continue
            with self.subTest(edge=edge_id):
                self.assertIn(edge_id, exp)
                self.assertEqual(exp[edge_id].effect.to_dict(), edge.effect.to_dict())
                self.assertEqual(exp[edge_id].lag.to_dict(), edge.lag.to_dict())
                self.assertEqual(exp[edge_id].polarity, edge.polarity)

    def test_experimental_variables_keep_baseline_dynamics(self) -> None:
        base = {v.id: v for v in get_module(BASELINE).variables}
        for var in get_module(EXPERIMENTAL).variables:
            if var.id == "vessel_queue":
                continue
            with self.subTest(variable=var.id):
                self.assertEqual((var.baseline, var.scale, var.response),
                                 (base[var.id].baseline, base[var.id].scale, base[var.id].response))

    def test_queue_unit_avoids_unsupported_conversion(self) -> None:
        queue = next(v for v in get_module(EXPERIMENTAL).variables if v.id == "vessel_queue")
        self.assertIn("normal-flow-weeks", queue.unit)
        self.assertNotIn("TEU", queue.unit)
        self.assertNotIn("vessels", queue.unit.replace("Vessel", ""))


class TestConservation(unittest.TestCase):
    """queue(t+1) = max(0, queue(t) + arrivals - processed), processed <= capacity."""

    def test_conservation_identity_holds_every_turn(self) -> None:
        sim = _sim(turns=25)
        for record in sim.trajectory:
            stock = (record.get("stocks") or {}).get("vessel_queue")
            if not stock:
                continue
            with self.subTest(turn=record["turn"]):
                expected = max(0.0, stock["previous_level"] + stock["arrivals"] - stock["processed"])
                self.assertAlmostEqual(stock["next_level"], expected, places=9)

    def test_queue_never_negative(self) -> None:
        for loss in (-30.0, -70.0, -100.0):
            sim = _sim(turns=30, capacity_loss=loss)
            with self.subTest(loss=loss):
                self.assertTrue(all(v >= 0.0 for v in sim.series("vessel_queue")))

    def test_processing_never_exceeds_capacity(self) -> None:
        sim = _sim(turns=25)
        for record in sim.trajectory:
            stock = (record.get("stocks") or {}).get("vessel_queue")
            if not stock:
                continue
            with self.subTest(turn=record["turn"]):
                self.assertLessEqual(stock["processed"], stock["processing_capacity"] + 1e-9)

    def test_processing_never_exceeds_what_is_available(self) -> None:
        """No spontaneous queue creation: you cannot process cargo that is not there."""
        sim = _sim(turns=25)
        for record in sim.trajectory:
            stock = (record.get("stocks") or {}).get("vessel_queue")
            if not stock:
                continue
            available = stock["previous_level"] + stock["arrivals"]
            self.assertLessEqual(stock["processed"], available + 1e-9)

    def test_queue_state_is_carried_between_turns(self) -> None:
        sim = _sim(turns=20)
        levels = sim.series("vessel_queue")
        for record in sim.trajectory[1:]:
            stock = (record.get("stocks") or {}).get("vessel_queue")
            if stock:
                self.assertAlmostEqual(stock["previous_level"], levels[record["turn"] - 1], places=9)


class TestCounterfactualSanity(unittest.TestCase):
    """Synthetic scenarios with predictable answers. No historical data."""

    def test_no_disruption_means_no_queue(self) -> None:
        sim = _sim(turns=15, capacity_loss=0.0)
        self.assertTrue(all(abs(v) < 1e-9 for v in sim.series("vessel_queue")))

    def test_brief_disruption_accumulates_then_drains(self) -> None:
        sim = _sim(turns=40, capacity_loss=-70.0, duration=3)
        queue = sim.series("vessel_queue")
        peak = max(queue)
        self.assertGreater(peak, 0.5)
        self.assertGreater(queue.index(peak), 1)          # builds over time
        self.assertLess(queue[-1], peak)                   # and drains afterwards

    def test_permanently_insufficient_capacity_grows_the_queue(self) -> None:
        sim = _sim(turns=25, capacity_loss=-50.0, duration=25)
        queue = sim.series("vessel_queue")
        self.assertGreater(queue[-1], queue[len(queue) // 2])
        self.assertEqual(queue, sorted(queue), "queue must grow monotonically while starved")

    def test_more_clearance_headroom_drains_faster(self) -> None:
        slow = _sim(turns=40, duration=4, axis_settings={"queue_clearance": "slow"})
        fast = _sim(turns=40, duration=4, axis_settings={"queue_clearance": "fast"})
        self.assertLess(fast.series("vessel_queue")[-1], slow.series("vessel_queue")[-1])

    def test_zero_arrivals_drains_an_existing_queue(self) -> None:
        slice_ = build_slice([EXPERIMENTAL])
        queue_var = slice_.variable("vessel_queue")
        queue_var.stock = dict(queue_var.stock, inflow=0.0)
        sim = build_simulation(
            slice_, config=SimulationConfig(turns=10),
            events=[EventDefinition(id="s", targets={"port_capacity": -70.0},
                                    start_turn=1, duration=1)],
        )
        sim.run()
        self.assertTrue(all(abs(v) < 1e-9 for v in sim.series("vessel_queue")))

    def test_recovery_is_not_hardcoded_but_emerges_from_residual_queue(self) -> None:
        """
        The whole point of H1: when capacity is restored the queue is still there, so delay
        stays elevated until the queue is worked off. Nothing imposes a recovery delay.
        """
        sim = _sim(turns=40, capacity_loss=-70.0, duration=6)
        capacity = sim.series("port_capacity")
        queue = sim.series("vessel_queue")
        recovered = next(t for t in range(7, len(capacity)) if capacity[t] >= 95.0)
        self.assertGreater(queue[recovered], 0.0,
                           "queue must survive the return of capacity — that is the mechanism")
        self.assertLess(queue[-1], queue[recovered], "and then drain")

    def test_no_hardcoded_recovery_constant_in_the_module(self) -> None:
        raw = (_PROJECT_ROOT / "world_models" / "supply_chain" / f"{EXPERIMENTAL}.json").read_text(encoding="utf-8")
        for banned in ("recovery_delay", "recovery_weeks", "persistence_turns"):
            self.assertNotIn(banned, raw)


class TestNoH2Smuggling(unittest.TestCase):
    """H2 is not_supported and must not appear in the experimental model."""

    def test_order_backlog_is_still_a_relaxation_variable(self) -> None:
        backlog = next(v for v in get_module(EXPERIMENTAL).variables if v.id == "order_backlog")
        self.assertEqual(backlog.kind, "relaxation")
        self.assertEqual(backlog.stock, {})

    def test_only_one_stock_variable_exists(self) -> None:
        stocks = [v.id for v in get_module(EXPERIMENTAL).variables if v.kind == "stock"]
        self.assertEqual(stocks, ["vessel_queue"])

    def test_downstream_edges_and_lags_are_untouched(self) -> None:
        base = {e.id: e for e in get_module(BASELINE).edges}
        exp = {e.id: e for e in get_module(EXPERIMENTAL).edges}
        downstream = [
            "shipping_delay->inventory_availability",
            "inventory_availability->service_level",
            "inventory_availability->production_capacity",
            "production_capacity->service_level",
            "freight_cost->consumer_price_pressure",
            "port_capacity->order_backlog",
            "order_backlog->shipping_delay",
        ]
        for edge_id in downstream:
            with self.subTest(edge=edge_id):
                self.assertEqual(exp[edge_id].lag.to_dict(), base[edge_id].lag.to_dict())
                self.assertEqual(exp[edge_id].effect.to_dict(), base[edge_id].effect.to_dict())

    def test_h2_status_unchanged(self) -> None:
        from event_sim.cross_event import STRUCTURAL_HYPOTHESES

        h2 = next(h for h in STRUCTURAL_HYPOTHESES if h["id"] == "H2")
        self.assertEqual(h2["status"], "not_supported")

    def test_semantic_debt_is_recorded_not_fixed(self) -> None:
        raw = json.loads(
            (_PROJECT_ROOT / "world_models" / "supply_chain" / f"{EXPERIMENTAL}.json")
            .read_text(encoding="utf-8")
        )
        debt = raw["semantic_debt"][0]
        self.assertEqual(debt["variable"], "order_backlog")
        self.assertEqual(debt["status"], "semantic_defect")
        self.assertIn("Do not structurally modify", debt["action"])


class TestDeterminismAndBranching(unittest.TestCase):
    def test_experimental_replay_is_deterministic(self) -> None:
        a, b = _sim(turns=20), _sim(turns=20)
        self.assertEqual(a.state(), b.state())
        self.assertEqual(a.series("vessel_queue"), b.series("vessel_queue"))

    def test_branch_preserves_queue_state_at_the_fork(self) -> None:
        parent = _sim(turns=0, capacity_loss=-70.0, duration=8)
        parent.config.turns = 30
        parent.run(turns=5)
        self.assertGreater(parent.state()["vessel_queue"], 0.0, "need a non-empty queue to fork")

        branch_a = parent.fork(5, branch_id="a")
        branch_b = parent.fork(5, branch_id="b", interventions=[
            Intervention(id="extra_capacity", magnitude=1.0, start_turn=6, duration=10,
                         effects_per_unit={"port_capacity": 40.0})
        ])
        self.assertEqual(branch_a.state()["vessel_queue"], branch_b.state()["vessel_queue"])
        self.assertEqual(branch_a.state(), branch_b.state())

        branch_a.run()
        branch_b.run()
        qa, qb = branch_a.series("vessel_queue"), branch_b.series("vessel_queue")
        self.assertEqual(qa[:6], qb[:6], "no divergence before the intervention")
        self.assertLess(qb[-1], qa[-1], "extra capacity must drain the queue faster")

    def test_intervention_moves_the_queue_mechanically(self) -> None:
        plain = _sim(turns=30, duration=6)
        helped = _sim(turns=30, duration=6, interventions=[
            Intervention(id="redirect_cargo", magnitude=0.3, start_turn=2, duration=10,
                         effects_per_unit={"port_capacity": 50.0, "freight_cost": 40.0})
        ])
        self.assertLess(max(helped.series("vessel_queue")), max(plain.series("vessel_queue")))

    def test_queue_survives_a_checkpoint_round_trip(self) -> None:
        parent = _sim(turns=0, capacity_loss=-70.0, duration=8)
        parent.config.turns = 20
        parent.run(turns=6)
        expected = parent.series("vessel_queue")
        branch = parent.fork(6, branch_id="b")
        self.assertEqual(branch.series("vessel_queue"), expected)


class TestOpsIsolationStillHolds(unittest.TestCase):
    def test_experimental_module_does_not_reach_the_ops_product(self) -> None:
        from adapters.ops_scenario_builder import build_scenario, get_decision_template
        from schemas.ops_schema import normalize_ops_profile
        from schemas.scenario_schema import validate_scenario

        _sim(turns=6)  # run the experimental model first
        profile = normalize_ops_profile({
            "business_unit_type": "distribution", "inventory_on_hand": 8200,
            "weekly_demand": 1100, "fill_rate": 0.89, "lead_time_days": 16,
        })
        scenario = build_scenario(profile, get_decision_template("increase_safety_stock"))
        self.assertEqual(validate_scenario(scenario), [])


if __name__ == "__main__":
    unittest.main()


class TestExperimentIsReproducibleAndUnretuned(unittest.TestCase):
    """
    The experiment's integrity guarantees: one shared configuration, no baseline change,
    deterministic, and the acceptance rule applied as pre-registered rather than as convenient.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "h1_cli", _PROJECT_ROOT / "scripts" / "run_h1_experiment.py"
        )
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)
        cls.baseline = cls.cli.run_arm(cls.cli.BASELINE_MODULE)
        cls.experimental = cls.cli.run_arm(cls.cli.EXPERIMENTAL_MODULE)
        cls.decision = cls.cli.apply_acceptance_rule(cls.baseline, cls.experimental)

    def test_experiment_is_deterministic(self) -> None:
        again = self.cli.run_arm(self.cli.EXPERIMENTAL_MODULE)
        self.assertEqual(again["findings"], self.experimental["findings"])
        self.assertEqual(again["bias"], self.experimental["bias"])

    def test_one_shared_configuration_across_both_events(self) -> None:
        """No event-specific parameter values are possible: both arms use the same module."""
        from event_sim.historical import build_replay_slice, load_episode

        slices = {
            episode_id: build_replay_slice(
                load_episode(episode_id), modules=[self.cli.EXPERIMENTAL_MODULE]
            )
            for episode_id in self.cli.EPISODES
        }
        yantian, baltimore = slices["yantian_2021"], slices["baltimore_2024"]
        for edge_y in yantian.edges:
            edge_b = next(e for e in baltimore.edges if e.id == edge_y.id)
            with self.subTest(edge=edge_y.id):
                self.assertEqual(edge_y.effect.to_dict(), edge_b.effect.to_dict())
                self.assertEqual(edge_y.lag.to_dict(), edge_b.lag.to_dict())
        queue_y = yantian.variable("vessel_queue")
        queue_b = baltimore.variable("vessel_queue")
        self.assertEqual(queue_y.stock, queue_b.stock)
        self.assertEqual(queue_y.scale, queue_b.scale)

    def test_new_parameters_match_the_protocol(self) -> None:
        """The values used must be the ones pre-registered, not something tuned afterwards."""
        module = get_module(EXPERIMENTAL)
        queue = next(v for v in module.variables if v.id == "vessel_queue")
        self.assertEqual(queue.stock["inflow"], 1.0)
        edge = next(e for e in module.edges if e.id == "vessel_queue->shipping_delay")
        self.assertEqual(edge.effect.to_dict(), {"low": 0.08, "central": 0.15, "high": 0.25})
        axis = next(a for a in module.axes if a.id == "queue_clearance")
        self.assertEqual(
            {k: v["surge"] for k, v in axis.mapping.items()},
            {"slow": 1.05, "central": 1.15, "fast": 1.35},
        )

    def test_protocol_was_written_and_states_its_thresholds(self) -> None:
        import re

        protocol = (_PROJECT_ROOT / "docs" / "replays" / "H1_EXPERIMENT_PROTOCOL.md").read_text(encoding="utf-8")
        flat = re.sub(r"[\s*]+", " ", protocol)  # markdown wraps lines and bolds mid-phrase
        self.assertIn("pre-registration", flat.lower())
        self.assertIn("≥ 2 turns", flat)
        self.assertIn("mechanically insensitive", flat)
        self.assertIn("Written before any replay", flat)

    def test_acceptance_rule_thresholds_match_the_protocol(self) -> None:
        self.assertEqual(self.cli.MIN_COMBINED_IMPROVEMENT_TURNS, 2)
        self.assertEqual(self.cli.MAX_TOLERATED_DEGRADATION_TURNS, 1)

    def test_verdict_is_one_of_the_declared_outcomes(self) -> None:
        self.assertIn(self.decision["verdict"],
                      {"experimental_mitigating", "experimental_no_effect", "experimental_worse"})

    def test_verdict_matches_the_criteria_it_reports(self) -> None:
        """The verdict must be derivable from the printed criteria, not asserted separately."""
        passed = all(self.decision["criteria"].values())
        self.assertEqual(passed, self.decision["verdict"] == "experimental_mitigating")

    def test_baseline_arm_reproduces_the_previously_published_numbers(self) -> None:
        """The baseline replay reports must not have drifted."""
        by_event = {f["episode"]: f["error_turns"] for f in self.baseline["findings"]}
        self.assertEqual(by_event["yantian_2021"], -9)
        self.assertEqual(by_event["baltimore_2024"], -6)

    def test_h1_status_reflects_the_experiment_outcome(self) -> None:
        from event_sim.cross_event import HYPOTHESIS_STATUS, STRUCTURAL_HYPOTHESES

        h1 = next(h for h in STRUCTURAL_HYPOTHESES if h["id"] == "H1")
        self.assertIn(h1["status"], HYPOTHESIS_STATUS)
        self.assertEqual(h1["status"], self.decision["verdict"])
        self.assertNotEqual(h1["status"], "historically_validated")

    def test_defect_stays_known_because_the_rule_was_not_met(self) -> None:
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
        self.assertNotEqual(defect["lifecycle"], "mitigated")
        self.assertEqual(defect["experimental_mechanism"]["hypothesis"], "H1")
        self.assertIn("NOT YET", defect["experimental_mechanism"]["historical_validation"])

    def test_held_out_guard_still_refuses_a_generalisation_claim(self) -> None:
        """Implementing H1 must not have weakened the guard."""
        from event_sim.cross_event import DataSplitError, declare_split

        with self.assertRaises(DataSplitError):
            declare_split(["yantian_2021"], ["baltimore_2024"])

    def test_results_report_exists_and_does_not_claim_validation(self) -> None:
        path = _PROJECT_ROOT / "docs" / "replays" / "H1_EXPERIMENT_RESULTS.md"
        self.assertTrue(path.is_file(), "run scripts/run_h1_experiment.py --write-report")
        text = path.read_text(encoding="utf-8")
        self.assertIn("Do not merge", text)
        self.assertIn("still blocked", text)
        self.assertNotIn("historically validated", text.lower().replace("historically validated`", ""))

    def test_report_states_the_negative_outcome_plainly(self) -> None:
        path = _PROJECT_ROOT / "docs" / "replays" / "H1_EXPERIMENT_RESULTS.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("experimental_no_effect", text)
        self.assertIn("bad choice of aggregator", text)
