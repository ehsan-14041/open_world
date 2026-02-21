"""Tests for narrative_synthesizer module."""

import re

import pytest

from core.narrative_synthesizer import (
    extract_structural_phases,
    detect_turning_point,
    detect_diminishing_returns,
    classify_pattern,
    infer_agent_display_names,
    interpret_beliefs_to_narrative,
    build_structured_narrative_summary,
    format_structured_summary_prose,
    transform_agents_state_with_display_names,
    _humanize_role,
)


def test_extract_structural_phases():
    trace = [
        {
            "variable_changes": [{"var": "cash", "delta": 100}, {"var": "growth", "delta": 5}],
            "causal_edges": [],
            "derived": {"dissatisfaction": 30, "instability_mode": False},
        },
        {
            "variable_changes": [{"var": "cash", "delta": -50}, {"var": "churn", "delta": -0.5}],
            "causal_edges": [],
            "derived": {"dissatisfaction": 35, "instability_mode": False},
        },
    ]
    final = {"variables": {"cash": 150, "growth": 15, "churn": 0.2}}
    phases = extract_structural_phases(trace, final)
    assert "opening_conditions" in phases
    assert "dominant_strategy_cluster" in phases
    assert "largest_delta_turn" in phases
    assert "turn_deltas" in phases


def test_detect_turning_point():
    phases = {"turn_deltas": [105, 50.5], "largest_delta_turn": 0, "first_constraint_turn": None}
    turning = detect_turning_point([{"variable_changes": [{"var": "cash", "delta": 100}]}], phases)
    assert "turn_index" in turning
    assert "reason_tag" in turning


def test_classify_pattern():
    trace = [
        {"variable_changes": [{"var": "cash", "delta": 500}, {"var": "churn", "delta": -0.5}]},
    ]
    final = {"variables": {"cash": 100000, "churn": 0.2, "growth": 10, "competition": 70}}
    phases = {"opening_conditions": {}, "repeated_action_monotony": False, "turn_deltas": [500]}
    turning = {"turn_index": 0, "dominant_variable_shift": "cash", "reason_tag": "max_delta"}
    pattern = classify_pattern(trace, final, phases, turning, diminishing_returns=False)
    assert pattern in (
        "Illusory Stabilization",
        "Defensive Lock-in",
        "Competitive Drift",
        "Governance Dominance",
        "Escalatory Volatility",
        "Strategic Stagnation",
    )


def test_infer_agent_display_names():
    agents = [
        {"name": "founder", "role": "Founder", "objectives": {}},
        {"name": "actor_1", "role": "Actor1", "objectives": {}},
    ]
    trace = []
    final = {"causal_links": [{"agent": "actor_1", "variable": "cash", "delta": 1000}]}
    names = infer_agent_display_names(agents, trace, final)
    assert names.get("founder") == "Founder"
    assert "actor_1" in names


def test_interpret_beliefs_to_narrative():
    beliefs = {"confidence": {"x": 0.46}, "variables": {"dissatisfaction": 15}}
    lines = interpret_beliefs_to_narrative(beliefs)
    assert len(lines) >= 1
    assert "moderate" in lines[0].lower() or "low" in lines[0].lower()


def test_build_structured_narrative_summary():
    trace = [
        {
            "variable_changes": [{"var": "cash", "delta": 100}],
            "causal_edges": [{"from_action": "raise_fund", "agent": "founder", "variable": "cash", "delta": 100}],
        },
    ]
    final = {"variables": {"cash": 10100}, "causal_links": []}
    agents = [{"name": "founder", "role": "Founder", "objectives": {}}]
    summary = build_structured_narrative_summary(trace, final, agents)
    assert "opening_conditions" in summary
    assert "behavioral_pattern" in summary
    assert "name_to_display" in summary


def test_format_structured_summary_prose():
    """English path: same two-paragraph structure as fa; beginning + outcome."""
    summary = {
        "opening_conditions": "The simulation opened with abundant liquidity.",
        "dominant_strategic_moves": "The dominant strategy centered on churn reduction.",
        "causal_cascade": ["founder raise_fund → cash (+1000)"],
        "turning_point_phrase": "Turn 1 marked the decisive shift.",
        "hidden_tradeoffs": "Although retention improved, competition remained elevated.",
        "behavioral_pattern": "Strategic Stagnation",
        "behavioral_pattern_phrase": "The run fits an Illusory Stabilization pattern.",
    }
    prose = format_structured_summary_prose(summary, lang="en")
    assert "at the beginning" in prose.lower()
    assert "dominant strategy" in prose.lower() or "churn" in prose.lower()
    paragraphs = [p.strip() for p in prose.split("\n\n") if p.strip()]
    assert len(paragraphs) >= 2


