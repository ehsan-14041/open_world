"""Tests for meta-action schemas: OptionSet, SelectedAction, meta proposals, DeltaPlan, predicates."""

from __future__ import annotations

import pytest

from schemas.meta_schema import (
    ActionOption,
    OptionSet,
    SelectedAction,
    NewActionSpecProposal,
    NewVariableProposal,
    NewCausalLinkProposal,
    NewEventProposal,
    DeltaPlan,
    VariableSpecs,
    ProbabilityModel,
    evaluate_predicate,
)


def test_action_option() -> None:
    opt = ActionOption(
        agent_id="a1",
        option_id="opt_1",
        style="safe",
        action_name="increase_stability",
        parameters={},
        intent="stabilize",
        expected_tradeoff="may reduce flexibility",
        uncertainty=0.3,
    )
    assert opt.style == "safe"
    assert opt.uncertainty == 0.3


def test_option_set() -> None:
    opts = [
        ActionOption(agent_id="a1", option_id="o1", style="safe", action_name="hold", parameters={}, intent="", expected_tradeoff="slow", uncertainty=0.2),
        ActionOption(agent_id="a1", option_id="o2", style="bold", action_name="push", parameters={}, intent="", expected_tradeoff="risky", uncertainty=0.5),
        ActionOption(agent_id="a1", option_id="o3", style="creative", action_name="pivot", parameters={}, intent="", expected_tradeoff="uncertain", uncertainty=0.7),
    ]
    os = OptionSet(agent_id="a1", options=opts)
    assert len(os.options) == 3
    assert os.options[1].style == "bold"


def test_selected_action() -> None:
    sa = SelectedAction(
        agent_id="a1",
        chosen_option_id="o2",
        action_name="push",
        parameters={"magnitude": 5},
        short_reason="Best risk-adjusted score",
        uncertainty=0.5,
    )
    assert sa.action_name == "push"


def test_new_variable_proposal() -> None:
    v = NewVariableProposal(
        name="trust",
        description="Trust level",
        scale="score_0_100",
        initial_value=50.0,
        variable_specs=VariableSpecs(min=0, max=100, clip=True, rate_limit=5),
    )
    assert v.scale == "score_0_100"
    assert v.variable_specs and v.variable_specs.rate_limit == 5


def test_new_event_proposal() -> None:
    e = NewEventProposal(
        name="incident",
        description="Minor incident",
        trigger_conditions=[{"key": "tension", "op": ">", "value": 60}],
        probability_model=ProbabilityModel(base_prob=0.2),
        effects=[{"op": "increase_variable", "key": "tension", "value": 3}],
    )
    assert e.name == "incident"
    assert len(e.trigger_conditions) == 1


def test_delta_plan() -> None:
    dp = DeltaPlan(
        deltas=[
            {"op": "increase_variable", "key": "stability", "value": 5},
            {"op": "decrease_variable", "key": "tension", "value": 3},
        ],
        confidence=0.8,
        justification_short="Stabilize",
    )
    assert len(dp.deltas) == 2
    assert dp.confidence == 0.8


def test_evaluate_predicate_key() -> None:
    snap = {"variables": {"tension": 65}, "global_state": {"tension": 65}}
    assert evaluate_predicate({"key": "tension", "op": ">", "value": 60}, snap) is True
    assert evaluate_predicate({"key": "tension", "op": "<", "value": 50}, snap) is False


def test_evaluate_predicate_fact() -> None:
    snap = {"facts": {"Hotline": "Active"}}
    assert evaluate_predicate({"fact": "Hotline", "op": "==", "value": "Active"}, snap) is True
