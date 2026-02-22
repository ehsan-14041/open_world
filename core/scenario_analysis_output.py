"""
Scenario analysis output: Logic Core (JSON) and Executive Summary (three paragraphs).
Consumes provenance, final snapshot, scenario, and agents to produce the two-part output format.
"""

from __future__ import annotations

from typing import Any

from core.attribution_layer import build_attribution_sentences
from core.convergence_analysis import analyze_convergence
from core.delta_aggregation import (
    compute_global_delta,
    compute_action_impact_summary,
    summarize_action_impact_by_action_id,
)


def build_logic_core(
    result: dict[str, Any],
    scenario: dict[str, Any] | None = None,
    agents: list[dict[str, Any]] | None = None,
    action_definitions: dict[str, Any] | None = None,
    *,
    allow_numbers: bool = True,
) -> dict[str, Any]:
    """
    Build the Logic Core (JSON/technical) output:
    global_delta, variable_updates, weights, attribution, convergence, action_impact_summary.
    """
    scenario = scenario or {}
    agents = agents or []
    if result is None or not isinstance(result, dict):
        result = {}
    provenance = result.get("provenance") or []
    final = result.get("final") or result
    if final is None or not isinstance(final, dict):
        final = {}
    variables = final.get("variables") or final.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}

    variable_specs = scenario.get("variable_specs") or {}

    global_delta = compute_global_delta(provenance)
    impact_list = compute_action_impact_summary(provenance, action_definitions)
    action_impact_summary = summarize_action_impact_by_action_id(impact_list)

    attribution_sentences = build_attribution_sentences(provenance, allow_numbers=allow_numbers)

    convergence = analyze_convergence(provenance)

    variable_updates: dict[str, Any] = {}
    for var, val in variables.items():
        if isinstance(val, (int, float)):
            spec = (variable_specs.get(var) or {}) if isinstance(variable_specs, dict) else {}
            variable_updates[var] = {
                "value": float(val),
                "min": spec.get("min"),
                "max": spec.get("max"),
                "rate_limit": spec.get("rate_limit"),
            }

    weights: dict[str, dict[str, float]] = {}
    agent_configs = {a.get("name"): a for a in agents if isinstance(a, dict) and a.get("name")}
    for a in (scenario.get("initial_agents") or []):
        if isinstance(a, dict) and a.get("name"):
            agent_configs[a["name"]] = a
    for name, cfg in agent_configs.items():
        obj = (cfg.get("objectives") or cfg.get("goals"))
        if isinstance(obj, dict):
            weights[name] = {k: float(v) for k, v in obj.items() if isinstance(v, (int, float))}

    return {
        "global_delta": global_delta,
        "variable_updates": variable_updates,
        "weights": weights,
        "attribution": attribution_sentences,
        "convergence": {
            "system_label": convergence.get("system_label"),
            "system_reason": convergence.get("system_reason"),
            "per_variable": convergence.get("per_variable", {}),
        },
        "action_impact_summary": action_impact_summary,
    }


