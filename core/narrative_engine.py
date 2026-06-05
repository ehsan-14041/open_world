"""
Narrative Engine: domain-agnostic turn-by-turn narrative and attribution.
Produces turn summary, actor performance, causal chains, outcome classification,
regime commentary, and confidence notes from delta, causal trace, goals, and calibration.
No hardcoded variable names or scenario-specific logic.
"""

from __future__ import annotations

import math
from typing import Any

from core.legacy_semantics import legacy_goal_to_var_direction
from core.narrative_model import NarrativeFact, NarrativeTag, TurnNarrativeInputs

# Outcome classification thresholds (configurable; no scenario semantics)
OUTCOME_POSITIVE_THRESHOLD = 2.0
OUTCOME_SMALL_POSITIVE = 0.5
OUTCOME_NEAR_ZERO_BAND = 0.3
CRISIS_ESCALATION_NET_THRESHOLD = -3.0


def _norm_lang(lang: str | None) -> str:
    """Normalize to 'fa' or 'en' (default en)."""
    return "fa" if str(lang or "").strip().lower().startswith("fa") else "en"


def _L(lang: str, en: str, fa: str) -> str:
    """Pick a localized string. Default behavior (lang='en') preserves prior output."""
    return fa if _norm_lang(lang) == "fa" else en


# Canonical (English) outcome labels are kept stable for tags/logic; this maps
# them to a Persian display label when rendering for a Persian audience.
_OUTCOME_FA = {
    "Crisis Escalation": "تشدید بحران",
    "Strategic Success": "موفقیت راهبردی",
    "Tactical Gain": "دستاورد تاکتیکی",
    "Mixed Outcome": "نتیجه‌ی مختلط",
    "Strategic Deterioration": "وخامت راهبردی",
}


def outcome_label_display(outcome: str, lang: str = "en") -> str:
    """Localized display label for a canonical outcome string."""
    if _norm_lang(lang) == "fa":
        return _OUTCOME_FA.get(str(outcome), str(outcome))
    return str(outcome)


def _humanize_var(var: str) -> str:
    """Variable-agnostic label from id."""
    return (var or "").replace("_", " ").strip() or "variable"


def _get_goal_vars_and_direction_for_agent(agent_goals: dict[str, Any]) -> list[tuple[str, int]]:
    """From agent goals (objectives + long_term_goals) return list of (var, direction)."""
    result: list[tuple[str, int]] = []
    objectives = agent_goals.get("objectives") or {}
    if isinstance(objectives, dict):
        for key in objectives:
            mapped = legacy_goal_to_var_direction(key)
            if mapped and objectives.get(key, 0) != 0:
                result.append(mapped)
    for g in agent_goals.get("long_term_goals") or []:
        if not g or not isinstance(g, str):
            continue
        mapped = legacy_goal_to_var_direction(g)
        if mapped and mapped not in result:
            result.append(mapped)
    return result


def _get_risk_variables(scenario: dict[str, Any]) -> set[str]:
    """Derive risk-related variable names from governance and causal_links."""
    risk: set[str] = set()
    gov = (scenario or {}).get("governance") or {}
    if isinstance(gov, dict):
        for key in ("stability_variable", "dissatisfaction_variable"):
            v = gov.get(key)
            if isinstance(v, str) and v:
                risk.add(v)
    causal_links = (scenario or {}).get("causal_links") or []
    if not risk and causal_links:
        return risk
    for link in causal_links:
        if not isinstance(link, dict):
            continue
        to_var = link.get("to")
        from_var = link.get("from")
        if to_var in risk and from_var:
            risk.add(from_var)
    return risk


def get_regime_commentary(regime: str, lang: str = "en") -> str:
    """Regime-driven single string; no variable or domain names."""
    r = (regime or "").strip().upper()
    if r == "CRISIS":
        return _L(
            lang,
            "The system is operating under high saturation pressure. "
            "Marginal interventions may have reduced impact and higher unintended consequences.",
            "سامانه زیر فشار اشباعِ بالا کار می‌کند. مداخله‌های جزئی ممکن است اثر کمتر و "
            "پیامدهای ناخواسته‌ی بیشتری داشته باشند.",
        )
    if r == "FRAGILE":
        return _L(lang, "The system shows early structural strain.", "سامانه نشانه‌های اولیه‌ی فشار ساختاری را نشان می‌دهد.")
    return _L(lang, "System dynamics remain elastic.", "دینامیکِ سامانه همچنان کشسان است.")


