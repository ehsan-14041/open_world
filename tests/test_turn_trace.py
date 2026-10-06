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
