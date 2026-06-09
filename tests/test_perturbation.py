"""Tests for scenario perturbation (robustness engine)."""

from __future__ import annotations

import random

from simulation.perturbation import perturb_scenario, DEFAULT_PERTURB_CONFIG


def _sample_scenario() -> dict:
    return {
        "causal_links": [
            {"from": "price", "to": "churn", "strength": 0.4},
            {"from": "churn", "to": "customers", "weight": -0.7},
        ],
        "initial_agents": [{"name": "founder", "objectives": {"growth": 0.6, "cash": 0.4}}],
        "initial_state": {"price": 100, "churn": 10, "customers": 200},
    }


def test_perturb_does_not_mutate_original() -> None:
    sc = _sample_scenario()
    rng = random.Random(1)
    perturb_scenario(sc, rng, {"causal_jitter": 0.4})
    assert sc["causal_links"][0]["strength"] == 0.4
    assert sc["initial_state"]["price"] == 100


def test_perturb_records_all_dimensions() -> None:
    rng = random.Random(7)
    _, rec = perturb_scenario(_sample_scenario(), rng,
                              {"causal_jitter": 0.4, "objective_jitter": 0.3, "state_jitter": 0.15})
    assert "causal:price->churn" in rec
    assert "causal:churn->customers" in rec
    assert "obj:founder:growth" in rec
    assert "state:price" in rec


def test_objectives_renormalized_to_original_total() -> None:
    rng = random.Random(3)
    p, _ = perturb_scenario(_sample_scenario(), rng, {"objective_jitter": 0.3})
    total = sum(p["initial_agents"][0]["objectives"].values())
    assert abs(total - 1.0) < 1e-6


def test_reproducible_with_same_seed() -> None:
    sc = _sample_scenario()
    cfg = {"causal_jitter": 0.4, "objective_jitter": 0.3, "state_jitter": 0.15}
    _, r1 = perturb_scenario(sc, random.Random(42), cfg)
    _, r2 = perturb_scenario(sc, random.Random(42), cfg)
    assert r1 == r2


def test_zero_jitter_is_identity() -> None:
    rng = random.Random(5)
    p, rec = perturb_scenario(_sample_scenario(), rng,
                              {"causal_jitter": 0.0, "objective_jitter": 0.0, "state_jitter": 0.0})
    assert p["causal_links"][0]["strength"] == 0.4
    assert all(abs(m - 1.0) < 1e-9 for m in rec.values())
