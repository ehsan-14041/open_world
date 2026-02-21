"""
Narrative Synthesizer: structured narrative synthesis from simulation logs.
Replaces raw state-log summaries with interpreted narrative descriptions.
Extracts structural phases, detects turning points, diminishing returns, and behavioral patterns.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

def _strip_digits(text: str, allow: bool) -> str:
    """Remove Western digits when allow is False (avoid dependency for tests)."""
    if allow or not text:
        return text
    return re.sub(r"\s+", " ", re.sub(r"-?\d+\.?\d*", "", text)).strip()


def _detect_lang(text: str) -> str:
    """Returns 'fa' if any char in \\u0600-\\u06FF."""
    if not text:
        return "en"
    for c in text:
        if "\u0600" <= c <= "\u06FF":
            return "fa"
    return "en"

# ---------------------------------------------------------------------------
# Part 1 — Structural Phase Extraction
# ---------------------------------------------------------------------------


def extract_structural_phases(
    trace: list[dict[str, Any]],
    final_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """
    From the simulation log compute:
    - Opening conditions (initial state snapshot)
    - Dominant strategy cluster (most repeated action class)
    - Largest delta turn (max total absolute state change)
    - First constraint activation (if any)
    - Instability peak
    - Repeated action monotony detection
    """
    variables = final_snapshot.get("variables") or final_snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}

    # Derive initial state by reversing variable_changes
    initial_vars = _initial_state_from_trace(trace, final_snapshot)

    # Opening conditions
    opening_conditions = dict(initial_vars)

    # Dominant strategy cluster: most repeated action class
    action_counts: Counter[str] = Counter()
    for entry in trace:
        for p in entry.get("actions") or entry.get("proposals") or []:
            action = p.get("action_type") or p.get("action") or ""
            if action:
                action_counts[action] += 1
    dominant_action = action_counts.most_common(1)[0][0] if action_counts else ""
    dominant_strategy_cluster = dominant_action

    # Largest delta turn
    largest_delta_turn = 0
    largest_delta_magnitude = 0.0
    turn_deltas: list[float] = []
    for i, entry in enumerate(trace):
        total = 0.0
        for vc in entry.get("variable_changes") or []:
            total += abs(float(vc.get("delta", 0)))
        turn_deltas.append(total)
        if total > largest_delta_magnitude:
            largest_delta_magnitude = total
            largest_delta_turn = i

    # First constraint activation (repaired deltas)
    first_constraint_turn: int | None = None
    for i, entry in enumerate(trace):
        for vc in entry.get("variable_changes") or []:
            if vc.get("repaired"):
                first_constraint_turn = i
                break
        if first_constraint_turn is not None:
            break

    # Instability peak: turn with highest instability_mode or dissatisfaction
    instability_peak_turn = 0
    instability_peak_val = 0.0
    for i, entry in enumerate(trace):
        derived = entry.get("derived") or {}
        diss = float(derived.get("dissatisfaction", 0) or 0)
        inst_mode = bool(derived.get("instability_mode", False))
        val = diss + (100.0 if inst_mode else 0.0)
        if val > instability_peak_val:
            instability_peak_val = val
            instability_peak_turn = i

    # Repeated action monotony: same action 3+ times in a row
    repeated_action_monotony = False
    agent_actions: dict[str, list[str]] = {}
    for entry in trace:
        for p in entry.get("actions") or entry.get("proposals") or []:
            name = p.get("agent_name") or p.get("agent") or "?"
            action = p.get("action_type") or p.get("action") or ""
            if name not in agent_actions:
                agent_actions[name] = []
            agent_actions[name].append(action)

    for actions in agent_actions.values():
        if len(actions) >= 3:
            for j in range(len(actions) - 2):
                if actions[j] == actions[j + 1] == actions[j + 2]:
                    repeated_action_monotony = True
                    break

    return {
        "opening_conditions": opening_conditions,
        "dominant_strategy_cluster": dominant_strategy_cluster,
        "largest_delta_turn": largest_delta_turn,
        "largest_delta_magnitude": largest_delta_magnitude,
        "first_constraint_turn": first_constraint_turn,
        "instability_peak_turn": instability_peak_turn,
        "repeated_action_monotony": repeated_action_monotony,
        "turn_deltas": turn_deltas,
    }


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


# ---------------------------------------------------------------------------
# Part 2 — Turning Point Detection
# ---------------------------------------------------------------------------


def detect_turning_point(
    trace: list[dict[str, Any]],
    phases: dict[str, Any],
) -> dict[str, Any]:
    """
    Turning point = earliest turn where one of these occurs:
    - Maximum total state delta
    - Instability spike (local max)
    - First major constraint trigger
    - First large capital injection (if applicable)

    Returns: turn_index, dominant_variable_shift, reason_tag
    """
    turn_deltas = phases.get("turn_deltas") or []
    largest_delta_turn = phases.get("largest_delta_turn", 0)
    first_constraint_turn = phases.get("first_constraint_turn")
    instability_peak_turn = phases.get("instability_peak_turn", 0)

    # Domain-agnostic: first large positive shift = turn where any var delta exceeds mean+2*std of turn_deltas
    large_injection_turn: int | None = None
    if turn_deltas:
        mean_d = sum(turn_deltas) / len(turn_deltas)
        variance = sum((d - mean_d) ** 2 for d in turn_deltas) / len(turn_deltas)
        std_d = (variance ** 0.5) if variance > 0 else 0.0
        threshold = mean_d + 2.0 * std_d
        for i, entry in enumerate(trace):
            for vc in entry.get("variable_changes") or []:
                delta = float(vc.get("delta", 0))
                if delta >= max(threshold, 1.0):
                    large_injection_turn = i
                    break
            if large_injection_turn is not None:
                break

    # Pick earliest among candidates
    candidates: list[tuple[int, str]] = []
    if turn_deltas and largest_delta_turn < len(trace):
        # Get dominant variable shift for largest delta turn
        entry = trace[largest_delta_turn]
        vcs = entry.get("variable_changes") or []
        if vcs:
            biggest = max(vcs, key=lambda c: abs(float(c.get("delta", 0))))
            dom_var = biggest.get("var", "state")
        else:
            dom_var = "state"
        candidates.append((largest_delta_turn, f"max_delta:{dom_var}"))

    if first_constraint_turn is not None:
        candidates.append((first_constraint_turn, "constraint_trigger"))

    if large_injection_turn is not None:
        candidates.append((large_injection_turn, "large_shift"))

    # Instability peak as local max
    if len(turn_deltas) >= 3:
        for i in range(1, len(turn_deltas) - 1):
            if turn_deltas[i] >= turn_deltas[i - 1] and turn_deltas[i] >= turn_deltas[i + 1]:
                if turn_deltas[i] > 0.5 * (turn_deltas[i - 1] + turn_deltas[i + 1]):
                    candidates.append((i, "instability_spike"))
                    break

    if not candidates:
        return {
            "turn_index": 0,
            "dominant_variable_shift": "state",
            "reason_tag": "opening",
        }

    candidates.sort(key=lambda x: x[0])
    turn_index, reason_tag = candidates[0]

    # Resolve dominant variable for this turn
    dominant_variable_shift = "state"
    if turn_index < len(trace):
        entry = trace[turn_index]
        vcs = entry.get("variable_changes") or []
        if vcs:
            biggest = max(vcs, key=lambda c: abs(float(c.get("delta", 0))))
            dominant_variable_shift = biggest.get("var", "state")
        if reason_tag.startswith("max_delta:"):
            dominant_variable_shift = reason_tag.split(":", 1)[1]
            reason_tag = "max_delta"

    return {
        "turn_index": turn_index,
        "dominant_variable_shift": dominant_variable_shift,
        "reason_tag": reason_tag,
    }


# ---------------------------------------------------------------------------
# Part 3 — Diminishing Returns Detection
# ---------------------------------------------------------------------------


def detect_diminishing_returns(
    trace: list[dict[str, Any]],
    phases: dict[str, Any],
) -> bool:
    """
    If same action repeated >2 times AND marginal delta shrinks each time:
    Mark as diminishing_returns = True
    """
    if not phases.get("repeated_action_monotony"):
        return False

    # Check per-agent: same action 3+ times with shrinking marginal deltas
    agent_action_deltas: dict[str, list[tuple[str, float]]] = {}
    for i, entry in enumerate(trace):
        vcs = entry.get("variable_changes") or []
        turn_total = sum(abs(float(c.get("delta", 0))) for c in vcs)
        for p in entry.get("actions") or entry.get("proposals") or []:
            name = p.get("agent_name") or p.get("agent") or "?"
            action = p.get("action_type") or p.get("action") or ""
            if name not in agent_action_deltas:
                agent_action_deltas[name] = []
            agent_action_deltas[name].append((action, turn_total))

    for history in agent_action_deltas.values():
        if len(history) < 3:
            continue
        for j in range(len(history) - 2):
            a1, a2, a3 = history[j][0], history[j + 1][0], history[j + 2][0]
            d1, d2, d3 = history[j][1], history[j + 1][1], history[j + 2][1]
            if a1 == a2 == a3 and d1 > d2 > d3 and d3 > 0:
                return True
    return False


# ---------------------------------------------------------------------------
# Part 4 — Pattern Classification (Rule-based)
# ---------------------------------------------------------------------------

PATTERN_LABELS = (
    "Illusory Stabilization",
    "Defensive Lock-in",
    "Competitive Drift",
    "Governance Dominance",
    "Escalatory Volatility",
    "Strategic Stagnation",
)

# Generic Persian labels for pattern (domain-agnostic)
PATTERN_LABELS_FA = {
    "Illusory Stabilization": "ثبات ظاهری",
    "Defensive Lock-in": "قفل دفاعی",
    "Competitive Drift": "انحراف رقابتی",
    "Governance Dominance": "سلطه حکمرانی",
    "Escalatory Volatility": "نوسان تصاعدی",
    "Strategic Stagnation": "رکود راهبردی",
}


def classify_pattern(
    trace: list[dict[str, Any]],
    final_snapshot: dict[str, Any],
    phases: dict[str, Any],
    turning_point: dict[str, Any],
    diminishing_returns: bool,
) -> str:
    """
    Rule-based classification into behavioral pattern labels.
    """
    variables = final_snapshot.get("variables") or final_snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}
    initial = phases.get("opening_conditions") or {}
    var_totals: dict[str, float] = {}
    for entry in trace:
        for vc in entry.get("variable_changes") or []:
            var = vc.get("var")
            delta = vc.get("delta", 0)
            if var is not None:
                var_totals[var] = var_totals.get(var, 0) + float(delta)

    # Domain-agnostic: use magnitudes and counts only
    turn_deltas = phases.get("turn_deltas") or []
    same_action_3plus = phases.get("repeated_action_monotony", False)
    total_abs_delta = sum(abs(d) for d in var_totals.values())
    sorted_vars = sorted(var_totals.items(), key=lambda x: -abs(x[1]))
    top_positive = [v for v, d in sorted_vars if d > 0.5][:3]
    top_negative = [v for v, d in sorted_vars if d < -0.5][:3]
    net_positive = sum(var_totals.values()) > 0.5
    net_negative = sum(var_totals.values()) < -0.5
    has_both_directions = len(top_positive) >= 1 and len(top_negative) >= 1

    # Defensive Lock-in: same action 3+ turns + diminishing returns
    if same_action_3plus and diminishing_returns:
        return "Defensive Lock-in"

    # Governance Dominance: many repaired deltas
    if phases.get("first_constraint_turn") is not None:
        repair_count = sum(
            1 for e in trace for vc in (e.get("variable_changes") or []) if vc.get("repaired")
        )
        if repair_count >= max(1, len(trace) * 2):
            return "Governance Dominance"

    # Escalatory Volatility: high variance in turn deltas
    if len(turn_deltas) >= 3:
        mean_d = sum(turn_deltas) / len(turn_deltas)
        variance = sum((d - mean_d) ** 2 for d in turn_deltas) / len(turn_deltas)
        if variance > mean_d * mean_d * 2 and mean_d > 1e-6:
            return "Escalatory Volatility"

    # Illusory Stabilization: net positive but strong opposite movements (tradeoff)
    if net_positive and has_both_directions and total_abs_delta > 10:
        return "Illusory Stabilization"

    # Competitive Drift / stagnation: mixed or low movement
    if has_both_directions and total_abs_delta < 20 and len(trace) >= 2:
        return "Competitive Drift"

    # Strategic Stagnation: low movement
    if sum(abs(d) for d in turn_deltas) < 5 and len(trace) >= 3:
        return "Strategic Stagnation"

    return "Strategic Stagnation"


# ---------------------------------------------------------------------------
# Part 5 — Agent Role Naming
# ---------------------------------------------------------------------------


def infer_agent_display_names(
    agents: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    final_snapshot: dict[str, Any],
    scenario: dict[str, Any] | None = None,
) -> dict[str, str]:
    """
    Map agent name -> display name. Domain-agnostic: use explicit role (humanized) from scenario,
    or generic "Primary Mover (humanized_var)" from impact; no domain roles like Capital Actor, Staff, etc.
    """
    name_to_display: dict[str, str] = {}
    agent_configs: dict[str, dict] = {}
    for a in agents or []:
        if isinstance(a, dict) and a.get("name"):
            agent_configs[a["name"]] = a
    # Also pull from scenario.initial_agents if not in agents
    if scenario:
        for a in scenario.get("initial_agents") or []:
            if isinstance(a, dict) and a.get("name") and a["name"] not in agent_configs:
                agent_configs[a["name"]] = a
    # Also pull from agents_state keys if we have final_snapshot
    agents_state = final_snapshot.get("agents_state") or {}
    for raw_name in agents_state:
        if raw_name not in agent_configs:
            agent_configs[raw_name] = {"name": raw_name, "role": raw_name}

    # 1. Use explicit role from scenario/agent config
    for name, cfg in agent_configs.items():
        role = cfg.get("role") or ""
        if role and not _is_generic_id(name):
            # Add behavioral suffix if we have personality hints
            suffix = ""
            if cfg.get("personality"):
                low = cfg["personality"].lower()
                if "risk" in low or "aggressive" in low:
                    suffix = " (Risk-Tolerant)"
                elif "capital" in low or "disciplined" in low:
                    suffix = " (Capital-Disciplined)"
                elif "morale" in low or "team" in low:
                    suffix = " (Morale-Driven)"
            name_to_display[name] = _humanize_role(role) + suffix

    # 2. Infer for generic IDs (actor_1, agent_1, etc.)
    causal_links = final_snapshot.get("causal_links") or []
    for entry in trace:
        causal_links = causal_links + (entry.get("causal_edges") or [])

    agent_impacts: dict[str, dict[str, float]] = {}
    for cl in causal_links:
        agent = cl.get("agent") or ""
        var = (cl.get("variable") or "").lower()
        delta = abs(float(cl.get("delta", 0)))
        if not agent:
            continue
        if agent not in agent_impacts:
            agent_impacts[agent] = {}
        agent_impacts[agent][var] = agent_impacts[agent].get(var, 0) + delta

    for name in agent_configs:
        if name in name_to_display:
            continue
        if not _is_generic_id(name):
            name_to_display[name] = _humanize_role(agent_configs[name].get("role", name))
            continue

        # Domain-agnostic: infer from which variable this agent moved most (impact-based)
        impacts = agent_impacts.get(name) or {}
        if not impacts:
            name_to_display[name] = _humanize_role(agent_configs.get(name, {}).get("role", name))
            continue
        top_var = max(impacts.items(), key=lambda x: x[1])
        var_name = top_var[0]
        # Generic label: "Primary Mover" with humanized variable, or just role
        humanized_var = _humanize_var(var_name)
        name_to_display[name] = f"Primary Mover ({humanized_var})"

    return name_to_display


def _is_generic_id(name: str) -> bool:
    n = (name or "").lower()
    return n.startswith("actor_") or n.startswith("agent_") or n in ("actor", "agent")


def _humanize_role(role: str) -> str:
    if not role:
        return "Actor"
    import re
    s = str(role).replace("_", " ").strip()
    # CamelCase -> "Camel Case" (e.g. CommunityLeader -> Community Leader)
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return s.title() if s else "Actor"


def transform_agents_state_with_display_names(
    agents_state: dict[str, Any],
    name_to_display: dict[str, str],
    *,
    interpret_beliefs: bool = True,
) -> dict[str, Any]:
    """
    Transform agents_state keys from raw names to display names.
    Optionally add belief_narrative to each agent state (interpreted from raw beliefs).
    Output format: "Founder (Risk-Tolerant)": {...}, "Investor (Capital-Disciplined)": {...}
    """
    out: dict[str, Any] = {}
    for raw_name, state in agents_state.items():
        display = name_to_display.get(raw_name) or _humanize_role(raw_name)
        state_copy = dict(state) if isinstance(state, dict) else {}
        if interpret_beliefs and isinstance(state_copy, dict):
            beliefs = state_copy.get("beliefs") or state_copy.get("memory", {}).get("beliefs")
            if beliefs:
                narrative_lines = interpret_beliefs_to_narrative(beliefs)
                if narrative_lines:
                    state_copy["belief_narrative"] = " ".join(narrative_lines)
        out[display] = state_copy
    return out


# ---------------------------------------------------------------------------
# Part 6 — Belief Interpretation Layer
# ---------------------------------------------------------------------------

BELIEF_THRESHOLDS = [
    (0.0, 0.3, "low"),
    (0.3, 0.6, "moderate"),
    (0.6, 0.8, "high"),
    (0.8, 1.01, "dominant"),
]


def _threshold_label(value: float) -> str:
    for lo, hi, label in BELIEF_THRESHOLDS:
        if lo <= value < hi:
            return label
    return "moderate"


def interpret_beliefs_to_narrative(
    beliefs: dict[str, Any],
    prev_beliefs: dict[str, Any] | None = None,
) -> list[str]:
    """
    Convert raw belief tensors (confidence, tensions, etc.) to narrative descriptors.
    Thresholds: 0–0.3 low, 0.3–0.6 moderate, 0.6–0.8 high, 0.8+ dominant.
    Add directional phrasing: strengthened, softened, shifted into high territory.
    """
    lines: list[str] = []
    if not isinstance(beliefs, dict):
        return lines

    confidence = beliefs.get("confidence") or {}
    variables = beliefs.get("variables") or {}
    if not isinstance(confidence, dict):
        confidence = {}
    if not isinstance(variables, dict):
        variables = {}

    # Aggregate confidence if it's per-variable
    if confidence:
        avg_conf = sum(float(v) for v in confidence.values() if isinstance(v, (int, float))) / max(
            1, len([v for v in confidence.values() if isinstance(v, (int, float))])
        )
    else:
        avg_conf = 0.5

    # Tensions: infer from variables like dissatisfaction, or use a tensions key
    tensions_val = 0.0
    if "tensions" in beliefs and isinstance(beliefs["tensions"], (int, float)):
        tensions_val = float(beliefs["tensions"])
    elif "dissatisfaction" in variables:
        tensions_val = float(variables.get("dissatisfaction", 0)) / 100.0
    elif "dissatisfaction" in confidence:
        tensions_val = float(confidence.get("dissatisfaction", 0))

    prev_conf = 0.5
    prev_tensions = 0.5
    if prev_beliefs and isinstance(prev_beliefs, dict):
        pc = prev_beliefs.get("confidence") or {}
        if isinstance(pc, dict) and pc:
            prev_conf = sum(float(v) for v in pc.values() if isinstance(v, (int, float))) / max(
                1, len([v for v in pc.values() if isinstance(v, (int, float))])
            )
        prev_tensions = float(prev_beliefs.get("tensions", 0.5))

    conf_label = _threshold_label(avg_conf)
    tensions_label = _threshold_label(tensions_val)

    # Directional phrasing
    conf_dir = ""
    if avg_conf > prev_conf + 0.05:
        conf_dir = " strengthened"
    elif avg_conf < prev_conf - 0.05:
        conf_dir = " softened"
    elif conf_label != _threshold_label(prev_conf):
        conf_dir = f" shifted into {conf_label} territory"

    tensions_dir = ""
    if tensions_val > prev_tensions + 0.05:
        tensions_dir = " rose"
    elif tensions_val < prev_tensions - 0.05:
        tensions_dir = " eased"

    if conf_label == "moderate" and tensions_label == "low":
        lines.append(
            f"Confidence remained{conf_dir or ' moderate'}, while tensions stayed{tensions_dir or ' low'}, "
            "indicating internal alignment."
        )
    else:
        parts = [f"Confidence was {conf_label}{conf_dir}"]
        if tensions_val > 0.01:
            parts.append(f"tensions {tensions_label}{tensions_dir}")
        lines.append(". ".join(parts) + ".")

    return lines


# ---------------------------------------------------------------------------
# Part 7 — Structured Summary Synthesis
# ---------------------------------------------------------------------------


def build_structured_narrative_summary(
    trace: list[dict[str, Any]],
    final_snapshot: dict[str, Any],
    agents: list[dict[str, Any]],
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Produce the full structured summary with all components.
    """
    phases = extract_structural_phases(trace, final_snapshot)
    turning_point = detect_turning_point(trace, phases)
    diminishing_returns = detect_diminishing_returns(trace, phases)
    pattern = classify_pattern(trace, final_snapshot, phases, turning_point, diminishing_returns)
    name_to_display = infer_agent_display_names(agents, trace, final_snapshot, scenario)

    initial = phases.get("opening_conditions") or {}
    variables = final_snapshot.get("variables") or final_snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}

    # Build causal cascade from causal_edges (trace) or causal_links (final_snapshot)
    causal_cascade: list[str] = []
    for entry in trace:
        for edge in entry.get("causal_edges") or []:
            action = edge.get("from_action", "?")
            var = edge.get("variable", "?")
            delta = edge.get("delta", 0)
            agent = edge.get("agent", "?")
            causal_cascade.append(f"{agent} {action} → {var} ({delta:+.1f})")
    if not causal_cascade:
        for edge in final_snapshot.get("causal_links") or []:
            action = edge.get("from_action", "?")
            var = edge.get("variable", "?")
            delta = edge.get("delta", 0)
            agent = edge.get("agent", "?")
            causal_cascade.append(f"{agent} {action} → {var} ({delta:+.1f})")
    causal_cascade = causal_cascade[:10]  # Limit for readability

    # Hidden tradeoffs: variables that moved in opposite directions
    var_totals: dict[str, float] = {}
    for entry in trace:
        for vc in entry.get("variable_changes") or []:
            var = vc.get("var")
            delta = vc.get("delta", 0)
            if var:
                var_totals[var] = var_totals.get(var, 0) + float(delta)

    ups = [v for v, d in var_totals.items() if d > 0.5]
    downs = [v for v, d in var_totals.items() if d < -0.5]
    hidden_tradeoffs = []
    if ups and downs:
        hidden_tradeoffs.append(f"Although {_humanize_var(ups[0])} improved, {_humanize_var(downs[0])} remained elevated.")

    # Format prose sections
    opening_phrase = _phrase_opening_conditions(initial, variables)
    dominant_strategy = phases.get("dominant_strategy_cluster") or "mixed actions"
    dominant_phrase = f"The dominant strategy centered on {_humanize_var(dominant_strategy.replace('_', ' '))}."
    turning_turn = turning_point.get("turn_index", 0) + 1
    turning_var = turning_point.get("dominant_variable_shift", "state")
    reason = turning_point.get("reason_tag", "max_delta")
    if reason and (reason == "max_delta" or str(reason).startswith("max_delta:")):
        reason = "largest aggregate change"
    turning_phrase = (
        f"Turn {turning_turn} marked the decisive shift as {_humanize_var(turning_var)} "
        f"produced the largest change ({reason})."
    )
    tradeoff_phrase = hidden_tradeoffs[0] if hidden_tradeoffs else "Variable movements produced interdependent effects."
    pattern_phrase = f"The run fits an {pattern} pattern."

    return {
        "opening_conditions": opening_phrase,
        "dominant_strategic_moves": dominant_phrase,
        "causal_cascade": causal_cascade,
        "turning_point_turn": turning_turn,
        "turning_point_phrase": turning_phrase,
        "hidden_tradeoffs": tradeoff_phrase,
        "behavioral_pattern": pattern,
        "behavioral_pattern_phrase": pattern_phrase,
        "diminishing_returns": diminishing_returns,
        "phases": phases,
        "turning_point": turning_point,
        "name_to_display": name_to_display,
    }


