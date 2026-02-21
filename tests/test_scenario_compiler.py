"""Tests for core.scenario_compiler (multi-stage compiler and build_agent_prompt)."""

from __future__ import annotations

from core.scenario_compiler import (
    ScenarioCompilationError,
    build_agent_prompt,
    compile_scenario,
)


def test_build_agent_prompt() -> None:
    actor = {"name": "faction_a", "role": "Faction A"}
    profile = {
        "objectives": {"increase_tensions": 0.6, "decrease_resources": 0.3},
        "risk_tolerance": 0.5,
        "aggressiveness": 0.4,
    }
    world_model = {
        "variables": {"tensions": 50, "resources": 80},
        "causal_links": [{"from": "tensions", "to": "resources", "polarity": "negative"}],
    }
    actions = ["increase_tensions", "decrease_tensions", "increase_resources", "decrease_resources"]
    p = build_agent_prompt(actor, profile, world_model, actions)
    assert "Faction A" in p
    assert "increase_tensions" in p
    assert "0.5" in p
    assert "### ACTION_JSON" in p
    assert "deltas" in p
    assert "action" in p and "actor" in p


def test_compile_scenario_mock() -> None:
    stage1 = [
        {"name": "faction_a", "role": "Faction A", "power_level": 0.8},
        {"name": "faction_b", "role": "Faction B", "power_level": 0.6},
    ]
    stage2 = {
        "variables": {"tensions": 50, "resources": 70},
        "causal_links": [{"from": "tensions", "to": "resources", "polarity": "negative"}],
    }
    stage3 = {
        "faction_a": {
            "objectives": {"increase_tensions": 0.6, "decrease_resources": 0.3},
            "risk_tolerance": 0.5,
            "aggressiveness": 0.6,
        },
        "faction_b": {
            "objectives": {"decrease_tensions": 0.6, "increase_resources": 0.4},
            "risk_tolerance": 0.4,
            "aggressiveness": 0.3,
        },
    }
    stage4 = ["increase_tensions", "decrease_tensions", "increase_resources", "decrease_resources"]
    outputs = [stage1, stage2, stage3, stage4]
    call_idx = [0]

    def mock_llm(prompt: str, system: str | None = None, *, as_json: bool = False):  # noqa: ARG001
        if call_idx[0] < len(outputs):
            out = outputs[call_idx[0]]
            call_idx[0] += 1
            return out
        return {}

    config = {"debug_llm": False}
    scenario = compile_scenario("Two factions compete for resources.", mock_llm, config)
    assert "description" in scenario
    assert "initial_agents" in scenario
    assert "initial_state" in scenario
    assert "allowed_actions" in scenario
    assert "causal_links" in scenario
    assert "relations" in scenario
    assert len(scenario["initial_agents"]) == 2
    assert scenario["initial_agents"][0].get("system_prompt_override")
    assert scenario["initial_state"] == {"tensions": 50, "resources": 70}
