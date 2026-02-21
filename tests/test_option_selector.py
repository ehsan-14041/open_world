"""Tests: rule-based option selector picks from 3 options."""

from __future__ import annotations

from schemas.meta_schema import ActionOption, OptionSet
from core.option_selector import select_option_rule_based, select_option


def test_select_option_rule_based() -> None:
    opts = [
        ActionOption(agent_id="a1", option_id="o1", style="safe", action_name="hold_position", parameters={}, intent="", expected_tradeoff="slow progress", uncertainty=0.2),
        ActionOption(agent_id="a1", option_id="o2", style="bold", action_name="propose_ceasefire", parameters={}, intent="", expected_tradeoff="may backfire", uncertainty=0.5),
        ActionOption(agent_id="a1", option_id="o3", style="creative", action_name="activate_hotline", parameters={}, intent="", expected_tradeoff="uncertain outcome", uncertainty=0.7),
    ]
    selected = select_option_rule_based(
        opts,
        "a1",
        {"decrease_tension": 0.6},
        {"variables": {"tension": 60}},
        ["hold_position"],
        instability_mode=True,
    )
    assert selected.chosen_option_id in ("o1", "o2", "o3")
    assert selected.action_name in ("hold_position", "propose_ceasefire", "activate_hotline")


def test_select_option_with_option_set() -> None:
    os = OptionSet(
        agent_id="a1",
        options=[
            ActionOption(agent_id="a1", option_id="o1", style="safe", action_name="hold", parameters={}, intent="", expected_tradeoff="x", uncertainty=0.2),
            ActionOption(agent_id="a1", option_id="o2", style="bold", action_name="push", parameters={}, intent="", expected_tradeoff="y", uncertainty=0.5),
            ActionOption(agent_id="a1", option_id="o3", style="creative", action_name="pivot", parameters={}, intent="", expected_tradeoff="z", uncertainty=0.7),
        ],
    )
    selected = select_option(os, {"increase_stability": 0.5}, {"variables": {}}, [], instability_mode=False)
    assert selected.agent_id == "a1"
    assert selected.action_name in ("hold", "push", "pivot")
