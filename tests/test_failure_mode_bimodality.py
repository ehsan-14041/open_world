"""
Path A — failure-mode authenticity via the native variable_specs.max threshold.

Proves the robustness layer detects a genuine *phase transition* (a bimodal regime
distribution), not a smooth copy of the input noise, with NO change to engine code.

The fixture (shared `threshold_scenario` factory) makes churn_rate the only bounded
variable, sitting on 0.9*max = 0.45. State-jitter perturbation straddles that boundary,
so detect_regime flips some runs to FRAGILE while others stay NORMAL.

NOTE: linear propagation only moves a variable when a delta is injected into it, so a
*catastrophic* bimodal goal_score (and a strong churn pivotal) requires the non-linear
rule (Path B, core/threshold_rules.py). Path A asserts the bimodal regime split.
"""

from __future__ import annotations

import json

from simulation.ensemble import run_ensemble
from simulation.robustness import aggregate_robustness


def _run_report(make_scenario, state_jitter: float = 0.12) -> dict:
    members = run_ensemble(
        make_scenario(),
        runs=20, steps=2, dry_run=True, base_seed=42,
        perturb_config={"causal_jitter": 0.0, "objective_jitter": 0.0, "state_jitter": state_jitter},
    )
    return aggregate_robustness(members, make_scenario())


def test_regime_distribution_is_bimodal(threshold_scenario) -> None:
    """Perturbation must push some runs across the threshold and leave others below."""
    report = _run_report(threshold_scenario)
    by_regime = report["outcome_distribution"]["by_regime"]
    crossed = by_regime.get("FRAGILE", 0) + by_regime.get("CRISIS", 0)
    stayed = by_regime.get("NORMAL", 0)
    assert crossed > 0, "system never crossed the threshold — output is still flat/linear"
    assert stayed > 0, "all runs crossed — not a bimodal split"
    assert crossed + stayed == report["n_runs"]


def test_not_flagged_low_signal(threshold_scenario) -> None:
    """A real phase transition is genuine signal, not noise."""
    assert _run_report(threshold_scenario)["low_signal"] is False


def test_zero_perturbation_is_degenerate(threshold_scenario) -> None:
    """Sanity: with no perturbation, every run is identical (no fake variance)."""
    members = run_ensemble(
        threshold_scenario(),
        runs=10, steps=2, dry_run=True, base_seed=7,
        perturb_config={"causal_jitter": 0.0, "objective_jitter": 0.0, "state_jitter": 0.0},
    )
    regimes = {m.regime_sequence[-1] for m in members}
    assert len(regimes) == 1, "no perturbation must yield identical runs"


def test_no_probability_language_in_report(threshold_scenario) -> None:
    report = _run_report(threshold_scenario)
    blob = json.dumps(report).lower()
    assert "probability" not in blob
    assert "% chance" not in blob
    assert "/" in report["robustness"]["label"]


def test_path_b_threshold_cascade_is_differential(threshold_scenario) -> None:
    """
    Path B: the non-linear churn_cliff rule (in the fixture) makes runs that cross
    the threshold systematically worse than runs that stay below it. We assert the
    *differential* (cliff vs safe) rather than a clean goal_score bimodality, because
    crude dry-run agent dynamics add scale-blind noise to every run; the differential
    isolates the rule's catastrophic cascade from that baseline noise.
    """
    members = run_ensemble(
        threshold_scenario(),
        runs=24, steps=3, dry_run=True, base_seed=42,
        perturb_config={"causal_jitter": 0.0, "objective_jitter": 0.0, "state_jitter": 0.12},
    )
    above = [m.final_state.get("mrr", 0.0) for m in members
             if m.perturbed_initial_state.get("churn_rate", 0.0) > 0.45]
    below = [m.final_state.get("mrr", 0.0) for m in members
             if m.perturbed_initial_state.get("churn_rate", 0.0) <= 0.45]
    assert above and below, "perturbation must straddle the threshold"
    assert sum(above) / len(above) < sum(below) / len(below), "threshold cascade did not make crossed runs worse"
