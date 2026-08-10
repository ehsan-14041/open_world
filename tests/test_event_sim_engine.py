"""
Event Simulator engine semantics.

These tests exist to catch *simulation* bugs, not rendering bugs: a chart that looks right
while the lag is dropped or the event never fires is a failure, so each test asserts on
the numbers the engine actually produced.

Covers: deterministic reproducibility, event injection, delayed effects, causal
propagation, provenance preservation, evidence-status propagation.
"""

from __future__ import annotations

import unittest

from event_sim import causal_trace
from event_sim.engine import Intervention, SimulationConfig, build_simulation
from event_sim.evidence import EvidenceValidationError, evidence_coverage, validate_module
from event_sim.registry import get_module
from event_sim.schemas import CausalEdgeEvidence, EffectRange, EventDefinition, Lag, WorldModule
from event_sim.scenarios.port_disruption import (
    OUTCOME_VARIABLE,
    build_baseline,
    build_event,
    build_world_slice,
)


class TestDeterministicReproducibility(unittest.TestCase):
    """Same slice + same config + same seed must give an identical trajectory."""

    def test_two_identical_runs_produce_identical_trajectories(self) -> None:
        a = build_baseline(turns=12, seed=7).run()
        b = build_baseline(turns=12, seed=7).run()
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        self.assertEqual(a["final_state"], b["final_state"])
        self.assertEqual(
            [rec["state"] for rec in a["trajectory"]],
            [rec["state"] for rec in b["trajectory"]],
        )

    def test_engine_draws_no_randomness(self) -> None:
        """Reseeding the global RNG between runs must not change anything."""
        import random

        random.seed(1)
        a = build_baseline(turns=8).run()
        random.seed(999)
        b = build_baseline(turns=8).run()
        self.assertEqual(a["final_state"], b["final_state"])

    def test_different_assumptions_produce_different_worlds(self) -> None:
        """Determinism must not be achieved by ignoring the configuration."""
        slice_ = build_world_slice()
        slow = build_simulation(
            slice_,
            config=SimulationConfig(turns=14, axis_settings={"recovery_rate": "slow"}),
            events=[build_event()],
        ).run()
        fast = build_simulation(
            slice_,
            config=SimulationConfig(turns=14, axis_settings={"recovery_rate": "fast"}),
            events=[build_event()],
        ).run()
        self.assertNotEqual(slow["final_state"], fast["final_state"])
        self.assertGreater(
            fast["final_state"]["port_capacity"], slow["final_state"]["port_capacity"]
        )


class TestEventInjection(unittest.TestCase):
    """The injected event must actually displace the world, for exactly its duration."""

    def test_event_displaces_target_and_releases_after_duration(self) -> None:
        sim = build_baseline(turns=14, capacity_loss=-70.0, duration=6)
        sim.run()
        series = sim.series("port_capacity")
        self.assertAlmostEqual(series[0], 100.0)          # baseline before the event
        for turn in range(1, 7):                           # held for six weeks
            self.assertAlmostEqual(series[turn], 30.0, places=6)
        self.assertGreater(series[7], series[6])           # released, recovering
        self.assertLess(series[7], 100.0)                  # but not instantly

    def test_no_event_means_no_movement(self) -> None:
        """A world with no injected event must sit exactly at baseline forever."""
        slice_ = build_world_slice()
        sim = build_simulation(slice_, config=SimulationConfig(turns=10), events=[])
        sim.run()
        for record in sim.trajectory:
            self.assertEqual(record["state"], slice_.baseline_state())

    def test_event_compiles_to_shared_engine_event_shape(self) -> None:
        """Injected events must be readable by the existing core.event_queue trace tooling."""
        events = build_event(capacity_loss=-70.0, duration=6).to_engine_events()
        self.assertEqual(len(events), 6)
        first = events[0]
        self.assertEqual(first["trigger_turn"], 1)
        self.assertEqual(first["event_type"], "event_sim_injection")
        self.assertIn("effects", first["params"])
        self.assertEqual(first["params"]["effects"][0]["key"], "port_capacity")

    def test_pulse_and_ramp_shapes_differ_from_step(self) -> None:
        step = build_baseline(turns=8, duration=4).run()["final_state"]
        slice_ = build_world_slice()
        pulse_event = EventDefinition(
            id="pulse", targets={"port_capacity": -70.0}, start_turn=1, duration=4, shape="pulse"
        )
        pulse = build_simulation(
            slice_, config=SimulationConfig(turns=8), events=[pulse_event]
        ).run()["final_state"]
        self.assertNotEqual(step["service_level"], pulse["service_level"])
        self.assertGreater(pulse["service_level"], step["service_level"])


