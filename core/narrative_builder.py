"""
Narrative builder: from simulation trace and final snapshot, build a structured summary then a coherent narrative.
Uses narrative_synthesizer for structural phases, turning point, pattern classification, and agent role naming.
Produces structured output: Opening Conditions, Dominant Strategic Moves, Causal Cascade, Turning Point,
Hidden Tradeoffs, Behavioral Pattern. No raw float dumps, no generic agent IDs (actor_1), no log-like compression.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from core.narrative_synthesizer import (
    build_structured_narrative_summary,
    format_structured_summary_prose,
    infer_agent_display_names,
    transform_agents_state_with_display_names,
)

from summarization.facts import build_narrative_facts
from summarization.lang import detect_narrative_language_from_scenario, opening_phrase
from summarization.llm_narrator import build_llm_prompt, invoke_llm_narrator
from summarization.renderer import render_narrative
from summarization.validators import validate_narrative

try:
    from core.world_summarizer import detect_language
except ImportError:
    def detect_language(text: str) -> str:
        if not text:
            return "en"
        for c in (text or ""):
            if "\u0600" <= c <= "\u06FF":
                return "fa"
        return "en"

# Legacy trajectory labels (mapped to new pattern taxonomy where applicable)
TRAJECTORY_LABELS = (
    "Stabilization",
    "Escalation",
    "Fragmentation",
    "Adaptation",
    "Stalemate",
    "Illusory improvement",
)

GENERIC_PHRASES_BLOCKLIST = (
    "modest improvement",
    "sharp adjustment",
    "slightly improved",
    "modest activity",
    "shifted modestly",
)


def _lang_from_scenario(scenario: dict[str, Any] | None) -> str:
    """Return 'fa' or 'en' from scenario (presentation-only). Uses summarization.lang."""
    return detect_narrative_language_from_scenario(scenario)


def _classify_trajectory(
    initial_vars: dict[str, float],
    final_vars: dict[str, float],
    var_totals: dict[str, float],
    trace: list[dict[str, Any]],
) -> str:
    """
    Classify system trajectory from variable patterns into one of six labels.
    """
    if not initial_vars and not final_vars:
        return "Stalemate"
    all_vars = set(initial_vars) | set(final_vars)
    deltas = []
    for v in all_vars:
        i = float(initial_vars.get(v, 0) or 0)
        f = float(final_vars.get(v, 0) or 0)
        deltas.append(f - i)
    if not deltas:
        return "Stalemate"
    net = sum(deltas)
    avg_abs = sum(abs(d) for d in deltas) / len(deltas)
    variance = sum((d - net / len(deltas)) ** 2 for d in deltas) / len(deltas) if deltas else 0
    num_positive = sum(1 for d in deltas if d > 0.01)
    num_negative = sum(1 for d in deltas if d < -0.01)
    # Illusory improvement: one metric improves while others worsen or stability drops
    if num_positive >= 1 and num_negative >= 1 and net > 0 and variance > avg_abs * avg_abs:
        return "Illusory improvement"
    # Escalation: key metrics worsening, net negative
    if net < -0.1 * avg_abs * len(deltas) and avg_abs > 0.5:
        return "Escalation"
    # Stabilization: low movement, low variance
    if avg_abs < 0.5 and variance < 1.0:
        return "Stabilization"
    # Fragmentation: high variance, mixed movements
    if variance > max(avg_abs * avg_abs * 3, 2.0) and num_positive >= 1 and num_negative >= 1:
        return "Fragmentation"
    # Adaptation: net positive, coherent movement
    if net > 0.1 * avg_abs * len(deltas):
        return "Adaptation"
    # Stalemate: no clear direction
    return "Stalemate"


def _detect_turning_point(trace: list[dict[str, Any]]) -> tuple[int, float]:
    """Find the turn with the largest total absolute variable change. Returns (turn_index_0based, magnitude)."""
    best_turn, best_mag = 0, 0.0
    for i, entry in enumerate(trace):
        total = 0.0
        for vc in entry.get("variable_changes") or []:
            total += abs(float(vc.get("delta", 0)))
        if total > best_mag:
            best_mag, best_turn = total, i
    return best_turn, best_mag


def _detect_primary_conflict(var_totals: dict[str, float]) -> list[tuple[str, float]]:
    """Detect variable pairs moving in opposite directions; return the strongest pair as [(var1, delta1), (var2, delta2)]."""
    items = [(v, d) for v, d in var_totals.items() if abs(d) > 1e-6]
    best_pair: list[tuple[str, float]] = []
    best_strength = 0.0
    for i, (v1, d1) in enumerate(items):
        for v2, d2 in items[i + 1 :]:
            if (d1 > 0) != (d2 > 0):  # opposite directions
                strength = abs(d1) + abs(d2)
                if strength > best_strength:
                    best_strength = strength
                    best_pair = [(v1, d1), (v2, d2)]
    return best_pair


def _initial_state_from_trace(trace: list[dict[str, Any]], final_snapshot: dict[str, Any]) -> dict[str, float]:
    """Derive initial variables by reversing all variable_changes from the final snapshot."""
    variables = final_snapshot.get("variables") or final_snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}
    init: dict[str, float] = {k: float(v) for k, v in variables.items()}
    for entry in reversed(trace):
        for vc in entry.get("variable_changes") or []:
            var = vc.get("var")
            delta = vc.get("delta", 0)
            if var is not None:
                init[var] = init.get(var, 0) - float(delta)
    return init


def build_compact_turn_log(provenance_entry: dict[str, Any]) -> str:
    """
    Compact strategic log per turn (new default).
    Header: turn, key state highlights. Per agent: chosen action, 1-line reason, applied deltas.
    Environment: triggered events + effects.
    """
    lines: list[str] = []
    turn = provenance_entry.get("turn", 0)
    vcs = provenance_entry.get("variable_changes") or []
    top_changes = sorted(vcs, key=lambda c: abs(float(c.get("delta", 0))), reverse=True)[:5]
    header_parts = [f"Turn {turn}"]
    for vc in top_changes:
        var = vc.get("var", "?")
        d = float(vc.get("delta", 0))
        header_parts.append(f"{var}:{d:+.1f}")
    lines.append(" | ".join(header_parts))

    for p in provenance_entry.get("proposals") or provenance_entry.get("actions") or []:
        name = p.get("agent_name") or p.get("agent") or "?"
        action = p.get("action_type") or p.get("action") or "?"
        rationale = (p.get("rationale") or "")[:80]
        lines.append(f"  {name}: {action} | {rationale}")

    delta = provenance_entry.get("delta") or {}
    nu = delta.get("numeric_updates") or {}
    if nu:
        compact = ", ".join(f"{k}:{v:+.1f}" for k, v in list(nu.items())[:5])
        lines.append(f"  deltas: {compact}")

    events = provenance_entry.get("events_triggered") or []
    if events:
        for ev in events:
            et = ev.get("event_type", "?")
            lines.append(f"  [env] {et}")

    return "\n".join(lines)


def trace_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Build a trace (provenance-like) from a saved snapshot when _last_run_result is unavailable.
    Uses causal_links and agents_state.episodic_memory from the snapshot.
    Returns empty list if snapshot lacks causal_links.
    """
    if snapshot is None or not isinstance(snapshot, dict):
        return []
    causal_links = snapshot.get("causal_links") or []
    if not causal_links:
        return []

    # Group causal_links by turn
    by_turn: dict[int, list[dict[str, Any]]] = {}
    for cl in causal_links:
        t = int(cl.get("turn", 0))
        if t not in by_turn:
            by_turn[t] = []
        by_turn[t].append(dict(cl))

    # Collect actions from episodic_memory per turn
    actions_by_turn: dict[int, list[dict[str, Any]]] = {}
    for agent_name, agent_state in (snapshot.get("agents_state") or {}).items():
        if not isinstance(agent_state, dict):
            continue
        memory = agent_state.get("memory") or {}
        episodic = memory.get("episodic_memory") or []
        for ep in episodic:
            t = int(ep.get("turn", 0))
            act = ep.get("action")
            if act and isinstance(act, dict):
                if t not in actions_by_turn:
                    actions_by_turn[t] = []
                actions_by_turn[t].append({
                    "agent_name": act.get("agent_name") or agent_name,
                    "action_type": act.get("action_type") or "?",
                    "rationale": act.get("rationale") or "",
                })

    trace: list[dict[str, Any]] = []
    for turn in sorted(by_turn.keys()):
        edges = by_turn[turn]
        variable_changes = [{"var": e.get("variable"), "delta": e.get("delta", 0)} for e in edges]
        trace.append({
            "turn": turn,
            "actions": actions_by_turn.get(turn, []),
            "proposals": actions_by_turn.get(turn, []),
            "variable_changes": variable_changes,
            "causal_edges": edges,
        })
    return trace


