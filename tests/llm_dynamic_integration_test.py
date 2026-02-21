"""
Tests for LLM-first simulation stack: llm_service, WorldState, validation guard, integration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.world_model_agent import WorldModelAgent, _validate_delta
from core.llm_service import call_llm, clear_cache, make_cache_key
from core.world_state import WorldState, DeltaValidationError, load_policy_from_config
from schemas.proposal_schema import Proposal


# --- Unit: llm_service ---
def test_llm_service_schema_validation() -> None:
    """Schema validation rejects missing required keys."""
    from core.llm_service import _validate_schema
    schema = {"required": ["x"], "types": {"x": "dict"}}
    assert _validate_schema({"x": {}}, schema)[0] is True
    assert _validate_schema({}, schema)[0] is False
    assert _validate_schema({"x": "not_dict"}, schema)[0] is False


def test_llm_service_cache_key() -> None:
    """make_cache_key produces deterministic hash."""
    k1 = make_cache_key("increase_growth", "abc123")
    k2 = make_cache_key("increase_growth", "abc123")
    assert k1 == k2
    k3 = make_cache_key("decrease_growth", "abc123")
    assert k1 != k3


def test_llm_service_clear_cache() -> None:
    """clear_cache clears the cache."""
    clear_cache()
    # No exception
    clear_cache()


# --- Unit: WorldState ---
def test_world_state_clone() -> None:
    """WorldState.clone() returns independent copy."""
    ws = WorldState(variables={"a": 10.0, "b": 20.0})
    clone = ws.clone()
    clone.variables["a"] = 99.0
    assert ws.get_variable("a") == 10.0
    assert clone.get_variable("a") == 99.0


def test_world_state_apply_delta() -> None:
    """WorldState.apply_delta applies numeric_updates."""
    ws = WorldState(variables={"cash": 100.0, "growth": 5.0})
    delta = {
        "numeric_updates": {"cash": -10.0, "growth": 2.0},
        "rationale": "test",
    }
    ws.apply_delta(delta, enforce_policy=False)
    assert ws.get_variable("cash") == 90.0
    assert ws.get_variable("growth") == 7.0


def test_world_state_policy_violation_raises() -> None:
    """Delta violating policy raises DeltaValidationError."""
    ws = WorldState(variables={"population": 10.0}, policy={"protected_keys": ["population"]})
    delta = {"numeric_updates": {"population": -20.0}, "rationale": "bad"}
    with pytest.raises(DeltaValidationError):
        ws.apply_delta(delta, enforce_policy=True)


def test_world_state_from_snapshot() -> None:
    """WorldState.from_snapshot builds from dict."""
    snap = {"global_state": {"x": 1.0}, "entities": {}, "relations": []}
    ws = WorldState.from_snapshot(snap)
    assert ws.get_variable("x") == 1.0


def test_load_policy_from_config() -> None:
    """load_policy_from_config returns dict with expected keys."""
    policy = load_policy_from_config()
    assert "protected_keys" in policy
    assert "max_magnitude" in policy


# --- Unit: WorldModelAgent _validate_delta ---
def test_validate_delta_requires_tradeoff() -> None:
    """_validate_delta rejects single-key numeric_updates without mitigation."""
    delta = {"numeric_updates": {"cash": -10}, "rationale": "x", "mitigation": None}
    snap = {"global_state": {"cash": 100}}
    assert _validate_delta(delta, snap) is False


def test_validate_delta_accepts_two_keys() -> None:
    """_validate_delta accepts >=2 numeric keys."""
    delta = {"numeric_updates": {"cash": -10, "growth": 5}, "rationale": "x"}
    snap = {"global_state": {"cash": 100, "growth": 10}}
    assert _validate_delta(delta, snap) is True


def test_validate_delta_accepts_mitigation() -> None:
    """_validate_delta accepts single key when mitigation set."""
    delta = {"numeric_updates": {"cash": -10}, "rationale": "x", "mitigation": "infeasible"}
    snap = {"global_state": {"cash": 100}}
    assert _validate_delta(delta, snap) is True


def test_validate_delta_rejects_negative_protected() -> None:
    """_validate_delta rejects negative population (10 + -20 = -10)."""
    delta = {"numeric_updates": {"population": -20, "cash": 10}, "rationale": "x"}
    snap = {"global_state": {"population": 10, "cash": 100}}
    assert _validate_delta(delta, snap) is False


# --- Integration: dry-run E2E ---
def test_dry_run_full_turn() -> None:
    """Dry-run: scenario -> agents -> one turn -> snapshot consistency."""
    scenario_path = _PROJECT_ROOT / "config" / "scenarios" / "demo_scenario.json"
    from simulation.loop import SimulationLoop
    loop = SimulationLoop(
        scenario_path=str(scenario_path),
        dry_run=True,
        enable_environment_agent=True,
    )
    result = loop.run(steps=1, silent=True)
    assert result is not None
    variables = result.get("variables") or result.get("global_state") or {}
    assert isinstance(variables, dict)
    assert len(loop._provenance) == 1


def test_world_model_agent_returns_none_on_invalid() -> None:
    """WorldModelAgent.normalize_proposal returns None when LLM returns invalid."""
    def bad_client(*args: object, **kwargs: object) -> dict:
        return {"numeric_updates": {"x": 1}, "rationale": "single key"}  # invalid: no tradeoff
    wma = WorldModelAgent(bad_client)
    p = Proposal(agent_name="a", action_type="test", parameters={}, rationale="", confidence=0.7)
    snap = {"global_state": {"x": 10}}
    result = wma.normalize_proposal(p, snap)
    assert result is None


def test_get_agents_fully_qualified_used() -> None:
    """When initial_agents fully qualified, use them (no LLM)."""
    from agents.agents import get_agents_from_scenario, _are_agents_fully_qualified
    scenario = {
        "initial_agents": [
            {"name": "founder", "role": "Founder", "objectives": {"growth": 0.6}},
            {"name": "investor", "role": "Investor", "objectives": {"runway": 0.5}},
        ],
        "initial_state": {"cash": 100, "growth": 10},
        "allowed_actions": ["increase_growth", "decrease_growth"],
    }
    assert _are_agents_fully_qualified(scenario["initial_agents"]) is True
    noop_llm = lambda *a, **kw: {}
    agents = get_agents_from_scenario(scenario, noop_llm, dry_run=True)
    assert len(agents) == 2
    assert agents[0].name == "founder"


def test_get_agents_actor_generic_triggers_llm_path() -> None:
    """When initial_agents has actor_1, triggers LLM or fallback path."""
    from agents.agents import _are_agents_fully_qualified
    assert _are_agents_fully_qualified([{"name": "actor_1", "role": "A"}] ) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
