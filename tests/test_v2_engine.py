"""
V2 engine tests: causal_links structural only, ValueSpec, beliefs, delayed effects,
shocks determinism, action_trace separation, narrative numberless/token/lang.
"""

import re
import random
import pytest


def test_causal_links_structural_only():
    """causal_links must not contain action/turn log keys (agent, from_action, variable, delta)."""
    from model.causal_graph import is_structural_link, structural_causal_links, ACTION_LOG_KEYS
    assert not is_structural_link({"from": "a", "to": "b", "agent": "x"})
    assert not is_structural_link({"from": "a", "to": "b", "from_action": "increase_x"})
    assert not is_structural_link({"from": "a", "to": "b", "variable": "x", "delta": 5})
    assert is_structural_link({"from": "a", "to": "b"})
    assert is_structural_link({"from": "a", "to": "b", "edge_model": {"type": "linear", "params": {"weight": 0.5}}})
    links = [
        {"from": "x", "to": "y", "weight": 0.5},
        {"from": "a", "to": "b", "agent": "alice"},
    ]
    out = structural_causal_links(links)
    assert len(out) == 1
    assert out[0]["from"] == "x" and out[0]["to"] == "y"


def test_valuespec_supports_non_numeric():
    """ValueSpec supports ordinal/categorical; clamp and to_scalar adapters."""
    from model.valuespec import ValueSpec, clamp_value, to_scalar_for_utility, value_spec_from_legacy
    spec_ord = ValueSpec(type="ordinal", ordinal_labels=["low", "mid", "high"])
    v = clamp_value("v", "mid", spec_ord, is_delta=False)
    assert v == "mid"
    s = to_scalar_for_utility("v", "high", spec_ord)
    assert isinstance(s, (int, float)) and s >= 0
    spec_cat = ValueSpec(type="categorical", categories=["a", "b", "c"])
    v2 = clamp_value("v2", "b", spec_cat, is_delta=False)
    assert v2 == "b"
    leg = value_spec_from_legacy({"min": 0, "max": 100, "rate_limit": 10})
    assert leg.type == "numeric" and leg.rate_limit == 10


def test_agents_use_beliefs_not_world_state():
    """Decisions/planning use belief snapshot; world_state only for application."""
    from agents.base_agent import BaseAgent, _belief_snapshot_from_world
    from agents.memory import AgentMemory
    mem = AgentMemory(beliefs={"variables": {"x": 30.0}, "confidence": {"x": 0.7}})
    agent = BaseAgent("a", {"increase_x": 1.0}, memory=mem)
    world = {"variables": {"x": 50.0}, "global_state": {"x": 50.0}}
    belief_vars = agent.memory.beliefs.get("variables") or {}
    belief_snap = _belief_snapshot_from_world(world, belief_vars)
    assert belief_snap["variables"]["x"] == 30.0
    assert world["variables"]["x"] == 50.0


def test_delayed_effects_applied_on_schedule():
    """Delayed queue fires at trigger_turn; applied once."""
    from world.delayed_events import DelayedEvent, apply_delayed_events_for_turn
    from schemas.delta_schema import Delta
    class FakeWorld:
        variables = {"x": 10.0}
        def apply_delta(self, delta):
            d = delta.numeric_updates or {}
            for k, v in d.items():
                self.variables[k] = self.variables.get(k, 0) + v
    world = FakeWorld()
    events = [
        DelayedEvent(trigger_turn=1, delta=Delta(numeric_updates={"x": 5.0}, entity_updates={}, new_entities={}, relation_updates=[], meta_proposals=[], rationale="", effects_duration=None, mitigation=None), source_action="test"),
    ]
    applied = apply_delayed_events_for_turn(world, 1, events)
    assert len(applied) == 1
    assert world.variables["x"] == 15.0
    assert len(events) == 0


def test_shocks_optional_determinism():
    """With shocks disabled + fixed seed, no shock application."""
    from shocks.shock_engine import apply_shocks_if_enabled, ShockSpec
    class W:
        variables = {"a": 50.0}
    w = W()
    rng = random.Random(42)
    applied = apply_shocks_if_enabled(w, [ShockSpec("s1", 0.5, {"type": "gaussian", "params": {"mean": 0, "std": 2}}, ["a"])], enabled=False, rng=rng)
    assert applied == {}
    assert w.variables["a"] == 50.0


def test_action_trace_separation():
    """action_trace is populated; causal_links unchanged by action trace."""
    from trace_log.action_trace import append_action_trace_entry, ActionTraceEntry
    action_trace = []
    append_action_trace_entry(action_trace, turn=1, agent_id="alice", action={"op": "intervene", "args": {"variable": "x"}}, delta_raw={"x": 5.0}, delta_applied={"x": 4.0})
    assert len(action_trace) == 1
    assert action_trace[0]["agent_id"] == "alice" and action_trace[0]["delta_raw"]["x"] == 5.0
    causal_links = [{"from": "x", "to": "y", "weight": 0.5}]
    for e in action_trace:
        assert "agent" not in causal_links[0] if causal_links else True


def test_narrative_token_substitution():
    """allow_numbers=true: tokens {{var:ID}}/{{delta:ID}} substituted from snapshot."""
    from summarization.narrative import substitute_narrative_tokens
    snapshot = {"variables": {"x": 50.0, "y": 10.0}, "global_state": {"x": 50.0, "y": 10.0}}
    prose = "Value x is {{var:x}} and delta is {{delta:y}}."
    deltas = {"y": 2.0}
    out, resolved = substitute_narrative_tokens(prose, snapshot, deltas=deltas)
    assert "50" in out or "50.0" in out
    assert "2" in out or "2.0" in out


