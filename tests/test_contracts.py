"""
Tests for canonical contracts: validation, adapters, and reduction of name-based assumptions.
"""

from __future__ import annotations

import pytest

from schemas.contracts import (
    SimulationSpec,
    State,
    ActionSpec,
    EventSpec,
    ConstraintSpec,
    TraceEntry,
    TransitionResult,
    simulation_spec_from_scenario,
    state_from_dict,
    action_spec_from_dict,
    event_spec_from_dict,
    constraint_spec_from_variable_spec,
    trace_entry_from_dict,
)
from schemas.delta_schema import Delta
from core.legacy_semantics import (
    legacy_infer_non_negative_variables,
    legacy_is_non_negative_variable,
    legacy_goal_to_var_direction,
    legacy_strategy_class_from_action_type,
    legacy_steady_action_name,
)
from core.llm_action_guard import LLMActionGuard


def test_simulation_spec_from_dict_and_adapter() -> None:
    d = {
        "description": "Test",
        "initial_state": {"a": 1},
        "allowed_actions": ["act1"],
        "variable_specs": {"a": {"min": 0, "max": 100}},
    }
    spec = SimulationSpec.from_dict(d)
    assert spec.description == "Test"
    assert spec.initial_state["a"] == 1
    assert "act1" in spec.allowed_actions
    out = spec.to_dict()
    assert out["description"] == "Test"
    spec2 = simulation_spec_from_scenario(d)
    assert spec2.variable_specs.get("a") == {"min": 0, "max": 100}


def test_state_from_dict_and_roundtrip() -> None:
    snap = {
        "variables": {"x": 10, "y": 20},
        "global_state": {"x": 10, "y": 20},
        "turn": 3,
        "version": 2,
    }
    state = State.from_dict(snap)
    assert state.variables["x"] == 10
    assert state.turn == 3
    assert state.version == 2
    out = state.to_dict()
    assert out["variables"]["x"] == 10
    assert state_from_dict(snap).turn == 3


def test_action_spec_from_dict_and_adapter() -> None:
    d = {"type": "increase_variable", "target": "cash", "magnitude": 5.0}
    spec = ActionSpec.from_dict(d)
    assert spec.type == "increase_variable"
    assert spec.target == "cash"
    assert spec.magnitude == 5.0
    assert action_spec_from_dict(d) is not None
    assert action_spec_from_dict(None) is None
    # Nested effect (legacy)
    d2 = {"type": "adjust_variable", "variable": "v", "effect": {"type": "increase_variable", "variable": "v", "value": 3}}
    spec2 = ActionSpec.from_dict(d2)
    assert spec2.variable == "v" or spec2.target == "v"


def test_event_spec_from_dict() -> None:
    d = {"event_type": "incident", "trigger_turn": 5, "params": {"effects": []}}
    spec = EventSpec.from_dict(d)
    assert spec.event_type == "incident"
    assert spec.trigger_turn == 5
    assert event_spec_from_dict(d).event_type == "incident"


def test_constraint_spec_and_adapter() -> None:
    c = ConstraintSpec(non_negative=True, min=0, max=100)
    assert c.non_negative is True
    assert c.min == 0
    leg = {"min": 0, "max": 100, "non_negative": True}
    c2 = constraint_spec_from_variable_spec(leg)
    assert c2.non_negative is True
    assert c2.min == 0
    # ValueSpec-like with scale
    leg_scale = {"scale": {"min": 10, "max": 50}, "rate_limit": 5}
    c3 = constraint_spec_from_variable_spec(leg_scale)
    assert c3.min == 10
    assert c3.max == 50
    assert c3.rate_limit == 5


def test_trace_entry_from_dict() -> None:
    d = {
        "turn": 1,
        "agent_id": "agent1",
        "action": {"action_type": "increase_x"},
        "delta_raw": {"x": 5},
        "delta_applied": {"x": 5},
    }
    e = TraceEntry.from_dict(d)
    assert e.turn == 1
    assert e.agent_id == "agent1"
    assert trace_entry_from_dict(d).delta_applied["x"] == 5


def test_transition_result_from_dict() -> None:
    d = {
        "state_before": {"variables": {"a": 1}},
        "state_after": {"variables": {"a": 2}},
        "delta_applied": {"numeric_updates": {"a": 1}},
    }
    r = TransitionResult.from_dict(d)
    assert r.state_before["variables"]["a"] == 1
    assert r.state_after["variables"]["a"] == 2


def test_legacy_semantics_synthetic_names() -> None:
    # Variables with no domain keywords should not be inferred non-negative by default
    names = ["x", "y", "z", "foo", "bar"]
    inferred = legacy_infer_non_negative_variables(names)
    assert inferred == set()
    # Only names containing keywords are inferred
    assert legacy_is_non_negative_variable("population") is True
    assert legacy_is_non_negative_variable("cash") is True
    assert legacy_is_non_negative_variable("x") is False
    assert legacy_is_non_negative_variable("resource_util") is True


def test_guard_prefers_variable_specs_non_negative() -> None:
    # When variable_specs set non_negative for a variable with no keyword in name, guard should clamp
    guard = LLMActionGuard(allowed_actions=["increase_x", "increase_y"], max_delta=100)
    world_state = {
        "variables": {"x": 10, "y": 20},
        "global_state": {"x": 10, "y": 20},
        "variable_specs": {"x": {"non_negative": True}},
    }
    json_action = {"action": "increase_x", "actor": "a", "deltas": [{"variable": "x", "change": -50}]}
    out = guard.sanitize(json_action, world_state)
    # x should be clamped to 0 (current 10 + change >= 0)
    deltas = out.get("deltas") or []
    for d in deltas:
        if d.get("variable") == "x":
            assert d["change"] == -10.0
            break
    else:
        assert False, "expected delta for x"


def test_legacy_goal_to_var_direction() -> None:
    assert legacy_goal_to_var_direction("increase_cash") == ("cash", 1)
    assert legacy_goal_to_var_direction("decrease_tension") == ("tension", -1)
    assert legacy_goal_to_var_direction("maximize_growth") == ("growth", 1)
    assert legacy_goal_to_var_direction("plain_var") == ("plain_var", 1)


def test_legacy_strategy_class_and_steady_action() -> None:
    assert legacy_strategy_class_from_action_type("launch_campaign") == "growth"
    assert legacy_strategy_class_from_action_type("steady_finance") == "conservation"
    assert legacy_strategy_class_from_action_type("unknown_act") == "default"
    assert legacy_steady_action_name() == "steady_finance"


def test_delta_roundtrip() -> None:
    d = {"numeric_updates": {"a": 1.0}, "rationale": "test", "action_type": "increase_a"}
    delta = Delta.from_dict(d)
    assert delta.numeric_updates["a"] == 1.0
    assert delta.to_dict()["action_type"] == "increase_a"