def get_confidence_adjustment_note(calibration_data: dict[str, Any] | None, lang: str = "en") -> str:
    """Confidence–calibration narrative note from calibration_data."""
    _low = _L(
        lang,
        "Predictive reliability remains low, suggesting model assumptions may require recalibration.",
        "اعتمادپذیریِ پیش‌بینی پایین است؛ احتمالاً مفروضاتِ مدل به بازکالیبراسیون نیاز دارند.",
    )
    _strong = _L(lang, "Predictive alignment is strengthening.", "هم‌ترازیِ پیش‌بینی در حال تقویت است.")
    if not calibration_data or not isinstance(calibration_data, dict):
        return ""
    health = calibration_data.get("health")
    agg = calibration_data.get("calibration_score_agg")
    if agg is None and isinstance(calibration_data.get("per_agent_calibration"), dict):
        scores = [
            v.get("calibration_score") if isinstance(v, dict) else v
            for v in calibration_data["per_agent_calibration"].values()
        ]
        scores = [s for s in scores if isinstance(s, (int, float))]
        agg = sum(scores) / len(scores) if scores else 0.5
    if isinstance(agg, (int, float)) and float(agg) < 0.2:
        return _low
    if health == "red" and (agg is None or (isinstance(agg, (int, float)) and float(agg) < 0.4)):
        return _low
    rmse_over_time = calibration_data.get("rmse_over_time") or []
    if len(rmse_over_time) >= 2 and isinstance(rmse_over_time[-1], (int, float)) and isinstance(rmse_over_time[-2], (int, float)):
        if float(rmse_over_time[-1]) < float(rmse_over_time[-2]):
            return _strong
    return ""


def _build_decision_framing(decision_input: dict[str, Any] | None, lang: str = "en") -> str:
    """Build a short framing block when analyzing a structured decision."""
    if not decision_input or not isinstance(decision_input, dict):
        return ""
    move = (decision_input.get("move") or "").strip()
    if not move:
        return ""
    actors = [str(a).strip() for a in (decision_input.get("actors") or []) if str(a).strip()]
    horizon = decision_input.get("horizon_months")
    if lang == "fa":
        parts = [f"تصمیم مورد تحلیل: {move}."]
        if actors:
            parts.append(f"بازیگران: {', '.join(actors)}.")
        if isinstance(horizon, int) and horizon > 0:
            parts.append(f"افق: {horizon} ماه.")
        parts.append(
            "در شناسایی محرک‌ها و هزینه‌های پنهان، موارد با بیشترین ارتباط علّی با این تصمیم اولویت دارند."
        )
    else:
        parts = [f"The user is analyzing this decision: {move}."]
        if actors:
            parts.append(f"Actors of interest: {', '.join(actors)}.")
        if isinstance(horizon, int) and horizon > 0:
            parts.append(f"Horizon: {horizon} months.")
        parts.append(
            "When listing drivers and hidden costs, prioritize those most causally connected to this move."
        )
    return " ".join(parts)


