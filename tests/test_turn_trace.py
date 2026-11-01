"""Tests for turn trace builder."""

from __future__ import annotations

from ui.turn_trace import build_turn_trace


def test_build_turn_trace_from_provenance() -> None:
    provenance = [
        {
            "turn": 1,
            "selected_action": "cut_costs",
            "primary_delta": {"burn_rate": -4000, "runway_months": 1},
            "narrative": {"turn_summary": "Burn reduced slightly."},
        },
        {
            "turn": 2,
            "selected_action": "invest_in_growth",
            "primary_delta": {"growth": 3},
            "narrative": {"turn_summary": "Growth investment applied."},
        },
    ]
    trace = build_turn_trace(provenance, {})
    assert len(trace) == 2
    assert trace[0]["turn"] == 1
    assert trace[0]["action"] == "cut_costs"
    assert trace[0]["key_changes"]


def test_build_turn_trace_reads_turn_record() -> None:
    """The simulation loop nests pre/post state under turn_record; the trace must look there."""
    provenance = [
        {
            "turn": 1,
            "actions": [{"agent_name": "ops_director", "action_type": "decision_increase_safety_stock"}],
            "turn_record": {
                "pre_state": {"variables": {"inventory_on_hand": 8200.0, "fill_rate": 0.89}},
                "post_state": {"variables": {"inventory_on_hand": 9700.0, "fill_rate": 0.91}},
                "events_fired": ["reorder_point_crossed"],
            },
        },
    ]
    trace = build_turn_trace(provenance, {})
    assert trace[0]["action"] == "decision_increase_safety_stock"
    assert {c["variable"] for c in trace[0]["key_changes"]} >= {"inventory_on_hand"}
    assert trace[0]["events"] == ["reorder_point_crossed"]