def _humanize_var(name: str) -> str:
    return str(name).replace("_", " ").strip()


def _delta_magnitude_phrase_fa(delta: float, turn_deltas: list[float] | None = None) -> str:
    """Return Persian phrase for delta magnitude: افزایش/کاهش جزئی or محسوس."""
    abs_d = abs(delta)
    if turn_deltas and len(turn_deltas) >= 2:
        mean_d = sum(abs(x) for x in turn_deltas) / len(turn_deltas)
        if mean_d > 1e-9 and abs_d >= mean_d * 0.5:
            magnitude = "محسوس"
        else:
            magnitude = "جزئی"
    else:
        magnitude = "محسوس" if abs_d >= 1.0 else "جزئی"
    if delta > 0:
        return f"افزایش {magnitude}"
    if delta < 0:
        return f"کاهش {magnitude}"
    return "بدون تغییر"


def _delta_magnitude_phrase_en(delta: float, turn_deltas: list[float] | None = None) -> str:
    """Return English phrase for delta magnitude: slight/substantial increase or decrease."""
    abs_d = abs(delta)
    if turn_deltas and len(turn_deltas) >= 2:
        mean_d = sum(abs(x) for x in turn_deltas) / len(turn_deltas)
        if mean_d > 1e-9 and abs_d >= mean_d * 0.5:
            magnitude = "substantial"
        else:
            magnitude = "slight"
    else:
        magnitude = "substantial" if abs_d >= 1.0 else "slight"
    if delta > 0:
        return f"{magnitude} increase"
    if delta < 0:
        return f"{magnitude} decrease"
    return "no change"