def test_format_structured_summary_prose_en_no_digits():
    """When lang=en and allow_numbers=False, output must not contain [0-9]."""
    summary = {
        "opening_conditions": "The simulation opened with key variables.",
        "dominant_strategic_moves": "The dominant strategy centered on act.",
        "causal_cascade": ["agent_1 act → x (+10)"],
        "turning_point_phrase": "Turn 1 marked the decisive shift.",
        "hidden_tradeoffs": "Variable movements produced effects.",
        "behavioral_pattern": "Strategic Stagnation",
        "phases": {"turn_deltas": [10.0, 2.0]},
    }
    prose = format_structured_summary_prose(summary, lang="en", allow_numbers=False)
    assert not re.search(r"[0-9]", prose), f"Output should have no digits: {prose!r}"
    assert "at the beginning" in prose.lower()


def test_format_structured_summary_prose_fa_no_digits():
    """When lang=fa and allow_numbers=False, output must not contain [0-9]."""
    summary = {
        "opening_conditions": "The simulation opened with key variables.",
        "dominant_strategic_moves": "The dominant strategy centered on reduce_churn.",
        "causal_cascade": ["agent_1 act → x (+10)"],
        "turning_point_phrase": "Turn 1 marked the decisive shift.",
        "hidden_tradeoffs": "Variable movements produced effects.",
        "behavioral_pattern": "Strategic Stagnation",
        "behavioral_pattern_phrase": "The run fits Strategic Stagnation.",
        "phases": {"turn_deltas": [10.0, 2.0]},
    }
    prose = format_structured_summary_prose(summary, lang="fa", allow_numbers=False)
    assert not re.search(r"[0-9]", prose), f"Output should have no digits: {prose!r}"


def test_format_structured_summary_prose_fa_has_dar_aghaz():
    """Persian narrative contains 'در آغاز' and at least 2 paragraphs."""
    summary = {
        "opening_conditions": "The simulation opened with key variables.",
        "dominant_strategic_moves": "The dominant strategy centered on act.",
        "causal_cascade": [],
        "turning_point_phrase": "The turning point occurred.",
        "hidden_tradeoffs": "Tradeoffs occurred.",
        "behavioral_pattern": "Strategic Stagnation",
        "behavioral_pattern_phrase": "Strategic Stagnation.",
        "phases": {},
    }
    prose = format_structured_summary_prose(summary, lang="fa", allow_numbers=False)
    assert "در آغاز" in prose
    paragraphs = [p.strip() for p in prose.split("\n\n") if p.strip()]
    assert len(paragraphs) >= 2


def test_format_structured_summary_prose_fa_has_persian_char():
    """Persian output contains at least one Persian character."""
    summary = {
        "opening_conditions": "Opened.",
        "dominant_strategic_moves": "Strategy centered on x.",
        "causal_cascade": [],
        "turning_point_phrase": "Turn 1 shift.",
        "hidden_tradeoffs": "Tradeoffs.",
        "behavioral_pattern": "Strategic Stagnation",
        "phases": {},
    }
    prose = format_structured_summary_prose(summary, lang="fa", allow_numbers=False)
    has_persian = any("\u0600" <= c <= "\u06FF" for c in prose)
    assert has_persian, f"Output should contain Persian: {prose!r}"


def test_domain_agnostic_generic_keys():
    """Narrative works with arbitrary variable keys (x, y, z) without hardcoded mappings."""
    trace = [
        {
            "variable_changes": [{"var": "x", "delta": 1}, {"var": "y", "delta": -0.5}],
            "causal_edges": [{"from_action": "inc_x", "agent": "a1", "variable": "x", "delta": 1}],
        },
    ]
    final = {"variables": {"x": 11, "y": 9.5}, "causal_links": []}
    agents = [{"name": "a1", "role": "Actor", "objectives": {}}]
    summary = build_structured_narrative_summary(trace, final, agents)
    prose = format_structured_summary_prose(summary, lang="fa", allow_numbers=False)
    assert not re.search(r"[0-9]", prose)
    assert "x" in prose or "y" in prose or "متغیر" in prose or "وضعیت" in prose


def test_transform_agents_state_with_display_names():
    agents_state = {"founder": {"beliefs": {"confidence": {"x": 0.5}}, "memory": {}}}
    name_to_display = {"founder": "Founder (Risk-Tolerant)"}
    out = transform_agents_state_with_display_names(agents_state, name_to_display)
    assert "Founder (Risk-Tolerant)" in out
    assert "founder" not in out


def test_humanize_role():
    assert _humanize_role("CommunityLeader") == "Community Leader"
    assert _humanize_role("actor_1") == "Actor 1"
