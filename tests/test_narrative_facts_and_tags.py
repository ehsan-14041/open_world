from __future__ import annotations

from core.narrative_engine import generate_turn_narrative


def test_generate_turn_narrative_embeds_facts_and_tags() -> None:
    previous = {"variables": {"x": 0}}
    current = {"variables": {"x": 1}}
    delta = {"x": 1.0}
    prov_like = []
    regime = "NORMAL"
    calibration = {"calibration_score_agg": 0.5}
    agent_actions: list[dict] = []
    goals = {"agent_a": {"objectives": {"increase_x": 1.0}, "long_term_goals": []}}
    scenario = {"governance": {"stability_variable": "x"}}

    result = generate_turn_narrative(
        previous,
        current,
        delta,
        prov_like,
        regime,
        calibration,
        agent_actions,
        goals,
        scenario,
        self_effect_per_agent={"agent_a": {"x": 1.0}},
        propagation_trace=[],
        delta_applied=delta,
    )

    assert "facts" in result
    assert "tags" in result
    assert "inputs" in result
    assert isinstance(result["facts"], list)
    assert any(f.get("kind") == "delta_summary" for f in result["facts"] if isinstance(f, dict))
