"""Tests for the 5-stage scenario pipeline and Strategic Simulation Engine."""

from __future__ import annotations

from pipeline import run_pipeline, PipelineError, ActionDiscoveryEngine
from pipeline.entity_extractor import EntityExtractor
from pipeline.variable_discovery import VariableDiscoveryEngine
from pipeline.causal_graph_builder import CausalGraphBuilder
from pipeline.incentive_modeler import IncentiveModeler
from pipeline.action_space_deriver import ActionSpaceDeriver
from pipeline.model_serializer import ModelSerializer
from scenario_parser import parse_scenario_text
from core.llm_action_guard import LLMActionGuard


def test_parse_scenario_text_no_llm() -> None:
    """parse_scenario_text with use_llm=False returns minimal scenario without placeholder names."""
    scenario = parse_scenario_text("Test scenario.", use_llm=False)
    assert "description" in scenario
    assert scenario["description"] == "Test scenario."
    assert "initial_agents" in scenario
    assert "initial_state" in scenario
    assert "allowed_actions" in scenario
    agents = scenario["initial_agents"]
    assert len(agents) >= 2
    for a in agents:
        name = a.get("name", "")
        assert "actor_1" not in name and "agent_1" not in name


def test_action_space_deriver() -> None:
    """ActionSpaceDeriver produces variable-driven and strategic actions."""
    variables = {"tension": 50, "stability": 60}
    causal_graph = [{"from": "tension", "to": "stability", "polarity": "negative", "strength": 0.5}]
    incentives = {"entity_a": {"objectives": {"increase_stability": 0.6}}}
    entities = [{"name": "entity_a", "role": "Entity A"}]
    actions = ActionSpaceDeriver.derive(variables, causal_graph, incentives, entities)
    assert "increase_tension" in actions
    assert "decrease_tension" in actions
    assert "increase_stability" in actions
    assert "decrease_stability" in actions
    assert "adjust_variable" in actions


def test_run_pipeline_mock() -> None:
    """run_pipeline with mock LLM returns valid scenario."""
    stage1_entities = [
        {"name": "coastal_faction", "role": "Coastal Faction", "power_level": 0.8},
        {"name": "federal_regulator", "role": "Federal Regulator", "power_level": 0.8},
    ]
    stage2_variables = {"variables": {"tension": 50, "stability": 60, "negotiation_progress": 30}}
    stage3_causal = {
        "causal_links": [
            {"from": "tension", "to": "stability", "polarity": "negative", "strength": 0.5},
            {"from": "negotiation_progress", "to": "tension", "polarity": "negative", "strength": 0.3},
        ],
    }
    stage4_incentives = {
        "coastal_faction": {
            "objectives": {"decrease_tension": 0.6, "increase_stability": 0.4},
            "capabilities": ["diplomatic"],
            "risk_tolerance": 0.5,
            "aggressiveness": 0.6,
        },
        "federal_regulator": {
            "objectives": {"increase_negotiation_progress": 0.6, "decrease_tension": 0.4},
            "capabilities": ["regulator"],
            "risk_tolerance": 0.4,
            "aggressiveness": 0.3,
        },
    }
    stage5_actions = {
        "actions": [
            {"name": "deescalate", "effect": {"tension": -5, "stability": 2}, "capability_tags": ["diplomatic"], "strategy_class": "diplomatic"},
            {"name": "propose_ceasefire", "effect": {"tension": -8, "negotiation_progress": 5}, "capability_tags": ["diplomatic", "regulator"], "strategy_class": "diplomatic"},
            {"name": "hold_position", "effect": {"stability": 1}, "capability_tags": ["diplomatic", "regulator"], "strategy_class": "neutral"},
        ],
    }
    outputs = [stage1_entities, stage2_variables, stage3_causal, stage4_incentives, stage5_actions]
    call_idx = [0]

    def mock_llm(prompt: str, system: str | None = None, *, as_json: bool = False):  # noqa: ARG001
        if call_idx[0] < len(outputs):
            out = outputs[call_idx[0]]
            call_idx[0] += 1
            return out
        return {}

    config = {"debug_llm": False}
    scenario = run_pipeline("Gulf standoff.", mock_llm, config)
    assert "description" in scenario
    assert "initial_agents" in scenario
    assert "initial_state" in scenario
    assert "allowed_actions" in scenario
    assert "causal_links" in scenario
    assert len(scenario["initial_agents"]) == 2
    assert scenario["initial_agents"][0]["name"] == "coastal_faction"
    assert scenario["initial_agents"][1]["name"] == "federal_regulator"
    assert "tension" in scenario["initial_state"]
    assert "stability" in scenario["initial_state"]
    assert "negotiation_progress" in scenario["initial_state"]
    assert "action_tradeoffs" in scenario
    assert "strategy_classes" in scenario
    assert "deescalate" in scenario["allowed_actions"] or "increase_tension" in scenario["allowed_actions"]


def test_action_discovery_engine_fallback() -> None:
    """ActionDiscoveryEngine falls back to ActionSpaceDeriver when LLM returns invalid format."""
    entities = [{"name": "a", "role": "A"}]
    variables = {"x": 50}
    causal_graph = []
    incentives = {"a": {"objectives": {"increase_x": 0.5}}}

    def mock_fail(_p, **_kw):
        return {"invalid": "format"}

    result = ActionDiscoveryEngine.discover("Test.", entities, variables, causal_graph, incentives, mock_fail, {})
    assert "allowed_actions" in result
    assert "increase_x" in result["allowed_actions"] or "adjust_variable" in result["allowed_actions"]


def test_llm_guard_agent_allowed_actions() -> None:
    """LLMActionGuard accepts agent_allowed_actions override for validation."""
    guard = LLMActionGuard(allowed_actions=["increase_a", "decrease_a"])
    raw = {"action": "increase_b", "actor": "agent1", "deltas": [{"variable": "b", "change": 5}]}
    result_global = guard.validate(raw)
    assert result_global.get("valid") is False
    result_agent = guard.validate(raw, agent_allowed_actions=["increase_b", "decrease_b"])
    assert "errors" not in result_agent or result_agent.get("valid") is not False
    assert "action" in result_agent
    assert result_agent["action"] == "increase_b"