def _phrase_opening_conditions(initial: dict[str, float], final: dict[str, Any]) -> str:
    """Generate opening conditions phrase from initial state."""
    if not initial:
        return "The simulation opened with key variables in play."
    parts = []
    for k, v in list(initial.items())[:3]:
        if isinstance(v, (int, float)):
            if v >= 60:
                level = "abundant"
            elif v >= 30:
                level = "moderate"
            else:
                level = "low"
            parts.append(f"{_humanize_var(k)} at {level} levels")
    if not parts:
        return "The simulation opened with key variables in flux."
    return "The simulation opened with " + ", ".join(parts) + "."


def format_structured_summary_prose(
    summary: dict[str, Any],
    lang: str = "auto",
    allow_numbers: bool = False,
) -> str:
    """
    Format the structured summary into prose. Language is NOT hardcoded: use lang='fa' or 'en'
    (caller should set lang from scenario, e.g. _lang_from_scenario). When lang is 'auto',
    default to 'en'. Both fa and en use the same two-paragraph narrative arc: Paragraph 1
    beginning (در آغاز / At the beginning) + setting; Paragraph 2 turning points, tradeoffs,
    outcome. Deltas rendered qualitatively unless allow_numbers=True.
    """
    # Do not hardcode Persian: "auto" -> en when unresolved (caller should pass resolved lang)
    resolved = "en" if lang == "auto" else lang
    turn_deltas = (summary.get("phases") or {}).get("turn_deltas") or []

    if resolved == "fa":
        return _format_prose_fa(summary, allow_numbers=allow_numbers, turn_deltas=turn_deltas)
    return _format_prose_en(summary, allow_numbers=allow_numbers, turn_deltas=turn_deltas)