def _build_summary_dict(
    trace: list[dict[str, Any]],
    final_snapshot: dict[str, Any],
    agents: list[dict[str, Any]] | None = None,
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a structured summary from trace and final state: main conflicts, biggest variable shifts,
    agent motivations, unintended consequences (e.g. large propagation-only changes). No LLM.
    """
    variables = final_snapshot.get("variables") or final_snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}
    conflicts: list[str] = []
    variable_shifts: list[dict[str, Any]] = []
    motivations: list[dict[str, Any]] = []
    unintended: list[str] = []

    # Per-turn magnitude for turning point
    turning_point_turn, turning_point_magnitude = _detect_turning_point(trace)

    # Aggregate variable changes per var across trace
    var_totals: dict[str, float] = {}
    var_by_source: dict[str, dict[str, float]] = {}
    for entry in trace:
        for p in entry.get("actions") or entry.get("proposals") or []:
            name = p.get("agent_name", "?")
            action = p.get("action_type", "?")
            rationale = (p.get("rationale") or "")[:200]
            motivations.append({"agent": name, "action": action, "rationale": rationale})
        for vc in entry.get("variable_changes") or []:
            var = vc.get("var")
            delta = vc.get("delta", 0)
            src = vc.get("source", "direct")
            if var is not None:
                var_totals[var] = var_totals.get(var, 0) + float(delta)
                if var not in var_by_source:
                    var_by_source[var] = {"direct": 0.0, "propagation": 0.0}
                var_by_source[var][src] = var_by_source[var].get(src, 0) + float(delta)

    primary_conflict = _detect_primary_conflict(var_totals)
    initial_vars = _initial_state_from_trace(trace, final_snapshot)
    trajectory_class = _classify_trajectory(initial_vars, variables, var_totals, trace)

    # Causal edges from provenance (action -> variable)
    # CRITICAL: Narrative must use causal_links, not raw logs
    causal_edges: list[dict[str, Any]] = []
    for entry in trace:
        causal_edges.extend(entry.get("causal_edges") or [])
    
    # If no causal edges found, abort (should have been caught earlier, but double-check)
    if not causal_edges:
        raise RuntimeError(
            "CRITICAL: Narrative generation aborted - no causal_edges found in trace. "
            "Narrative engine cannot use raw logs and requires causal_links."
        )

    # Agent roles and per-turn actions by role (use display names for narrative)
    agent_roles: list[dict[str, Any]] = []
    seen_agents: set[str] = set()
    for entry in trace:
        for p in entry.get("actions") or entry.get("proposals") or []:
            name = p.get("agent_name") or p.get("agent")
            role = p.get("role") or name
            if name and name not in seen_agents:
                seen_agents.add(name)
                agent_roles.append({"name": name, "role": role, "actions": []})
            for a in agent_roles:
                if a.get("name") == name:
                    act = p.get("action_type") or p.get("action")
                    if act and (not a["actions"] or a["actions"][-1] != act):
                        a["actions"].append(act)
                    break

    # Apply role-based display names to agent_roles when agents/scenario provided
    if agents is not None or scenario is not None:
        name_to_display = infer_agent_display_names(agents or [], trace, final_snapshot, scenario)
        for a in agent_roles:
            raw_name = a.get("name") or a.get("role")
            display = name_to_display.get(raw_name, raw_name)
            a["display_name"] = display

    # Turning point reason (largest delta or instability shift)
    turning_point_reason = ""
    if trace and turning_point_turn < len(trace):
        turn_entry = trace[turning_point_turn]
        vcs = turn_entry.get("variable_changes") or []
        if vcs:
            biggest = max(vcs, key=lambda c: abs(float(c.get("delta", 0))))
            turning_point_reason = f"largest variable shift in {biggest.get('var', 'state')}"
        if turn_entry.get("instability_mode"):
            turning_point_reason = "instability spike and " + (turning_point_reason or "shift")

    for var, total in sorted(var_totals.items(), key=lambda x: -abs(x[1]))[:15]:
        variable_shifts.append({"var": var, "total_delta": total, "final": variables.get(var)})
        if var in var_by_source and abs(var_by_source[var].get("propagation", 0)) > abs(var_by_source[var].get("direct", 0)):
            unintended.append(f"{var} moved largely by propagation (cascade effects)")

    return {
        "conflicts": conflicts,
        "variable_shifts": variable_shifts,
        "motivations": motivations[:20],
        "unintended_consequences": unintended,
        "num_turns": len(trace),
        "final_variables": dict(variables),
        "initial_variables": initial_vars,
        "turning_point_turn": turning_point_turn,
        "turning_point_magnitude": turning_point_magnitude,
        "turning_point_reason": turning_point_reason or "largest aggregate change",
        "primary_conflict": primary_conflict,
        "causal_edges": causal_edges,
        "agent_roles": agent_roles,
        "trajectory_class": trajectory_class,
    }


def build_narrative(
    trace: list[dict[str, Any]],
    final_snapshot: dict[str, Any],
    *,
    use_llm: bool | None = None,
    llm_callback: Callable[[str, str | None], str] | None = None,
    agents: list[dict[str, Any]] | None = None,
    scenario: dict[str, Any] | None = None,
    lang: str = "auto",
    allow_numbers: bool = False,
) -> str:
    """
    Produce a coherent narrative from trace and final snapshot. If llm_callback provided,
    use_llm defaults to True unless explicitly False. Deterministic path uses unified formatter
    (Persian-first when lang=fa), story from the beginning, no digits unless allow_numbers=True.
    """
    # Auto-enable LLM when callback provided unless explicitly disabled
    if use_llm is None and llm_callback is not None:
        use_llm = True
    elif use_llm is None:
        use_llm = False

    # Language: from scenario when lang=auto
    if lang == "auto":
        lang = _lang_from_scenario(scenario)

    # CRITICAL: Check if causal_links exist
    causal_links_found = False
    for entry in trace:
        if entry.get("causal_edges"):
            causal_links_found = True
            break
    if not causal_links_found:
        snapshot_causal_links = final_snapshot.get("causal_links") or []
        if snapshot_causal_links:
            causal_links_found = True
    if not causal_links_found:
        raise RuntimeError(
            "CRITICAL: Narrative generation aborted - causal_links are empty. "
            "Narrative engine cannot proceed without causal edges. "
            "Simulation must create causal_links for every numeric_updates entry."
        )

    summary_dict = _build_summary_dict(trace, final_snapshot, agents=agents, scenario=scenario)
    state_specs = (scenario or {}).get("variable_specs") or (scenario or {}).get("state_spec") or {}
    facts = build_narrative_facts(
        trace, final_snapshot, agents=agents, scenario=scenario, state_specs=state_specs
    )

    if use_llm and llm_callback:
        for _ in range(2):  # try once, retry once on validation failure
            try:
                out = invoke_llm_narrator(facts, llm_callback, lang=lang, allow_numbers=allow_numbers)
                if isinstance(out, str) and len(out.strip()) > 20:
                    out = _strip_generic_phrases(out.strip())
                    if len(out.split()) > 180:
                        out = " ".join(out.split()[:180]).strip()
                    passed, reason = validate_narrative(out, lang=lang, allow_numbers=allow_numbers)
                    if passed:
                        return out
            except Exception:
                pass
        return render_narrative(facts, lang=lang, allow_numbers=allow_numbers)

    # Deterministic: Layer 2 from NarrativeFacts only
    try:
        prose = render_narrative(facts, lang=lang, allow_numbers=allow_numbers)
        if prose and len(prose) > 50:
            return prose
    except Exception:
        pass
    try:
        synth = build_structured_narrative_summary(trace, final_snapshot, agents or [], scenario=scenario)
        prose = format_structured_summary_prose(synth, lang=lang, allow_numbers=allow_numbers)
        if prose and len(prose) > 50:
            return prose
    except Exception:
        pass

    initial_vars = summary_dict.get("initial_variables") or _initial_state_from_trace(trace, final_snapshot)
    agents_from_trace = summary_dict.get("agent_roles") or []
    if not agents_from_trace:
        seen: set[str] = set()
        for entry in trace:
            for p in entry.get("actions") or entry.get("proposals") or []:
                name = p.get("agent_name") or p.get("agent")
                if name and name not in seen:
                    seen.add(name)
                    agents_from_trace.append({"name": name, "role": name, "objectives": {}})
    return _build_paragraph_dry_run(trace, initial_vars, final_snapshot, agents_from_trace, summary_dict)


def _infer_tone(initial: dict[str, Any], final: dict[str, Any]) -> str:
    """
    Classify system tone from variance and net deltas.
    Returns one of: stable, escalating, fragile, improving, volatile.
    """
    if "variables" in final or "global_state" in final:
        vars_final = final.get("variables") or final.get("global_state") or {}
    else:
        vars_final = final
    if not isinstance(vars_final, dict):
        vars_final = {}
    initial = initial or {}
    if not isinstance(initial, dict):
        initial = {}
    all_vars = set(initial) | set(vars_final)
    if not all_vars:
        return "stable"
    deltas = []
    for v in all_vars:
        i = float(initial.get(v, 0) or 0)
        f = float(vars_final.get(v, 0) or 0)
        deltas.append(f - i)
    if not deltas:
        return "stable"
    net = sum(deltas)
    avg_abs = sum(abs(d) for d in deltas) / len(deltas) if deltas else 0
    mean_d = net / len(deltas)
    variance = sum((d - mean_d) ** 2 for d in deltas) / len(deltas) if deltas else 0

    if avg_abs < 0.01:
        return "stable"
    # High variance in deltas → volatile
    if variance > max(avg_abs * avg_abs * 2, 1.0):
        return "volatile"
    # Large net negative movement → escalating
    if net < -0.15 * avg_abs * len(deltas):
        return "escalating"
    # Net positive, moderate movement → improving
    if net > 0.15 * avg_abs * len(deltas):
        return "improving" if avg_abs > 0.5 else "stable"
    # Mixed signs, moderate variance → fragile
    return "fragile"


def _humanize_var(name: str) -> str:
    """Turn variable name into readable phrase (e.g. negotiation_progress -> negotiation progress)."""
    return name.replace("_", " ").strip()


def _build_paragraph_dry_run(
    trace: list[dict[str, Any]],
    initial_state: dict[str, Any],
    final_state: dict[str, Any],
    agents: list[dict[str, Any]],
    summary_dict: dict[str, Any],
) -> str:
    """
    Compose one paragraph (120–180 words): initial context, agent intentions, conflict/tradeoff,
    turning point, trajectory classification, consequence framing. Causal connectors; no generic blocklist phrases.
    """
    init_vars = initial_state if isinstance(initial_state, dict) else {}
    fin_vars = final_state.get("variables") or final_state.get("global_state") or {}
    if not isinstance(fin_vars, dict):
        fin_vars = {}
    shifts = summary_dict.get("variable_shifts", [])[:5]
    turning_turn = summary_dict.get("turning_point_turn", len(trace) // 2 if trace else 0)
    primary_conflict = summary_dict.get("primary_conflict", [])
    trajectory_class = summary_dict.get("trajectory_class") or "Stalemate"
    turning_reason = summary_dict.get("turning_point_reason") or "largest aggregate change"
    agent_roles = summary_dict.get("agent_roles") or []

    # 1. Initial context: dominant system condition, at least two key variables
    init_keys = [s["var"] for s in shifts][:3]
    if not init_keys:
        init_keys = list(init_vars.keys())[:3] if init_vars else list(fin_vars.keys())[:3]
    init_phrases = []
    for k in init_keys[:2]:
        val = init_vars.get(k, fin_vars.get(k))
        if val is not None and isinstance(val, (int, float)):
            if val >= 60:
                level = "high"
            elif val >= 30:
                level = "moderate"
            else:
                level = "low"
            init_phrases.append(f"{_humanize_var(k)} at {level} levels")
        elif k:
            init_phrases.append(f"{_humanize_var(k)} in flux")
    beginning = "The run opened with " + (", ".join(init_phrases) if init_phrases else "two or more key variables in play") + "."

    # 2. Agent intentions: which agent types acted and what strategic direction (use display names)
    role_names = [
        a.get("display_name") or a.get("role") or a.get("name")
        for a in agent_roles
        if a.get("name") or a.get("role")
    ]
    if not role_names and agents:
        role_names = [a.get("name", "actor") for a in (agents or []) if isinstance(a, dict)]
    strategic_actions = []
    for a in agent_roles:
        acts = a.get("actions") or []
        display = a.get("display_name") or a.get("role") or a.get("name")
        if acts:
            strategic_actions.append(f"{display} pursued {acts[0]}")
    agent_sentence = " " + ", ".join(strategic_actions[:3]) + "." if strategic_actions else f" Agents ({', '.join(role_names[:3])}) took action." if role_names else " Multiple agents pursued distinct strategies."

    # 3. Conflict or tradeoff: "X improved, but Y deteriorated" with causal connector
    if primary_conflict:
        v1, d1 = primary_conflict[0]
        v2, d2 = primary_conflict[1]
        up_var = v1 if d1 > 0 else v2
        down_var = v2 if d1 > 0 else v1
        tradeoff = f" As a result, {_humanize_var(up_var)} rose while {_humanize_var(down_var)} fell, which triggered competing pressures."
    else:
        # Describe one tradeoff from variable_shifts (one up, one down)
        up_down = [(s["var"], s["total_delta"]) for s in shifts if abs(s.get("total_delta", 0)) > 0.01]
        ups = [v for v, d in up_down if d > 0]
        downs = [v for v, d in up_down if d < 0]
        if ups and downs:
            tradeoff = f" Because {_humanize_var(ups[0])} increased while {_humanize_var(downs[0])} decreased, the system experienced a clear tradeoff."
        else:
            tradeoff = " Variable movements produced interdependent effects across the run."

    # 4. Turning point: turn with largest delta or instability shift, why it changed trajectory
    turn_label = turning_turn + 1 if trace else 0
    turning = f" Turn {turn_label} marked the turning point ({turning_reason}), leading to a new trajectory."

    # 5. System trajectory classification (one of six)
    trajectory_sentence = f" The outcome fits a {trajectory_class} pattern."

    # 6. Consequence framing: interpretive conclusion about structural health (no generic blocklist)
    if trajectory_class == "Escalation":
        consequence = " Structural stress increased and the system became more brittle."
    elif trajectory_class == "Stabilization":
        consequence = " The system settled into a more coherent configuration."
    elif trajectory_class == "Adaptation":
        consequence = " Agents and variables moved toward a more sustainable configuration."
    elif trajectory_class == "Fragmentation":
        consequence = " Divergent variable movements left the system structurally fragmented."
    elif trajectory_class == "Illusory improvement":
        consequence = " Surface gains in one dimension masked deterioration elsewhere."
    else:
        consequence = " No clear resolution emerged; the system remained in tension."

    para = beginning + agent_sentence + tradeoff + turning + trajectory_sentence + consequence
    words = para.split()
    if len(words) > 180:
        para = " ".join(words[:180]).strip()
    para = _strip_generic_phrases(para)
    return _ensure_narrative_constraints(para, summary_dict, init_vars, fin_vars, agent_roles, agents)


def _strip_generic_phrases(text: str) -> str:
    for phrase in GENERIC_PHRASES_BLOCKLIST:
        text = re.sub(re.escape(phrase), "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _ensure_narrative_constraints(
    para: str,
    summary_dict: dict[str, Any],
    init_vars: dict[str, Any],
    fin_vars: dict[str, Any],
    agent_roles: list[dict[str, Any]],
    agents: list[dict[str, Any]],
) -> str:
    """Ensure at least 2 variables, 1 agent role, 1 causal connector mentioned."""
    causal_connectors = ("because", "as a result", "which triggered", "leading to")
    has_causal = any(c in para.lower() for c in causal_connectors)
    var_names = list(init_vars.keys())[:5] + list(fin_vars.keys())[:5]
    mentioned_vars = [v for v in var_names if _humanize_var(v) in para or v in para]
    roles = [
        a.get("display_name") or a.get("role") or a.get("name")
        for a in (agent_roles or [])
        if a.get("role") or a.get("name")
    ]
    if not roles and agents:
        roles = [a.get("name") for a in agents if isinstance(a, dict) and a.get("name")]
    has_role = any(r and r in para for r in roles)
    if not has_causal and " which " in para:
        has_causal = True
    if len(mentioned_vars) < 2 and var_names:
        para = para + f" Key variables such as {_humanize_var(var_names[0])} and {_humanize_var(var_names[1])} drove the outcome."
    if not has_role and roles:
        para = para + f" The {roles[0]} and others shaped this outcome."
    if not has_causal:
        para = para + " As a result, the run reflected these dynamics."
    words = para.split()
    if len(words) > 180:
        para = " ".join(words[:180]).strip()
    return para


def build_structured_summary(
    trace: list[dict[str, Any]],
    initial_state: dict[str, Any],
    final_state: dict[str, Any],
    agents: list[dict[str, Any]],
    *,
    use_llm: bool = False,
    llm_callback: Callable[[str, str | None], str] | None = None,
    scenario: dict[str, Any] | None = None,
    lang: str = "auto",
    allow_numbers: bool = False,
) -> str:
    """
    Produce a structured narrative summary using the narrative synthesizer layer.
    Uses unified formatter (Persian-first when lang=fa), from the beginning, no digits unless allow_numbers=True.
    """
    if lang == "auto":
        lang = _lang_from_scenario(scenario)
    try:
        synth = build_structured_narrative_summary(
            trace, final_state, agents, scenario=scenario
        )
        prose = format_structured_summary_prose(synth, lang=lang, allow_numbers=allow_numbers)
        if prose and len(prose) > 50:
            return prose
    except Exception:
        pass

    # Fallback to legacy _build_summary_dict path
    summary_dict = _build_summary_dict(trace, final_state, agents=agents, scenario=scenario)
    if use_llm and llm_callback:
        init_vars = initial_state if isinstance(initial_state, dict) else {}
        fin_vars = final_state.get("variables") or final_state.get("global_state") or {}
        if not isinstance(fin_vars, dict):
            fin_vars = {}
        name_to_display = infer_agent_display_names(agents, trace, final_state, scenario)
        context = {
            **summary_dict,
            "initial_state": init_vars,
            "final_state": fin_vars,
            "actors": [
                {
                    "name": name_to_display.get(a.get("name"), a.get("name")),
                    "role": a.get("role"),
                    "objectives": a.get("objectives", {}),
                }
                for a in (agents or [])
                if isinstance(a, dict)
            ],
        }
        lang_instruction = "Write in Persian." if _lang_from_scenario(scenario) == "fa" else "Write in English."
        number_instruction = "Do not include any digits or raw numbers." if not allow_numbers else "You may include numbers if relevant."
        prompt = (
            f"{lang_instruction} Start from the beginning. {number_instruction} "
            "Use a causal narrative in 2–3 short paragraphs. Do not invent facts beyond the provided summary. "
            "Include: (1) Initial situation and key variables. (2) Dominant strategic moves. "
            "(3) At least one tradeoff with causal connectors. (4) Turning point. "
            "(5) Behavioral pattern (domain-agnostic). (6) Consequence framing. Use role names, not generic IDs. "
            "Analytical tone.\n\n"
            f"Context:\n{json.dumps(context, default=str, indent=2)}"
        )
        try:
            out = llm_callback(prompt, "You are a narrative writer. Output only the narrative prose, no headers.")
            if isinstance(out, str) and len(out.strip()) > 20:
                out = _strip_generic_phrases(out.strip())
                words = out.split()
                if len(words) > 180:
                    out = " ".join(words[:180]).strip()
                return out
        except Exception:
            pass
    init_vars = summary_dict.get("initial_variables") or (initial_state if isinstance(initial_state, dict) else {})
    return _build_paragraph_dry_run(trace, init_vars, final_state, agents, summary_dict)


def prepare_final_output_with_role_names(
    final_state: dict[str, Any],
    agents: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Return a copy of final_state with agents_state keys transformed to role-based display names
    (e.g. "Founder (Risk-Tolerant)" instead of "actor_1") and belief_narrative added per agent.
    """
    out = dict(final_state)
    agents_state = out.get("agents_state") or {}
    if not agents_state:
        return out
    name_to_display = infer_agent_display_names(agents, trace, final_state, scenario)
    out["agents_state"] = transform_agents_state_with_display_names(
        agents_state, name_to_display, interpret_beliefs=True
    )
    return out