def build_executive_summary(
    result: dict[str, Any],
    scenario: dict[str, Any] | None = None,
    agents: list[dict[str, Any]] | None = None,
    facts: Any = None,
    logic_core: dict[str, Any] | None = None,
    *,
    lang: str = "en",
    allow_numbers: bool = False,
) -> dict[str, str]:
    """
    Build the Executive Summary (narrative) as three paragraphs:
    - paragraph_1_what_happened
    - paragraph_2_why_causal
    - paragraph_3_critical_risk_next_turn
    """
    scenario = scenario or {}
    provenance = result.get("provenance") or []
    final = result.get("final") or result
    variables = final.get("variables") or final.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}

    if logic_core is None:
        logic_core = build_logic_core(result, scenario=scenario, agents=agents, allow_numbers=allow_numbers)

    convergence = logic_core.get("convergence") or {}
    attribution = logic_core.get("attribution") or []
    system_reason = convergence.get("system_reason", "")

    # Paragraph 1: What happened (from facts or simple summary)
    if facts is not None and hasattr(facts, "opening_context"):
        opening = getattr(facts, "opening_context", []) or []
        ending = getattr(facts, "ending_state", []) or []
        p1_parts = []
        if opening:
            p1_parts.append(" ".join(opening[:3]))
        if ending:
            p1_parts.append(" ".join(ending[:2]))
        paragraph_1 = " ".join(p1_parts).strip() or "The simulation ran over several turns; key variables evolved from their initial state to a final state."
    else:
        var_names = list(variables.keys())[:3]
        if var_names:
            paragraph_1 = f"The run evolved key variables such as {', '.join(v.replace('_', ' ') for v in var_names)}. The system moved from its initial configuration to a new state over {len(provenance)} turns."
        else:
            paragraph_1 = "The simulation ran over several turns; the system moved from its initial state to a final state."

    # Paragraph 2: Why it happened (causal) — from attribution
    if attribution:
        paragraph_2 = " ".join(attribution[:5]).strip()
        if len(paragraph_2) > 600:
            paragraph_2 = paragraph_2[:597].rsplit(" ", 1)[0] + "."
    else:
        paragraph_2 = "Changes in variables were driven by agent actions and propagation through the causal structure. " + (system_reason or "The trajectory reflects the interplay of chosen strategies and system dynamics.")

    # Paragraph 3: Most critical risk for next turn
    system_label = convergence.get("system_label", "unknown")
    variable_specs = scenario.get("variable_specs") or {}
    events = scenario.get("events") or []
    risk_parts = []
    if system_label == "oscillating":
        risk_parts.append("The most critical risk for the next turn is continued oscillation: without a clear shift in strategy, the system may keep swinging between states rather than settling.")
    elif system_label == "diverging":
        risk_parts.append("The most critical risk is further divergence or instability in key variables if current dynamics continue.")
    else:
        risk_parts.append("The main risk for the next turn depends on whether current strategies are sustained; the system appears to be " + system_label + ".")
    # If any variable is near a typical crisis threshold (e.g. > 80 for tension-like)
    for var, val in variables.items():
        if not isinstance(val, (int, float)):
            continue
        v = float(val)
        if any(kw in var.lower() for kw in ("tension", "conflict", "stress", "crisis")):
            if v > 70:
                risk_parts.append(f"Elevated levels in a key driver suggest heightened risk of escalation if no mitigating action is taken.")
                break
    paragraph_3 = " ".join(risk_parts).strip()

    return {
        "paragraph_1_what_happened": paragraph_1,
        "paragraph_2_why_causal": paragraph_2,
        "paragraph_3_critical_risk_next_turn": paragraph_3,
    }