def _build_turn_summary(
    delta: dict[str, float],
    regime: str,
    calibration_data: dict[str, Any] | None,
    actor_analysis: list[dict[str, Any]],
    outcome_assessment: dict[str, Any],
    scenario: dict[str, Any],
    self_effect_per_agent: dict[str, dict[str, float]],
    risk_vars: set[str],
    direction_label: str,
    lang: str = "en",
) -> str:
    """Algorithmically build 5–7 sentence turn summary."""
    sentences: list[str] = []
    if not delta:
        sentences.append(_L(lang, "No variable changes this turn.", "در این نوبت تغییری در متغیرها رخ نداد."))
    else:
        top3 = sorted(
            [(v, d) for v, d in delta.items() if isinstance(d, (int, float)) and abs(float(d)) > 1e-9],
            key=lambda x: abs(x[1]),
            reverse=True,
        )[:3]
        if top3:
            parts = [f"{_humanize_var(v)} ({d:+.1f})" for v, d in top3]
            sentences.append(_L(lang, "Largest changes: ", "بزرگ‌ترین تغییرها: ") + ", ".join(parts) + ".")
        primary_actors = [a.get("actor") for a in (actor_analysis or [])[:3] if a.get("actor")]
        if primary_actors:
            sentences.append(_L(lang, "Primary contributing actors: ", "بازیگرانِ اصلیِ مؤثر: ") + ", ".join(primary_actors) + ".")
        dir_disp = {
            "Stabilizing": _L(lang, "Stabilizing", "تثبیت‌کننده"),
            "Escalatory": _L(lang, "Escalatory", "تشدیدکننده"),
            "Mixed": _L(lang, "Mixed", "مختلط"),
        }.get(direction_label, direction_label)
        sentences.append(_L(lang, "Overall direction: ", "جهتِ کلی: ") + dir_disp + ".")
    sentences.append(get_regime_commentary(regime, lang))
    risk_delta_sum = sum(
        float(delta.get(v, 0)) for v in risk_vars if isinstance(delta.get(v), (int, float))
    )
    if risk_vars and abs(risk_delta_sum) > 1e-6:
        if risk_delta_sum > 0:
            sentences.append(_L(lang, "Risk-related variables increased, raising systemic risk.", "متغیرهای مرتبط با ریسک افزایش یافتند و ریسکِ سامانه‌ای را بالا بردند."))
        else:
            sentences.append(_L(lang, "Risk-related variables decreased, reducing systemic pressure.", "متغیرهای مرتبط با ریسک کاهش یافتند و فشارِ سامانه‌ای را کم کردند."))
    outcome_label = (outcome_assessment or {}).get("outcome") or "Mixed Outcome"
    sentences.append(_L(lang, "Outcome classification: ", "طبقه‌بندیِ نتیجه: ") + outcome_label_display(outcome_label, lang) + ".")
    note = get_confidence_adjustment_note(calibration_data, lang)
    if note:
        sentences.append(note)
    return " ".join(sentences)