class TestDelayedEffects(unittest.TestCase):
    """A lag of N turns must mean the target cannot move for N turns."""

    def test_two_hop_chain_arrives_late(self) -> None:
        sim = build_baseline(turns=12)
        sim.run()
        capacity = sim.series("port_capacity")
        delay = sim.series("shipping_delay")
        inventory = sim.series("inventory_availability")

        self.assertLess(capacity[1], 100.0)               # week 1: the shock lands
        self.assertAlmostEqual(delay[1], 4.0, places=6)   # delay cannot react in the same week
        self.assertGreater(delay[2], 4.0)                 # week 2: it does

        # inventory is two lagged hops downstream and must move strictly later than delay
        first_delay_move = next(t for t, v in enumerate(delay) if abs(v - 4.0) > 1e-6)
        first_inv_move = next(t for t, v in enumerate(inventory) if abs(v - 100.0) > 1e-6)
        self.assertGreater(first_inv_move, first_delay_move)

    def test_lag_setting_shifts_arrival_time(self) -> None:
        """The 'high' lag setting must delay transmission relative to 'low'."""
        slice_ = build_world_slice()
        fast = build_simulation(
            slice_, config=SimulationConfig(turns=12, lag_setting="low"), events=[build_event()]
        )
        slow = build_simulation(
            slice_, config=SimulationConfig(turns=12, lag_setting="high"), events=[build_event()]
        )
        fast.run()
        slow.run()

        def first_move(sim, var, baseline):
            return next(t for t, v in enumerate(sim.series(var)) if abs(v - baseline) > 1e-6)

        self.assertLessEqual(
            first_move(fast, "inventory_availability", 100.0),
            first_move(slow, "inventory_availability", 100.0),
        )

    def test_effect_is_read_from_the_lagged_turn(self) -> None:
        """A contribution must cite the turn its source value was actually read from."""
        sim = build_baseline(turns=6)
        sim.run()
        prov = next(p for p in sim.provenance if p["turn"] == 5)
        contribs = prov["contributions"]["inventory_availability"]
        edge = next(c for c in contribs if c["edge"] == "shipping_delay->inventory_availability")
        self.assertEqual(edge["lag"], 1)
        self.assertEqual(edge["source_turn"], 3)  # evaluated at turn 4, lag 1 -> read turn 3
        self.assertAlmostEqual(edge["source_deviation"], sim.series("shipping_delay")[3] / 10.0 - 0.4, places=9)