def build_strategic_analysis(
    result: dict[str, Any],
    scenario: dict[str, Any] | None = None,
    agents: list[dict[str, Any]] | None = None,
    action_definitions: dict[str, Any] | None = None,
    facts: Any = None,
    *,
    lang: str = "en",
    allow_numbers: bool = False,
) -> dict[str, Any]:
    """
    Build the strategic analysis envelope (agents, variables, causal_links, predicted_changes,
    agent_actions, causal_explanations, confidence_scores, strategic_decisions).
    Reuses logic_core and executive_summary; adds structured fields for the Cursor spec.
    """
    scenario = scenario or {}
    result = result or {}
    provenance = result.get("provenance") or []
    final = result.get("final") or result
    if not isinstance(final, dict):
        final = {}
    variables = final.get("variables") or final.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}

    logic_core = build_logic_core(
        result,
        scenario=scenario,
        agents=agents,
        action_definitions=action_definitions,
        allow_numbers=allow_numbers,
    )
    executive_summary = build_executive_summary(
        result,
        scenario=scenario,
        agents=agents,
        facts=facts,
        logic_core=logic_core,
        lang=lang,
        allow_numbers=allow_numbers,
    )

    # Agents: list with role and optional belief/confidence summary
    agents_list: list[dict[str, Any]] = []
    agent_configs = {a.get("name"): a for a in (agents or []) if isinstance(a, dict) and a.get("name")}
    for cfg in scenario.get("initial_agents") or []:
        if isinstance(cfg, dict) and cfg.get("name"):
            agent_configs[cfg["name"]] = cfg
    for name, cfg in agent_configs.items():
        entry = {"name": name, "role": cfg.get("role", ""), "objectives": cfg.get("objectives") or cfg.get("goals") or {}}
        if isinstance(cfg.get("beliefs"), dict):
            entry["beliefs_summary"] = {"variables": cfg["beliefs"].get("variables"), "confidence": cfg["beliefs"].get("confidence")}
        agents_list.append(entry)

    # Variables: key variables and current/final values with optional bounds
    variable_specs = scenario.get("variable_specs") or {}
    variables_out: dict[str, Any] = {}
    for var, val in variables.items():
        if isinstance(val, (int, float)):
            spec = (variable_specs.get(var) or {}) if isinstance(variable_specs, dict) else {}
            variables_out[var] = {"value": float(val), "min": spec.get("min"), "max": spec.get("max")}

    # Causal links: structural only (from, to, weight); no action provenance
    raw_links = final.get("causal_links") or scenario.get("causal_links") or []
    causal_links = []
    for link in raw_links:
        if not isinstance(link, dict) or link.get("from_action") or link.get("agent"):
            continue
        from_var = link.get("from")
        to_var = link.get("to")
        if from_var and to_var:
            causal_links.append({
                "from": from_var,
                "to": to_var,
                "weight": link.get("weight") or link.get("strength"),
                "polarity": link.get("polarity"),
            })

    # Predicted changes: global_delta + per-turn predicted_deltas from provenance
    predicted_changes: dict[str, Any] = {
        "global_delta": logic_core.get("global_delta", {}),
    }
    all_predicted: list[dict[str, Any]] = []
    for p in provenance:
        for pd in p.get("predicted_deltas") or []:
            all_predicted.append({"turn": p.get("turn"), **pd})
    predicted_changes["per_turn_predicted_deltas"] = all_predicted

    # Agent actions: from provenance (chosen_actions / actions)
    agent_actions: list[dict[str, Any]] = []
    for p in provenance:
        turn = p.get("turn")
        for action in p.get("turn_record", {}).get("chosen_actions") or p.get("actions") or []:
            if isinstance(action, dict):
                agent_actions.append({"turn": turn, "agent": action.get("agent"), "action_id": action.get("action_id")})
            else:
                agent_actions.append({"turn": turn, "action": action})

    # Causal explanations: from logic_core attribution
    causal_explanations = logic_core.get("attribution", [])

    # Confidence scores: from convergence and optional per-variable; agent beliefs not in result so use convergence
    convergence = logic_core.get("convergence") or {}
    confidence_scores: dict[str, Any] = {
        "system_convergence": convergence.get("system_label"),
        "system_reason": convergence.get("system_reason"),
        "per_variable": convergence.get("per_variable", {}),
    }

    # Strategic decisions: risks and suggested next steps (from executive_summary and convergence)
    strategic_decisions: list[str] = []
    p3 = executive_summary.get("paragraph_3_critical_risk_next_turn", "")
    if p3:
        strategic_decisions.append(p3)
    if convergence.get("system_label") == "oscillating":
        strategic_decisions.append("Consider shifting strategy to break oscillation.")
    elif convergence.get("system_label") == "diverging":
        strategic_decisions.append("Consider stabilizing or rebalancing key variables.")

    return {
        "agents": agents_list,
        "variables": variables_out,
        "causal_links": causal_links,
        "predicted_changes": predicted_changes,
        "agent_actions": agent_actions,
        "causal_explanations": causal_explanations,
        "confidence_scores": confidence_scores,
        "strategic_decisions": strategic_decisions,
        "logic_core": logic_core,
        "executive_summary": executive_summary,
    }


def build_scenario_analysis_output(
    result: dict[str, Any],
    scenario: dict[str, Any] | None = None,
    agents: list[dict[str, Any]] | None = None,
    action_definitions: dict[str, Any] | None = None,
    facts: Any = None,
    *,
    lang: str = "en",
    allow_numbers: bool = False,
) -> dict[str, Any]:
    """
    Build both Logic Core and Executive Summary. Returns:
    { "logic_core": {...}, "executive_summary": { "paragraph_1_what_happened", ... } }
    """
    logic_core = build_logic_core(
        result,
        scenario=scenario,
        agents=agents,
        action_definitions=action_definitions,
        allow_numbers=allow_numbers,
    )
    executive_summary = build_executive_summary(
        result,
        scenario=scenario,
        agents=agents,
        facts=facts,
        logic_core=logic_core,
        lang=lang,
        allow_numbers=allow_numbers,
    )
    return {
        "logic_core": logic_core,
        "executive_summary": executive_summary,
    }
