"""Tests for the ensemble runner (real dry-run simulation, no LLM/key).

Uses the shared `causal_scenario` factory fixture (tests/conftest.py).
"""

from __future__ import annotations

from simulation.ensemble import run_ensemble, aggregate_goal_vars
from simulation.robustness import aggregate_robustness


def test_ensemble_runs_n_members(causal_scenario) -> None:
    members = run_ensemble(causal_scenario(), runs=8, steps=3, dry_run=True, base_seed=2026)
    assert len(members) == 8
    assert all(len(m.trajectory) == 3 for m in members)
    assert all(isinstance(m.goal_score, float) for m in members)


def test_ensemble_reproducible(causal_scenario) -> None:
    sc = causal_scenario()
    a = run_ensemble(sc, runs=6, steps=3, dry_run=True, base_seed=99)
    b = run_ensemble(sc, runs=6, steps=3, dry_run=True, base_seed=99)
    assert [round(m.goal_score, 6) for m in a] == [round(m.goal_score, 6) for m in b]


def test_perturbation_produces_variance_without_llm(causal_scenario) -> None:
    """The core claim: sweeping coefficients yields divergence in pure dry-run."""
    members = run_ensemble(causal_scenario(), runs=12, steps=4, dry_run=True, base_seed=2026,
                           perturb_config={"causal_jitter": 0.5, "objective_jitter": 0.3, "state_jitter": 0.2})
    scores = {round(m.goal_score, 3) for m in members}
    assert len(scores) > 1, "perturbation must produce distinct trajectories"
    rep = aggregate_robustness(members, causal_scenario())
    assert rep["low_signal"] is False
    assert rep["quantitative_spread"]["goal_score_relative_spread"] > 0.0


def test_goal_vars_extracted(causal_scenario) -> None:
    goals = aggregate_goal_vars(causal_scenario())
    assert isinstance(goals, list)
    assert all(isinstance(t, tuple) and len(t) == 2 for t in goals)