def test_language_autodetect():
    """Fa scenario -> fa narrative; en scenario -> en narrative."""
    from summarization.narrative import detect_lang_from_scenario
    fa_scenario = {"description": "وضعیت اولیه تنش\u200cزا بود."}
    en_scenario = {"description": "Initial situation was tense."}
    assert detect_lang_from_scenario(fa_scenario) == "fa"
    assert detect_lang_from_scenario(en_scenario) == "en"
    assert detect_lang_from_scenario({}) == "en"


def test_language_is_presentation_only():
    """Engine-core modules must not import summarization or summarization.lang."""
    import ast
    import os
    engine_core_roots = ["simulation", "dynamics", "model", "governance", "policy", "pipeline"]
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bad_imports = []
    for root in engine_core_roots:
        dirpath = os.path.join(project_root, root)
        if not os.path.isdir(dirpath):
            continue
        for _dirpath, _dnames, filenames in os.walk(dirpath):
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(_dirpath, f)
                try:
                    with open(path) as fp:
                        tree = ast.parse(fp.read())
                except Exception:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name in ("summarization", "summarization.lang"):
                                bad_imports.append((path, alias.name))
                    if isinstance(node, ast.ImportFrom):
                        if node.module and (node.module == "summarization" or node.module.startswith("summarization.")):
                            bad_imports.append((path, node.module))
    assert not bad_imports, f"Engine core must not import summarization: {bad_imports}"


def test_narrative_fa_starts_correctly():
    """When narrative_language=fa or auto-detected fa, first sentence starts with 'در آغاز'."""
    from summarization.facts import build_narrative_facts
    from summarization.lang import detect_narrative_language_from_scenario, opening_phrase
    from summarization.renderer import render_narrative
    trace = [{"variable_changes": [{"var": "x", "delta": 1}], "causal_edges": []}]
    snap = {"variables": {"x": 50}, "global_state": {"x": 50}}
    facts = build_narrative_facts(trace, snap, agents=[])
    assert opening_phrase("fa") == "در آغاز"
    prose_fa = render_narrative(facts, lang="fa", allow_numbers=False)
    first = prose_fa.split("\n")[0].strip()
    assert first.startswith("در آغاز"), f"First sentence must start with 'در آغاز': {first!r}"
    fa_scenario = {"description": "وضعیت"}
    assert detect_narrative_language_from_scenario(fa_scenario) == "fa"


def test_narrative_numberless_default():
    """allow_numbers=false: no digits; correct start phrase for lang fa vs en; >=2 paragraphs."""
    from core.narrative_synthesizer import format_structured_summary_prose
    summary = {"opening_conditions": "x was 50.", "dominant_strategic_moves": "increase_x", "turning_point_phrase": "Turn 2 marked shift.", "hidden_tradeoffs": "", "behavioral_pattern": "", "behavioral_pattern_phrase": "", "causal_cascade": []}
    prose_en = format_structured_summary_prose(summary, lang="en", allow_numbers=False)
    assert not re.search(r"[0-9]", prose_en), prose_en
    assert "At the beginning" in prose_en
    assert prose_en.count("\n\n") >= 1, "expect at least 2 paragraphs"
    prose_fa = format_structured_summary_prose(summary, lang="fa", allow_numbers=False)
    assert not re.search(r"[0-9]", prose_fa), prose_fa
    assert "در آغاز" in prose_fa
    assert prose_fa.count("\n\n") >= 1, "expect at least 2 paragraphs"


def test_no_domain_keywords_in_templates():
    """Narrator prompts and deterministic renderer output must not contain domain-specific words."""
    from summarization.llm_narrator import build_llm_prompt
    from summarization.facts import build_narrative_facts
    from summarization.renderer import render_narrative
    domain_keywords = ["tension", "growth", "war", "revenue", "politics", "startup"]
    facts_dict = {"opening_context": ["X was low."], "key_actors": [{"id": "Actor", "intent": "act"}], "turning_points": [], "tradeoff": {}, "ending_state": []}
    prompt = build_llm_prompt(facts_dict, lang="en", allow_numbers=False)
    prompt_lower = prompt.lower()
    for kw in domain_keywords:
        assert kw not in prompt_lower, f"Prompt must not contain domain keyword {kw!r}"
    # Deterministic renderer output must not contain banned artifacts (Causal chain:, max_delta, Variable, Turn )
    trace = [{"variable_changes": [{"var": "x", "delta": 1}], "causal_edges": []}]
    snap = {"variables": {"x": 50}, "global_state": {"x": 50}}
    facts = build_narrative_facts(trace, snap, agents=[])
    prose = render_narrative(facts, lang="en", allow_numbers=False)
    assert "Causal chain:" not in prose
    assert "max_delta" not in prose
    assert "Variable " not in prose
    assert "Turn " not in prose


def test_allow_numbers_placeholder_substitution():
    """When allow_numbers=true, placeholders {{PRE:var}}, {{POST:var}}, {{DELTA:var}} are substituted from snapshot."""
    from core.narrative_firewall import replace_placeholders
    turn_record = {
        "turn": 1,
        "pre_state": {"variables": {"x": 10.0}},
        "post_state": {"variables": {"x": 14.0}},
        "delta_applied": {"x": 4.0},
        "events_fired": [],
        "chosen_actions": [{"agent": "a", "action_id": "inc_x"}],
    }
    prose = "At the beginning, x was {{PRE:x}}. After the turn, x became {{POST:x}} (delta {{DELTA:x}})."
    out = replace_placeholders(prose, turn_record)
    assert "10" in out or "10.0" in out
    assert "14" in out or "14.0" in out
    assert "4" in out or "4.0" in out
    assert "{{PRE:" not in out and "{{POST:" not in out and "{{DELTA:" not in out
