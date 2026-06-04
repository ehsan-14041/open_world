from __future__ import annotations

"""
Tests for delayed-event and rule coverage in TransitionProvenance.

Verifies that delayed events and rule activations are surfaced both in the
typed provenance fields and in unified effect_records with correct sources.
"""

from typing import Any
from unittest.mock import patch

from schemas.delta_schema import Delta
from simulation.loop import SimulationLoop
from world.delayed_events import DelayedEvent


def _minimal_scenario() -> dict[str, Any]:
    return {
        "description": "TransitionProvenance delayed/rule test",
        "initial_state": {"x": 0.0},
        "initial_agents": [
            {"name": "agent1", "role": "Actor", "objectives": {"x": 1.0}},
        ],
        "relations": [],
        "allowed_actions": ["increase_x"],
        "action_tradeoffs": {
            "increase_x": {"x": 1.0},
        },
        "causal_links": [],
        "governance": {"strictness_level": 1},
        # A scenario rule must be present so the loop invokes run_rules (which the
        # test patches). Its content is irrelevant because run_rules is mocked.
        "rules": [
            {"id": "r1", "condition": {"always": True}, "effect": {"type": "noop"}},
        ],
    }


def test_transition_provenance_includes_delayed_and_rule_effects() -> None:
    """
    Single dry-run step with:
    - one delayed event scheduled for this turn, and
    - one synthetic rule activation (via patched run_rules).

    Asserts that TransitionProvenance.delayed_effects/events_fired/rule_effects
    and effect_records contain the expected entries.
    """
    scenario = _minimal_scenario()

    with patch("config.settings.ENABLE_UNCERTAINTY", False), patch(
        "core.world_model.ENABLE_UNCERTAINTY", False
    ):
        loop = SimulationLoop(scenario_data=scenario, dry_run=True)

        # Inject a delayed event scheduled for turn 1.
        loop.world.delayed_events.append(
            DelayedEvent(
                trigger_turn=1,
                delta=Delta(
                    numeric_updates={"x": 1.0},
                    entity_updates={},
                    new_entities={},
                    relation_updates=[],
                    meta_proposals=[],
                    rationale="delayed-test",
                    effects_duration=None,
                    mitigation=None,
                ),
                source_action="test_action",
                probability=None,
            )
        )

        # Patch the rule engine used by the loop to return a synthetic activation.
        fake_rule_activation = {
            "id": "r1",
            "condition_key": "always_true",
            "effect_key": "noop",
            "params": {"k": 1},
        }
        with patch("simulation.loop.run_rules") as mock_run_rules:
            mock_run_rules.return_value = [fake_rule_activation]
            loop.step()

    assert loop._provenance, "expected at least one provenance entry"
    last = loop._provenance[-1]
    tp = last.get("transition_provenance")
    assert isinstance(tp, dict)

    # Delayed effects: fired delayed event should be present and tagged.
    delayed_effects = tp.get("delayed_effects") or []
    assert len(delayed_effects) >= 1
    delayed_meta = (delayed_effects[0].get("metadata") or {}) if isinstance(
        delayed_effects[0], dict
    ) else {}
    assert delayed_meta.get("source") == "delayed_event"

    # Rule effects: synthetic activation should appear.
    rule_effects = tp.get("rule_effects") or []
    assert any(
        isinstance(r, dict) and r.get("id") == "r1" for r in rule_effects
    ), "expected rule activation r1 in rule_effects"

    # Unified effect_records: expect one 'delayed' and one 'rule' entry.
    effect_records = tp.get("effect_records") or []
    sources = [er.get("source") for er in effect_records if isinstance(er, dict)]
    assert "delayed" in sources, f"expected 'delayed' source in effect_records; got {sources}"
    assert "rule" in sources, f"expected 'rule' source in effect_records; got {sources}"