def _format_prose_en(
    summary: dict[str, Any],
    *,
    allow_numbers: bool = False,
    turn_deltas: list[float] | None = None,
) -> str:
    """Two-paragraph English narrative: same structure as fa. At the beginning ... As a result."""
    turn_deltas = turn_deltas or []
    opening = summary.get("opening_conditions", "")
    dominant = summary.get("dominant_strategic_moves", "")
    turning_phrase = summary.get("turning_point_phrase", "")
    tradeoffs = summary.get("hidden_tradeoffs", "")
    pattern = summary.get("behavioral_pattern", "")

    if not allow_numbers:
        opening = _strip_digits(opening, False)
        dominant = _strip_digits(dominant, False)
        turning_phrase = _strip_digits(turning_phrase, False)
        tradeoffs = _strip_digits(tradeoffs, False)

    # Qualitative causal cascade: replace (+N) with "slight/substantial increase/decrease"
    cascade_raw = summary.get("causal_cascade", [])[:5]
    cascade_en: list[str] = []
    for s in cascade_raw:
        m = re.search(r"\(([+-]?\d+\.?\d*)\)", s)
        if m and not allow_numbers:
            delta = float(m.group(1))
            phrase = _delta_magnitude_phrase_en(delta, turn_deltas)
            s = re.sub(r"\s*\([+-]?\d+\.?\d*\)", f" ({phrase})", s)
        cascade_en.append(s)

    # Paragraph 1: At the beginning + initial situation + dominant strategy
    p1_parts = ["At the beginning, the initial situation was shaped by key variables."]
    if dominant:
        cent = _strip_digits(
            dominant.replace("The dominant strategy centered on ", "").replace(".", "").strip(),
            allow_numbers,
        )
        if cent:
            p1_parts.append(f"The dominant strategy centered on {cent}.")
    para1 = " ".join(p for p in p1_parts if p).strip()
    if not allow_numbers:
        para1 = _strip_digits(para1, False)

    # Paragraph 2: turning point(s), tradeoffs, outcome (no "Causal chain:" or banned artifacts)
    p2_parts = []
    if turning_phrase:
        t = turning_phrase
        if not allow_numbers:
            t = re.sub(r"Turn\s+\d+", "the turning point", t, flags=re.IGNORECASE)
            t = _strip_digits(t, False)
        p2_parts.append("As a result, " + t)
    if tradeoffs:
        p2_parts.append("This led to " + tradeoffs)
    if cascade_en:
        p2_parts.append("Cause and effect: " + "; ".join(cascade_en[:3]))
    if pattern:
        p2_parts.append(f"The run fits a {pattern} pattern.")
    para2 = " ".join(p for p in p2_parts if p).strip()
    if not allow_numbers:
        para2 = _strip_digits(para2, False)

    if not para1:
        para1 = "At the beginning, the scenario started from its initial state."
    if not para2:
        para2 = "In the course of the run, changes and final outcomes took shape."

    return (para1 + "\n\n" + para2).strip()