def compute_actor_performance(
    delta_applied: dict[str, float],
    self_effect_per_agent: dict[str, dict[str, float]],
    goals_per_agent: dict[str, dict[str, Any]],
    scenario: dict[str, Any],
    calibration_data: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Per-actor: goal alignment, net impact, escalation score, calibration, influence.
    Classification: Stabilizer / Escalator / Mixed / Ineffective.
    Returns ranked list (by goal alignment then net impact).
    """
    risk_vars = _get_risk_variables(scenario or {})
    variable_specs = (scenario or {}).get("variable_specs") or {}
    per_agent_cal = (calibration_data or {}).get("per_agent_calibration") or {}
    if not isinstance(per_agent_cal, dict):
        per_agent_cal = {}

    results: list[dict[str, Any]] = []
    for agent_id, self_effect in (self_effect_per_agent or {}).items():
        if not isinstance(self_effect, dict):
            continue
        goals = (goals_per_agent or {}).get(agent_id) or {}
        goal_var_dir = _get_goal_vars_and_direction_for_agent(goals)

        goal_alignment = 0.0
        for var, direction in goal_var_dir:
            d = self_effect.get(var)
            if isinstance(d, (int, float)):
                goal_alignment += float(d) * direction

        escalation_score = 0.0
        for var in risk_vars:
            d = self_effect.get(var)
            if isinstance(d, (int, float)) and float(d) > 0:
                escalation_score += float(d)

        net_system_impact = sum(
            float(v) for v in self_effect.values() if isinstance(v, (int, float))
        )
        influence_magnitude = sum(
            abs(float(v)) for v in self_effect.values() if isinstance(v, (int, float))
        )
        cal_row = per_agent_cal.get(agent_id) if isinstance(per_agent_cal.get(agent_id), dict) else {}
        calibration_accuracy = float(cal_row.get("calibration_score", 0.5))
        if "rolling_mse" in cal_row and isinstance(cal_row.get("rolling_mse"), (int, float)):
            mse = float(cal_row["rolling_mse"])
            calibration_accuracy = 1.0 / (1.0 + mse) if mse >= 0 else 0.5

        if goal_alignment > 0.5 and escalation_score < 0.3:
            role = "Stabilizer"
        elif goal_alignment < -0.5 or escalation_score > 0.5:
            role = "Escalator"
        elif abs(goal_alignment) <= 0.5 and abs(escalation_score) <= 0.5 and influence_magnitude < 1e-6:
            role = "Ineffective"
        else:
            role = "Mixed"

        results.append({
            "actor": agent_id,
            "goal_alignment_score": round(goal_alignment, 4),
            "net_system_impact": round(net_system_impact, 4),
            "escalation_score": round(escalation_score, 4),
            "calibration_accuracy": round(calibration_accuracy, 4),
            "influence_magnitude": round(influence_magnitude, 4),
            "role": role,
        })

    results.sort(
        key=lambda x: (x["goal_alignment_score"], x["net_system_impact"]),
        reverse=True,
    )
    return results


def build_causal_chain_story(
    chosen_actions: list[dict[str, Any]],
    self_effect_per_agent: dict[str, dict[str, float]],
    propagation_trace: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    For each primary action build chain: Action -> direct var changes -> propagated -> system impact.
    Returns list of { "actor": str, "action": str, "chain": [ (var, delta), ... ] } ordered by strength.
    """
    chains: list[dict[str, Any]] = []
    agent_to_action: dict[str, str] = {}
    for c in chosen_actions or []:
        if not isinstance(c, dict):
            continue
        ag = c.get("agent") or c.get("agent_id") or ""
        act = c.get("action_id") or c.get("action") or "action"
        if ag:
            agent_to_action[ag] = act

    for agent_id, self_effect in (self_effect_per_agent or {}).items():
        if not isinstance(self_effect, dict):
            continue
        action_id = agent_to_action.get(agent_id) or "action"
        direct = [(v, float(d)) for v, d in self_effect.items() if isinstance(d, (int, float)) and abs(float(d)) > 1e-9]
        seen_vars: set[str] = set()
        chain: list[tuple[str, float]] = []
        for v, d in sorted(direct, key=lambda x: -abs(x[1])):
            if v not in seen_vars:
                chain.append((v, d))
                seen_vars.add(v)
        for hop in (1, 2, 3):
            for e in propagation_trace or []:
                if not isinstance(e, dict):
                    continue
                if e.get("hop") != hop:
                    continue
                from_var = e.get("from")
                to_var = e.get("to")
                contrib = e.get("delta_contrib")
                if not to_var or contrib is None:
                    continue
                try:
                    dc = float(contrib)
                except (TypeError, ValueError):
                    continue
                if abs(dc) < 1e-9:
                    continue
                if to_var not in seen_vars:
                    chain.append((to_var, dc))
                    seen_vars.add(to_var)
        strength = sum(abs(d) for _, d in chain)
        chains.append({
            "actor": agent_id,
            "action": action_id,
            "chain": chain,
            "strength": round(strength, 4),
        })
    chains.sort(key=lambda x: -(x.get("strength") or 0))
    return [{"actor": c["actor"], "action": c["action"], "chain": c["chain"]} for c in chains]


def classify_outcome(
    delta: dict[str, float],
    goals_aggregate: list[tuple[str, int]],
    scenario: dict[str, Any],
    regime: str,
    lang: str = "en",
) -> dict[str, Any]:
    """
    net_progress = weighted(goal_improvements) - weighted(risk_increase).
    Returns outcome label, explanation, hidden_tradeoffs.

    The canonical `outcome` label stays English (used by tags/logic); narrative
    text and hidden_tradeoffs are localized via `lang`.
    """
    risk_vars = _get_risk_variables(scenario or {})
    goal_improvement = 0.0
    for var, direction in goals_aggregate or []:
        d = delta.get(var)
        if isinstance(d, (int, float)):
            goal_improvement += float(d) * direction
    risk_increase = sum(
        float(delta.get(v, 0)) for v in risk_vars
        if isinstance(delta.get(v), (int, float)) and float(delta.get(v, 0)) > 0
    )
    net_progress = goal_improvement - risk_increase

    hidden_tradeoffs: list[str] = []
    for v in risk_vars:
        d = delta.get(v)
        if isinstance(d, (int, float)) and float(d) > 0:
            hidden_tradeoffs.append(_humanize_var(v) + _L(lang, " increased", " افزایش یافت"))
    for var, direction in goals_aggregate or []:
        d = delta.get(var)
        if isinstance(d, (int, float)) and float(d) * direction < 0:
            hidden_tradeoffs.append(_humanize_var(var) + _L(lang, " moved against goals", " خلافِ اهداف حرکت کرد"))

    r = (regime or "").strip().upper()
    if r == "CRISIS" and net_progress < CRISIS_ESCALATION_NET_THRESHOLD:
        outcome = "Crisis Escalation"
        explanation = "Net progress strongly negative under crisis regime; risk increased and goal alignment declined."
    elif net_progress > OUTCOME_POSITIVE_THRESHOLD:
        outcome = "Strategic Success"
        explanation = "Substantial goal improvement with limited risk increase."
    elif net_progress > OUTCOME_SMALL_POSITIVE:
        outcome = "Tactical Gain"
        explanation = "Modest positive net progress."
    elif abs(net_progress) <= OUTCOME_NEAR_ZERO_BAND:
        outcome = "Mixed Outcome"
        explanation = "Goal and risk movements roughly balanced."
    else:
        outcome = "Strategic Deterioration"
        explanation = "Risk increase and goal deterioration dominated."

    return {
        "outcome": outcome,
        "explanation": explanation,
        "hidden_tradeoffs": hidden_tradeoffs,
        "net_progress": round(net_progress, 4),
    }


def generate_turn_narrative(
    previous_state: dict[str, Any],
    current_state: dict[str, Any],
    delta: dict[str, float],
    causal_trace: list[dict[str, Any]],
    regime: str,
    calibration_data: dict[str, Any] | None,
    agent_actions: list[dict[str, Any]],
    goals_per_agent: dict[str, dict[str, Any]],
    scenario: dict[str, Any],
    *,
    self_effect_per_agent: dict[str, dict[str, float]] | None = None,
    propagation_trace: list[dict[str, Any]] | None = None,
    delta_applied: dict[str, float] | None = None,
    lang: str = "en",
    decision_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Main entry: produce structured narrative from turn data.

    Returns a dict with:
    - turn_summary, actor_analysis, causal_chain, outcome_assessment,
      regime_commentary, key_drivers, hidden_costs, confidence_adjustment_note
      (backwards compatible fields).
    - facts, tags, inputs: canonical fact/tag representation for renderers.
    """
    scenario = scenario or {}
    delta = delta or {}
    delta_use = delta_applied if delta_applied is not None else delta
    self_effect = self_effect_per_agent or {}
    prop_trace = propagation_trace if propagation_trace is not None else causal_trace or []

    risk_vars = _get_risk_variables(scenario)
    goals_aggregate: list[tuple[str, int]] = []
    for ag_goals in (goals_per_agent or {}).values():
        if isinstance(ag_goals, dict):
            goals_aggregate.extend(_get_goal_vars_and_direction_for_agent(ag_goals))
    seen = set()
    unique_goals: list[tuple[str, int]] = []
    for v, d in goals_aggregate:
        if (v, d) not in seen:
            seen.add((v, d))
            unique_goals.append((v, d))

    outcome_assessment = classify_outcome(delta_use, unique_goals, scenario, regime, lang)
    actor_analysis = compute_actor_performance(
        delta_use,
        self_effect,
        goals_per_agent or {},
        scenario,
        calibration_data,
    )

    goal_improvement = 0.0
    for var, direction in unique_goals:
        d = delta_use.get(var)
        if isinstance(d, (int, float)):
            goal_improvement += float(d) * direction
    risk_inc = sum(
        float(delta_use.get(v, 0)) for v in risk_vars
        if isinstance(delta_use.get(v), (int, float)) and float(delta_use.get(v, 0)) > 0
    )
    if goal_improvement > 0.5 and risk_inc < 0.3:
        direction_label = "Stabilizing"
    elif goal_improvement < -0.5 or risk_inc > 0.5:
        direction_label = "Escalatory"
    else:
        direction_label = "Mixed"

    turn_summary = _build_turn_summary(
        delta_use,
        regime,
        calibration_data,
        actor_analysis,
        outcome_assessment,
        scenario,
        self_effect,
        risk_vars,
        direction_label,
        lang,
    )

    decision_framing = _build_decision_framing(decision_input, lang)
    if decision_framing:
        turn_summary = decision_framing + " " + turn_summary

    causal_chain = build_causal_chain_story(
        agent_actions or [],
        self_effect,
        prop_trace,
    )

    # Build key_drivers ranked by |delta|, boosted for variables related to the decision move.
    _move_keywords: set[str] = set()
    if decision_input and isinstance(decision_input, dict):
        move_text = (decision_input.get("move") or "").lower()
        _move_keywords = {w for w in move_text.split() if len(w) > 3}
        for actor in (decision_input.get("actors") or []):
            _move_keywords.update(w for w in str(actor).lower().split() if len(w) > 3)

    def _driver_score(var: str, d_val: float) -> float:
        base = abs(float(d_val))
        if _move_keywords:
            v_lower = var.lower()
            base += sum(0.5 for kw in _move_keywords if kw in v_lower)
        return base

    key_drivers: list[str] = []
    for var, d in sorted(
        [(v, delta_use.get(v)) for v in delta_use if isinstance(delta_use.get(v), (int, float)) and abs(float(delta_use.get(v))) > 1e-9],
        key=lambda x: -_driver_score(x[0], x[1]),
    )[:5]:
        key_drivers.append(f"{_humanize_var(var)}: {float(d):+.1f}")

    hidden_costs = outcome_assessment.get("hidden_tradeoffs") or []

    confidence_note = get_confidence_adjustment_note(calibration_data, lang)

    # Facts: compact, structured statements derived from the above quantities.
    facts: list[NarrativeFact] = []
    facts.append(
        NarrativeFact(
            kind="delta_summary",
            data={"delta": dict(delta_use)},
        )
    )
    facts.append(
        NarrativeFact(
            kind="outcome",
            data=dict(outcome_assessment),
        )
    )
    facts.append(
        NarrativeFact(
            kind="regime",
            data={"regime": regime, "commentary": get_regime_commentary(regime, lang)},
        )
    )
    if self_effect:
        facts.append(
            NarrativeFact(
                kind="self_effect_per_agent",
                data=self_effect,
            )
        )
    if actor_analysis:
        facts.append(
            NarrativeFact(
                kind="actor_analysis",
                data={"actors": actor_analysis},
            )
        )
    if causal_chain:
        facts.append(
            NarrativeFact(
                kind="causal_chain",
                data={"chains": causal_chain},
            )
        )
    if key_drivers:
        facts.append(
            NarrativeFact(
                kind="key_drivers",
                data={"drivers": key_drivers},
            )
        )

    # Tags: abstract labels for interpretation.
    tags: list[NarrativeTag] = []
    tags.append(NarrativeTag(kind="direction", value=direction_label))
    tags.append(
        NarrativeTag(
            kind="outcome_label",
            value=str(outcome_assessment.get("outcome", "Mixed Outcome")),
        )
    )
    if isinstance(regime, str):
        tags.append(NarrativeTag(kind="regime", value=regime))
    for a in actor_analysis:
        actor_id = str(a.get("actor", ""))
        role = str(a.get("role", ""))
        if actor_id and role:
            tags.append(
                NarrativeTag(
                    kind="actor_role",
                    value=f"{actor_id}:{role}",
                    weight=float(a.get("influence_magnitude", 0.0)) if isinstance(a.get("influence_magnitude"), (int, float)) else None,
                )
            )

    inputs = TurnNarrativeInputs(
        turn=None,
        facts=facts,
        tags=tags,
        metadata={
            "has_delta": bool(delta_use),
            "has_causal_trace": bool(prop_trace),
            "decision_framing": decision_framing or None,
        },
    )

    return {
        "turn_summary": turn_summary,
        "actor_analysis": actor_analysis,
        "causal_chain": causal_chain,
        "outcome_assessment": outcome_assessment,
        "regime_commentary": get_regime_commentary(regime, lang),
        "key_drivers": key_drivers,
        "hidden_costs": hidden_costs,
        "confidence_adjustment_note": confidence_note,
        "decision_framing": decision_framing or None,
        "facts": [f.to_dict() for f in facts],
        "tags": [t.to_dict() for t in tags],
        "inputs": inputs.to_dict(),
    }
