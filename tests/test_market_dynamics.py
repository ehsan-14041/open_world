"""Tests for the Market Dynamics Library (Phase 4 — shocks & contagion)."""

from __future__ import annotations

import random

from core.market_dynamics import (
    cond_at_turn, cond_after_turn, cond_with_probability,
    supply_shock, demand_shock, probabilistic_shock, contagion_cascade,
)
from core.rule_engine import run_rules, has_condition
from schemas.scenario_schema import normalize_scenario
from simulation.loop import SimulationLoop


# ---- conditions ----

def test_at_turn_fires_only_on_that_turn() -> None:
    assert cond_at_turn({"turn": 3}, {"turn": 3}) is True
    assert cond_at_turn({"turn": 2}, {"turn": 3}) is False


def test_after_turn_is_sustained() -> None:
    assert cond_after_turn({"turn": 5}, {"turn": 3}) is True
    assert cond_after_turn({"turn": 1}, {"turn": 3}) is False


def test_with_probability_is_seed_reproducible() -> None:
    random.seed(42)
    a = [cond_with_probability({}, {"p": 0.5}) for _ in range(10)]
    random.seed(42)
    b = [cond_with_probability({}, {"p": 0.5}) for _ in range(10)]
    assert a == b
    assert cond_with_probability({}, {"p": 0.0}) is False
    assert cond_with_probability({}, {"p": 1.0}) is True


def test_primitives_registered() -> None:
    assert has_condition("at_turn") and has_condition("after_turn") and has_condition("with_probability")


# ---- builders ----

def test_supply_and_demand_shock_builders() -> None:
    s = supply_shock(3, "capacity", 0.6)
    assert s["condition_key"] == "at_turn" and s["effect_key"] == "scale_var"
    assert s["params"] == {"turn": 3, "target": "capacity", "factor": 0.6}
    d = demand_shock(2, "demand", -120)
    assert d["effect_key"] == "add_to_var" and d["params"]["amount"] == -120


def test_contagion_cascade_chains_pairs() -> None:
    rules = contagion_cascade(["a", "b", "c"], threshold=0.5, factor=0.7)
    assert len(rules) == 2
    assert rules[0]["params"]["var"] == "a" and rules[0]["params"]["target"] == "b"
    assert rules[1]["params"]["var"] == "b" and rules[1]["params"]["target"] == "c"


# ---- end-to-end through run_rules ----

def test_supply_shock_fires_at_turn_via_run_rules(make_world) -> None:
    rule = supply_shock(2, "capacity", 0.5)
    w1 = make_world({"capacity": 100.0}, turn=1)
    run_rules(w1.snapshot(), w1, [rule])
    assert w1.variables["capacity"] == 100.0  # not turn 2 yet
    w2 = make_world({"capacity": 100.0}, turn=2)
    run_rules(w2.snapshot(), w2, [rule])
    assert w2.variables["capacity"] < 90.0  # shock landed (×0.5, after physics-free apply)


def test_contagion_in_full_simulation_is_non_degenerate() -> None:
    """A contagion cascade in a real dry-run produces a genuine multi-variable drop."""
    sc = normalize_scenario({
        "description": "contagion",
        "initial_state": {"trust": 0.5, "demand": 0.5, "revenue": 0.5},
        "variable_specs": {"trust": {"min": 0, "max": 1}, "demand": {"min": 0, "max": 1}, "revenue": {"min": 0, "max": 1}},
        "initial_agents": [{"name": "op", "role": "Operator", "objectives": {"revenue": 1.0}}],
        "causal_links": [{"from": "trust", "to": "demand", "polarity": "positive", "strength": 0.5}],
        "allowed_actions": ["steady"],
        "rules": contagion_cascade(["trust", "demand", "revenue"], threshold=0.4, factor=0.5),
    })
    res = SimulationLoop(scenario_data=sc, dry_run=True).run(steps=2, return_provenance=True, silent=True, delay_between_rounds=0.0)
    # trust starts at 0.5 (> 0.4) -> cascade should fire and pull revenue down
    final = res["final"].get("variables") or res["final"].get("global_state") or {}
    assert final.get("revenue", 1.0) < 0.5
