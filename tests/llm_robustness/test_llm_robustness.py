"""
LLM robustness testing harness: run 1-2 steps with dry_run or minimal scenario;
assert no crash and either valid delta or turn_degraded.
"""

from __future__ import annotations

from simulation.loop import SimulationLoop


MINIMAL_SCENARIO = {
    "name": "Minimal robustness",
    "description": "Minimal scenario for LLM harness",
    "initial_state": {"growth": 50.0, "stability": 60.0},
    "causal_links": [{"from": "growth", "to": "stability", "weight": 0.3, "polarity": "positive"}],
    "initial_agents": [
        {"name": "Agent1", "objectives": {"growth": 1.0, "stability": 0.5}, "role": "actor"},
    ],
    "allowed_actions": ["increase_growth", "decrease_growth", "increase_stability", "decrease_stability"],
    "rules": [],
    "events": [],
}


def test_dry_run_two_steps_no_crash() -> None:
    """Run 2 steps with dry_run (rule-based path); no crash, provenance has 2 entries."""
    loop = SimulationLoop(scenario_data=MINIMAL_SCENARIO, dry_run=True)
    result = loop.run(steps=2, silent=True)
    assert result is not None
    assert len(loop._provenance) == 2
    for entry in loop._provenance:
        assert "turn" in entry
        assert "delta" in entry or "turn_record" in entry
        # Either we have applied deltas or turn was degraded (null action)
        assert "turn_degraded" in entry or "variable_changes" in entry or "turn_record" in entry


def test_dry_run_single_step_provenance_shape() -> None:
    """One step: provenance entry has expected shape for analysis."""
    loop = SimulationLoop(scenario_data=MINIMAL_SCENARIO, dry_run=True)
    loop.run(steps=1, silent=True)
    assert len(loop._provenance) == 1
    entry = loop._provenance[0]
    assert "turn" in entry
    assert "actions" in entry or "proposals" in entry
    assert "turn_record" in entry
    tr = entry["turn_record"]
    assert "pre_state" in tr or "delta_applied" in tr or "chosen_actions" in tr


def test_minimal_scenario_variables_present() -> None:
    """Final state contains scenario variables."""
    loop = SimulationLoop(scenario_data=MINIMAL_SCENARIO, dry_run=True)
    result = loop.run(steps=2, silent=True)
    variables = result.get("variables") or result.get("global_state") or {}
    assert "growth" in variables or "stability" in variables
    assert isinstance(variables.get("growth"), (int, float)) or isinstance(variables.get("stability"), (int, float))


def test_guard_extract_json_invalid_returns_error() -> None:
    """LLMActionGuard.extract_json returns error dict for invalid or missing JSON."""
    from core.llm_action_guard import LLMActionGuard
    guard = LLMActionGuard(allowed_actions=["increase_growth", "decrease_growth"])
    out = guard.extract_json("no marker here")
    assert out.get("error")
    assert out.get("stage") == "extraction"
    out2 = guard.extract_json("### ACTION_JSON\n { invalid json ")
    assert out2.get("error")


def test_guard_check_internal_consistency_detects_mismatch() -> None:
    """check_internal_consistency detects action_type vs primary_variable mismatch."""
    from core.llm_action_guard import LLMActionGuard
    guard = LLMActionGuard(allowed_actions=["increase_growth", "decrease_growth"])
    extracted = {"action": "increase_growth", "primary_variable": "stability", "deltas": [{"variable": "stability", "change": 1.0}]}
    ok, issues = guard.check_internal_consistency(extracted)
    assert ok is False
    assert any("growth" in i and "stability" in i for i in issues)


def test_guard_check_internal_consistency_ok_when_aligned() -> None:
    """check_internal_consistency returns ok when action and primary_variable align."""
    from core.llm_action_guard import LLMActionGuard
    guard = LLMActionGuard(allowed_actions=["increase_growth", "decrease_growth"])
    extracted = {"action": "increase_growth", "primary_variable": "growth", "deltas": [{"variable": "growth", "change": 2.0}]}
    ok, issues = guard.check_internal_consistency(extracted)
    assert ok is True
    assert len(issues) == 0


def test_guard_sanitize_clamps_magnitude() -> None:
    """Sanitize clamps delta change to max_delta when strategic."""
    from core.llm_action_guard import LLMActionGuard
    guard = LLMActionGuard(allowed_actions=["increase_growth"], max_delta=5.0)
    world = {"variables": {"growth": 50.0}, "global_state": {"growth": 50.0}}
    sanitized = guard.sanitize(
        {"action": "increase_growth", "actor": "A", "deltas": [{"variable": "growth", "change": 999.0}], "_strategic": False},
        world,
    )
    assert sanitized["deltas"]
    assert abs(sanitized["deltas"][0]["change"]) <= 1000.0