class TestCausalPropagation(unittest.TestCase):
    """Effects must travel along declared edges with the declared polarity — and only there."""

    def test_polarity_is_respected_along_the_chain(self) -> None:
        sim = build_baseline(turns=14)
        sim.run()
        final = sim.state()
        self.assertLess(final["port_capacity"], 100.01)
        self.assertGreater(max(sim.series("shipping_delay")), 4.0)        # negative edge -> delay up
        self.assertGreater(max(sim.series("freight_cost")), 100.0)        # positive edge -> cost up
        self.assertLess(min(sim.series("inventory_availability")), 100.0)  # negative edge -> stock down
        self.assertLess(min(sim.series("service_level")), 0.95)           # positive edge -> service down

    def test_disconnected_variable_does_not_move(self) -> None:
        """Removing every incoming edge must freeze a variable, proving edges do the work."""
        slice_ = build_world_slice()
        slice_.edges = [e for e in slice_.edges if e.target != "freight_cost"]
        sim = build_simulation(slice_, config=SimulationConfig(turns=12), events=[build_event()])
        sim.run()
        self.assertEqual(set(sim.series("freight_cost")), {100.0})

    def test_effect_setting_changes_transmission_strength(self) -> None:
        slice_ = build_world_slice()
        weak = build_simulation(
            slice_,
            config=SimulationConfig(turns=10, axis_settings={"alternative_capacity": "high"}),
            events=[build_event()],
        )
        strong = build_simulation(
            slice_,
            config=SimulationConfig(turns=10, axis_settings={"alternative_capacity": "none"}),
            events=[build_event()],
        )
        weak.run()
        strong.run()
        self.assertLess(max(weak.series("shipping_delay")), max(strong.series("shipping_delay")))

    def test_variables_stay_within_declared_ranges(self) -> None:
        sim = build_baseline(turns=20, capacity_loss=-95.0, duration=12)
        sim.run()
        for var in sim.slice.variables:
            for value in sim.series(var.id):
                if var.minimum is not None:
                    self.assertGreaterEqual(value, var.minimum - 1e-9, f"{var.id} below min")
                if var.maximum is not None:
                    self.assertLessEqual(value, var.maximum + 1e-9, f"{var.id} above max")

    def test_system_returns_to_baseline_without_permanent_drift(self) -> None:
        """A released shock must not leave an unexplained permanent offset."""
        sim = build_baseline(turns=40)
        sim.run()
        final = sim.state()
        for var in sim.slice.variables:
            self.assertAlmostEqual(final[var.id], var.baseline, places=1, msg=f"{var.id} drifted")


class TestProvenancePreservation(unittest.TestCase):
    """Every turn must retain a usable, typed record of what moved and why."""

    def test_every_turn_has_transition_provenance(self) -> None:
        sim = build_baseline(turns=10)
        sim.run()
        self.assertEqual(len(sim.provenance), 10)
        for record in sim.provenance:
            transition = record["transition"]
            self.assertIn("effect_records", transition)
            self.assertIn("final_variable_changes", transition)
            self.assertEqual(record["config"]["axis_settings"], sim.config.axis_settings)

    def test_provenance_reconciles_with_state_changes(self) -> None:
        """final_variable_changes must equal the actual state difference for that turn."""
        sim = build_baseline(turns=8)
        sim.run()
        for turn in range(1, 9):
            before = sim.trajectory[turn - 1]["state"]
            after = sim.trajectory[turn]["state"]
            recorded = {
                c["var"]: c["delta"]
                for c in sim.provenance[turn - 1]["transition"]["final_variable_changes"]
            }
            for var, delta in recorded.items():
                self.assertAlmostEqual(after[var] - before[var], delta, places=9)

    def test_effect_records_classify_event_and_lagged_sources(self) -> None:
        sim = build_baseline(turns=8)
        sim.run()
        sources = {
            rec["source"]
            for record in sim.provenance
            for rec in record["transition"]["effect_records"]
        }
        self.assertIn("event", sources)     # the injected shock
        self.assertIn("delayed", sources)   # lagged edges
        self.assertIn("direct", sources)    # lag-0 edges

    def test_causal_trace_is_built_from_provenance_not_narration(self) -> None:
        sim = build_baseline(turns=14)
        sim.run()
        trace = causal_trace.explain(sim, OUTCOME_VARIABLE, 14)
        self.assertEqual(trace["variable"], OUTCOME_VARIABLE)
        self.assertTrue(trace["drivers"], "service_level should have recorded drivers")
        driver = trace["drivers"][0]
        self.assertIn(driver["source"], {"inventory_availability", "production_capacity"})
        # the chain must reach the injected event, through real recorded contributions
        path = causal_trace.dominant_path(sim, OUTCOME_VARIABLE, 14)
        self.assertIn("port_capacity", [step["variable"] for step in path])


