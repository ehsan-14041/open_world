"""Tests for robustness aggregation (no simulation needed — synthetic members)."""

from __future__ import annotations

from simulation.ensemble import RunResult
from simulation.robustness import aggregate_robustness, compare_scenarios, DISCLAIMER


def _members() -> list[RunResult]:
    members = []
    for i in range(20):
        churn = 10 + (i % 5) * 8          # 10,18,26,34,42 cycling
        fail = churn > 30
        members.append(RunResult(
            run_id=i,
            perturbation={"causal:price->churn": 1.0 + (i - 10) * 0.04, "state:price": 1.0},
            trajectory=[{"churn": churn}, {"churn": churn}],
            final_state={"churn": float(churn), "customers": float(200 - churn), "mrr": float(100 - (churn - 10))},
            regime_sequence=["NORMAL", "CRISIS" if fail else "NORMAL"],
            outcome_label="Crisis Escalation" if fail else "Strategic Success",
            goal_score=-1.0 if fail else 2.0,
            perturbed_initial_state={"churn": 10.0, "customers": 190.0},
        ))
    return members


_SCENARIO = {"causal_links": [{"from": "price", "to": "churn", "strength": 0.4}],
             "initial_agents": [{"name": "f", "objectives": {"mrr": 1.0}}]}


def test_report_shape_and_disclaimer() -> None:
    rep = aggregate_robustness(_members(), _SCENARIO)
    assert rep["n_runs"] == 20
    assert rep["disclaimer"] == DISCLAIMER
    assert set(rep["robustness"]) >= {"robust_count", "of", "label", "band"}
    assert "by_regime" in rep["outcome_distribution"]


def test_no_absolute_probability_emitted() -> None:
    rep = aggregate_robustness(_members(), _SCENARIO)
    # robustness must be a count "x / N", never a percentage/probability key
    assert "/" in rep["robustness"]["label"]
    assert "probability" not in str(rep).lower()
    assert "% chance" not in str(rep).lower()


def test_failure_mode_identifies_driver() -> None:
    rep = aggregate_robustness(_members(), _SCENARIO)
    assert rep["failure_modes"], "should detect at least one failure driver"
    assert rep["failure_modes"][0]["variable"] == "churn"
    assert rep["failure_modes"][0]["direction"] == "higher"


def test_low_signal_when_no_causal_graph() -> None:
    rep = aggregate_robustness(_members(), {"initial_agents": []})  # no causal_links
    assert rep["low_signal"] is True
    assert "low_signal_reason" in rep


def test_empty_members() -> None:
    rep = aggregate_robustness([], _SCENARIO)
    assert rep["n_runs"] == 0
    assert rep["low_signal"] is True


def _aligned_members(offset: float) -> list[RunResult]:
    """20 members; goal_score shifted by `offset` so options are comparable per-state."""
    ms = []
    for i in range(20):
        base = (i % 5) - 2.0  # -2..+2 cycling, same pattern per index
        score = base + offset
        ms.append(RunResult(
            run_id=i, perturbation={"causal:price->churn": 1.0 + (i - 10) * 0.03},
            trajectory=[{}], final_state={"mrr": 100.0 + score},
            regime_sequence=["NORMAL" if score > 0 else "FRAGILE"],
            outcome_label="ok" if score > 0 else "bad",
            goal_score=score, perturbed_initial_state={},
        ))
    return ms


def test_compare_scenarios_rdm_structure_and_criteria() -> None:
    # Option A uniformly better per-state (offset +1) than B (offset -1).
    cmp = compare_scenarios({"A": _aligned_members(1.0), "B": _aligned_members(-1.0)})
    assert cmp["disclaimer"] == DISCLAIMER
    assert cmp["regret_aligned"] is True
    # A dominates on every criterion when it's better in every state.
    assert cmp["criteria"]["maximin"] == "A"
    assert cmp["criteria"]["expected_value"] == "A"
    assert cmp["criteria"]["minimax_regret"] == "A"
    # Each option row exposes the three decision-criteria fields.
    for opt in cmp["options"]:
        assert "worst_case_score" in opt and "median_score" in opt and "max_regret" in opt


def _members_with_regime(regime: str, score: float, n: int = 10) -> list[RunResult]:
    return [RunResult(run_id=i, perturbation={"causal:x->y": 1.0 + i * 0.01},
                      trajectory=[{}], final_state={"v": score},
                      regime_sequence=["NORMAL", regime], outcome_label="x",
                      goal_score=score, perturbed_initial_state={}) for i in range(n)]


def test_synthesis_does_not_call_crisis_option_robust() -> None:
    # winner has the best scores but reaches CRISIS -> must be 'least-bad', not 'robust'
    cmp = compare_scenarios({
        "aggressive": _members_with_regime("CRISIS", 2.0),
        "safe": _members_with_regime("FRAGILE", 0.5),
    })
    assert cmp["criteria"]["maximin"] == "aggressive"  # best goal_score
    assert "robust choice" not in cmp["synthesis"].lower()
    assert "least-bad" in cmp["synthesis"].lower()


def test_synthesis_calls_all_normal_winner_robust() -> None:
    cmp = compare_scenarios({
        "good": _members_with_regime("NORMAL", 2.0),
        "bad": _members_with_regime("FRAGILE", 0.5),
    })
    assert cmp["criteria"]["maximin"] == "good"
    assert "robust" in cmp["synthesis"].lower()


def test_compare_scenarios_regret_skipped_when_unaligned() -> None:
    cmp = compare_scenarios({"A": _aligned_members(0.0), "B": _aligned_members(0.0)[:10]})
    assert cmp["regret_aligned"] is False
    assert "minimax_regret" not in cmp["criteria"]
    assert "regret_note" in cmp