def _format_prose_fa(
    summary: dict[str, Any],
    *,
    allow_numbers: bool = False,
    turn_deltas: list[float] | None = None,
) -> str:
    """Two-paragraph Persian narrative: در آغاز ... سپس / در نتیجه."""
    turn_deltas = turn_deltas or []
    opening = summary.get("opening_conditions", "")
    dominant = summary.get("dominant_strategic_moves", "")
    turning_phrase = summary.get("turning_point_phrase", "")
    tradeoffs = summary.get("hidden_tradeoffs", "")
    pattern = summary.get("behavioral_pattern", "")
    pattern_phrase = summary.get("behavioral_pattern_phrase", "")

    if not allow_numbers:
        opening = _strip_digits(opening, False)
        dominant = _strip_digits(dominant, False)
        turning_phrase = _strip_digits(turning_phrase, False)
        tradeoffs = _strip_digits(tradeoffs, False)
        pattern_phrase = _strip_digits(pattern_phrase, False)

    # Qualitative causal cascade: replace (+\d) with افزایش جزئی/محسوس
    cascade_raw = summary.get("causal_cascade", [])[:5]
    cascade_fa: list[str] = []
    for s in cascade_raw:
        m = re.search(r"\(([+-]?\d+\.?\d*)\)", s)
        if m and not allow_numbers:
            delta = float(m.group(1))
            phrase = _delta_magnitude_phrase_fa(delta, turn_deltas)
            s = re.sub(r"\s*\([+-]?\d+\.?\d*\)", f" ({phrase})", s)
        cascade_fa.append(s)

    # Paragraph 1: در آغاز + initial situation + dominant strategy (plain Persian)
    p1_parts = ["در آغاز، وضعیت اولیه با متغیرهای کلیدی شکل گرفت."]
    if dominant:
        # Extract action/variable from "The dominant strategy centered on X."
        cent = _strip_digits(dominant.replace("The dominant strategy centered on ", "").replace(".", "").strip(), allow_numbers)
        if cent:
            p1_parts.append(f"استراتژی غالب حول {cent} بود.")
    para1 = " ".join(p for p in p1_parts if p).strip()
    if not allow_numbers:
        para1 = _strip_digits(para1, False)

    # Paragraph 2: turning point(s), tradeoffs, outcome, pattern (cause/effect connectors)
    p2_parts = []
    if turning_phrase:
        t = turning_phrase
        if not allow_numbers:
            t = re.sub(r"Turn\s+\d+", "نوبت", t)
            t = t.replace(" marked the decisive shift", " نقطه تعیین‌کننده بود").replace(" produced the largest change", " بیشترین تغییر را ایجاد کرد")
            t = _strip_digits(t, False)
        p2_parts.append("در نتیجه، " + t)
    if tradeoffs:
        p2_parts.append("همین باعث شد که " + tradeoffs)
    if cascade_fa:
        p2_parts.append("علت و اثر: " + "؛ ".join(cascade_fa[:3]))
    pattern_fa = PATTERN_LABELS_FA.get(pattern, "")
    if pattern_fa:
        p2_parts.append(f"الگوی رفتاری: {pattern_fa}.")
    para2 = " ".join(p for p in p2_parts if p).strip()
    if not allow_numbers:
        para2 = _strip_digits(para2, False)

    if not para1:
        para1 = "در آغاز، سناریو با وضعیت اولیه آغاز شد."
    if not para2:
        para2 = "در ادامه، تغییرات و نتایج نهایی رخ داد."

    return (para1 + "\n\n" + para2).strip()