class TestEvidenceStatusPropagation(unittest.TestCase):
    """Evidence status must survive from the module file to the trace and the coverage panel."""

    def test_status_reaches_the_causal_trace(self) -> None:
        sim = build_baseline(turns=12)
        sim.run()
        trace = causal_trace.explain(sim, OUTCOME_VARIABLE, 12)
        statuses = {d["evidence_status"] for d in trace["drivers"] if d.get("kind") == "causal_edge"}
        self.assertTrue(statuses)
        self.assertTrue(statuses <= {"expert_assumption"})  # what the module actually claims

    def test_status_reaches_effect_records(self) -> None:
        sim = build_baseline(turns=6)
        sim.run()
        payloads = [
            rec["params_or_delta"]
            for record in sim.provenance
            for rec in record["transition"]["effect_records"]
        ]
        self.assertTrue(all("evidence_status" in p for p in payloads))

    def test_coverage_reports_assumptions_honestly(self) -> None:
        slice_ = build_world_slice()
        coverage = slice_.coverage
        self.assertEqual(coverage["edge_count"], len(slice_.edges))
        self.assertEqual(coverage["by_group"]["observed_empirical"], 0)
        self.assertEqual(coverage["by_group"]["literature_backed"], 0)
        self.assertTrue(coverage["weakly_evidenced"])
        # Coverage must stay a count of mechanisms; it must never collapse into a
        # numeric probability that the model is correct.
        self.assertNotIn("probability", coverage)
        self.assertNotIn("confidence_score", coverage)
        self.assertIn("not a probability", coverage["disclaimer"].lower())

    def test_unsourced_strong_status_is_rejected(self) -> None:
        """An AI- or expert-authored edge cannot be labelled literature_backed with no source."""
        module = get_module("port_disruption")
        bad = WorldModule.from_dict(module.to_dict())
        bad.edges[0].status = "literature_backed"
        bad.edges[0].evidence = []
        with self.assertRaises(EvidenceValidationError):
            validate_module(bad)

    def test_ai_hypothesis_edges_are_counted_separately(self) -> None:
        edge = CausalEdgeEvidence(
            source="freight_cost",
            target="service_level",
            polarity="negative",
            effect=EffectRange(0.1, 0.2, 0.3),
            status="ai_hypothesis",
            lag=Lag(1, 1),
        )
        slice_ = build_world_slice()
        coverage = evidence_coverage(list(slice_.edges) + [edge])
        self.assertEqual(coverage["by_group"]["ai_hypothesis"], 1)
        self.assertEqual(coverage["by_status"]["ai_hypothesis"], 1)


class TestInterventionMechanics(unittest.TestCase):
    """Interventions come from the module library; nothing may invent an effect size."""

    def test_intervention_effect_comes_from_the_module(self) -> None:
        slice_ = build_world_slice()
        iv = Intervention.from_slice(slice_, "redirect_cargo", magnitude=0.3)
        self.assertEqual(iv.effects_per_unit["port_capacity"], 50.0)
        self.assertEqual(iv.offsets_at(iv.start_turn)["port_capacity"], 15.0)

    def test_unknown_intervention_is_rejected(self) -> None:
        slice_ = build_world_slice()
        with self.assertRaises(KeyError):
            Intervention.from_slice(slice_, "make_the_problem_go_away")

    def test_intervention_only_applies_inside_its_window(self) -> None:
        iv = Intervention(id="x", magnitude=1.0, start_turn=3, duration=2,
                          effects_per_unit={"port_capacity": 10.0})
        self.assertEqual(iv.offsets_at(2), {})
        self.assertEqual(iv.offsets_at(3), {"port_capacity": 10.0})
        self.assertEqual(iv.offsets_at(4), {"port_capacity": 10.0})
        self.assertEqual(iv.offsets_at(5), {})


if __name__ == "__main__":
    unittest.main()
