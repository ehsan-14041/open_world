"""
Founder-facing decision brief — sharp, screenshot-ready copy for the product wedge.
"""

from __future__ import annotations

import re
from typing import Any

VAR_LABELS: dict[str, str] = {
    "cash": "Cash balance",
    "runway_months": "Cash runway",
    "burn_rate": "Monthly burn",
    "mrr": "MRR",
    "growth": "Growth rate",
    "churn": "Monthly churn",
    "team_size": "Team size",
    "cac": "Customer acquisition cost",
    "ltv": "Lifetime value",
    "system_stability": "Operational stability",
    "dissatisfaction": "Team morale",
}

REGIME_LABELS: dict[str, str] = {"NORMAL": "Stable", "FRAGILE": "Shaky", "CRISIS": "Critical"}

FEATURED_DECISIONS = ("hire_engineer", "cut_burn", "raise_seed", "increase_price")

PRODUCT_DISCLAIMER = (
    "Directional decision support — not a prediction engine. "
    "Numbers illustrate tradeoffs from your inputs and stated assumptions, not market forecasts."
)

_JARGON_REWRITES: list[tuple[str, str]] = [
    (r"kill criterion", "walk-away signal"),
    (r"CRISIS regime", "critical stress"),
    (r"CRISIS territory", "critical stress"),
    (r"system_stability", "operational stability"),
    (r"simulation flags", "analysis suggests"),
    (r"in this simulation", "in this scenario"),
    (r"primary driver", "biggest lever"),
]


def humanize_var(name: str) -> str:
    key = (name or "").strip().lower()
    return VAR_LABELS.get(key, key.replace("_", " ").title())


def humanize_regime(level: str) -> str:
    return REGIME_LABELS.get(str(level or "").upper(), str(level or "Stable").title())


def defoundify(text: str) -> str:
    out = str(text or "").strip()
    for pattern, replacement in _JARGON_REWRITES:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out


def founder_kill_summary(item: dict[str, Any]) -> str:
    var = humanize_var(str(item.get("watch_variable") or ""))
    signal = defoundify(str(item.get("signal") or item.get("why") or ""))
    if var and signal:
        return f"{var}: {signal}"
    return defoundify(signal or var or "A key metric moves against you")


def _vars(snapshot: dict[str, Any]) -> dict[str, float]:
    v = snapshot.get("variables") or snapshot.get("global_state") or {}
    return {k: float(val) for k, val in v.items() if isinstance(val, (int, float))}


def _regime_level(brief: dict[str, Any]) -> str:
    regime = brief.get("regime") or {}
    if isinstance(regime, dict):
        return str(regime.get("level") or "NORMAL").upper()
    return "NORMAL"


def _runway_delta(initial: dict[str, float], final: dict[str, float]) -> float:
    return final.get("runway_months", 0) - initial.get("runway_months", 0)


def _growth_delta(initial: dict[str, float], final: dict[str, float]) -> float:
    return final.get("growth", 0) - initial.get("growth", 0)


def _risk_level(runway: float, regime: str, runway_delta: float) -> str:
    if runway < 6 or regime == "CRISIS":
        return "High"
    if runway < 10 or regime == "FRAGILE" or runway_delta < -1.5:
        return "Medium"
    return "Low"


def _runway_headline(delta: float, runway: float) -> str:
    if abs(delta) < 0.1:
        return f"Runway holds at ~{runway:.0f} months"
    if delta > 0:
        return f"+{delta:.1f} months runway gained → {runway:.0f} months left"
    return f"{delta:.1f} months runway lost → {runway:.0f} months left"


def _assumption_value(assumptions: list[dict[str, Any]] | None, key: str, default: float) -> float:
    for item in assumptions or []:
        if item.get("key") == key:
            try:
                return float(item.get("value", default))
            except (TypeError, ValueError):
                break
    return default


def _verdict_basis(
    decision_id: str | None,
    runway: float,
    runway_delta: float,
    growth_delta: float,
    regime: str,
    assumptions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Separate simulation deltas from rule-based guidance triggers."""
    did = (decision_id or "").lower()
    rules: list[dict[str, str]] = []

    if did == "hire_engineer":
        if runway < 7:
            rules.append({"id": "runway_below_7", "text": f"Runway after decision ({runway:.1f} mo) is below 7 months."})
        if runway_delta < -1:
            rules.append({"id": "runway_delta_below_-1", "text": f"Simulation shows runway drops by {abs(runway_delta):.1f} months."})
    elif did == "cut_burn":
        if runway_delta > 0.5:
            rules.append({"id": "runway_gain", "text": f"Simulation shows ~{runway_delta:.1f} months runway gained."})
    elif did in ("raise_seed", "raise_pre_seed"):
        if runway < 9:
            rules.append({"id": "runway_below_9", "text": f"Runway ({runway:.0f} mo) leaves limited time to close a round."})
    elif did == "increase_price":
        if runway < 8:
            rules.append({"id": "runway_below_8", "text": "Tight runway increases risk if churn spikes after a price change."})
    if runway < 6:
        rules.append({"id": "runway_critical", "text": f"Runway under 6 months ({runway:.0f} left)."})
    if regime == "CRISIS":
        rules.append({"id": "critical_stress", "text": "Business shows critical stress in the scenario."})

    has_simulation = abs(runway_delta) >= 0.1 or abs(growth_delta) >= 0.1
    if rules and has_simulation:
        primary = "both"
    elif rules:
        primary = "rules"
    elif has_simulation:
        primary = "simulation"
    else:
        primary = "neutral"

    return {
        "simulation": {
            "runway_months_after": round(runway, 1),
            "runway_delta": round(runway_delta, 1),
            "growth_delta": round(growth_delta, 1),
        },
        "rules_triggered": rules,
        "primary_source": primary,
    }


def _one_line_verdict(
    decision_id: str | None,
    runway: float,
    runway_delta: float,
    regime: str,
    profile: dict[str, Any] | None,
    assumptions: list[dict[str, Any]] | None = None,
) -> str:
    name = (profile or {}).get("startup_name") or "You"
    did = (decision_id or "").lower()
    hire_cost = _assumption_value(assumptions, "monthly_hire_cost", 8000)

    if did == "hire_engineer":
        if runway < 7 or runway_delta < -1:
            return (
                f"Don't hire yet — {name} needs more runway before adding "
                f"~${hire_cost:,.0f}/mo in burn (simulation: {runway_delta:+.1f} mo runway)."
            )
        if runway >= 10 and runway_delta >= -0.5:
            return f"Hiring is viable — ~{runway:.0f} months runway remain if you ship and watch burn weekly."
        return f"Hire only if you have a committed revenue path — runway tightens to ~{runway:.0f} months."

    if did == "cut_burn":
        if runway_delta > 0.5:
            return f"Cut burn now — it buys ~{abs(runway_delta):.0f} extra months and reduces panic decisions."
        return "Trim burn even if painful — runway is your constraint right now."

    if did in ("raise_seed", "raise_pre_seed"):
        if runway < 9:
            return f"Start fundraising now — you have ~{runway:.0f} months before options narrow."
        return f"You can wait 1–2 months to improve metrics, but don't let runway drop below 6 months."

    if did == "increase_price":
        if runway < 8:
            return "Raise prices carefully — churn risk is real when runway is tight."
        return "A price increase can fund growth if retention holds — test on a segment first."

    if runway < 6:
        return f"Pause major bets — cash runway is under 6 months ({runway:.0f} left)."
    if regime == "CRISIS":
        return "Stabilize cash and retention before any big move."
    if runway_delta < -1:
        return f"This decision costs runway — you'll land near {runway:.0f} months unless revenue accelerates."
    return f"This decision looks manageable with ~{runway:.0f} months runway — execute in small steps."


def _why_now(profile: dict[str, Any] | None, runway: float, decision_id: str | None) -> str:
    constraint = str((profile or {}).get("key_constraint") or "").strip()
    stage = str((profile or {}).get("stage") or "seed").replace("_", "-")
    churn = float((profile or {}).get("churn") or 0)
    parts = [f"You're at {stage} with ~{runway:.0f} months of cash."]
    if runway < 9:
        parts.append("Runway is the binding constraint — every month of delay shrinks your options.")
    elif churn > 8:
        parts.append(f"Churn at {churn:.0f}% means growth decisions won't stick until retention improves.")
    elif constraint:
        parts.append(f"Your bottleneck: {constraint}.")
    else:
        parts.append("You have room to act, but burn and growth still need weekly tracking.")
    return " ".join(parts)


def _next_step(decision_id: str | None, runway: float, risk: str) -> str:
    did = (decision_id or "").lower()
    if did == "hire_engineer":
        if runway < 7:
            return "Next: model hire cost vs revenue timeline, or defer 90 days and cut non-essential spend."
        return "Next: define the hire's 90-day output metric, cap salary band, and set a runway floor (e.g. 6 months)."
    if did == "cut_burn":
        return "Next: list top 3 cost lines, cut 15–20% in 30 days, and communicate timeline to the team."
    if did in ("raise_seed", "raise_pre_seed"):
        return "Next: update deck + metrics, identify 15 target investors, and start warm intros this week."
    if did == "increase_price":
        return "Next: run a 10-customer price test, measure churn for 30 days, then roll out or rollback."
    if risk == "High":
        return "Next: extend runway first (cut costs or accelerate collections), then revisit this decision."
    return "Next: pick one metric to watch weekly (runway, MRR, or churn) and set a 30-day checkpoint."


def _outcome_summary(
    brief: dict[str, Any],
    runway: float,
    growth: float,
    runway_delta: float,
    growth_delta: float,
    decision_id: str | None,
) -> str:
    what = defoundify(str(brief.get("what_likely_happens") or "").strip())
    if what:
        return what[:400]
    direction = "extends" if runway_delta >= 0 else "shortens"
    return (
        f"Over the next few months, this move {direction} runway to ~{runway:.0f} months "
        f"and {' lifts' if growth_delta >= 0 else ' pressures'} growth toward {growth:.0f}%."
    )


def _humanize_drivers(brief: dict[str, Any], limit: int = 3) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for d in brief.get("top_drivers") or []:
        if not isinstance(d, dict):
            continue
        name = humanize_var(d.get("name") or "")
        why = defoundify(d.get("why_it_matters") or d.get("direction") or "")
        if name:
            out.append({"name": name, "why": why})
        if len(out) >= limit:
            break
    if not out:
        out = [
            {"name": "Cash runway", "why": "Directly determines how long you can execute"},
            {"name": "Monthly burn", "why": "Every hire or campaign decision hits this first"},
            {"name": "Growth rate", "why": "Signals whether the decision buys time or spends it"},
        ]
    return out


def _second_order_plain(brief: dict[str, Any], limit: int = 3) -> list[str]:
    lines: list[str] = []
    for e in brief.get("second_order_effects") or []:
        if not isinstance(e, dict):
            continue
        effect = defoundify(str(e.get("effect") or ""))
        trigger = defoundify(str(e.get("trigger") or ""))
        if effect:
            lines.append(f"{effect}" + (f" (after {trigger})" if trigger else ""))
        if len(lines) >= limit:
            break
    return lines


def _recommended_action(brief: dict[str, Any], profile: dict[str, Any] | None, final_vars: dict[str, float]) -> str:
    runway = final_vars.get("runway_months", 12)
    regime = _regime_level(brief)
    if runway < 6:
        return f"Protect runway first — you're near {runway:.0f} months of cash."
    if regime == "CRISIS":
        return "Cut non-essential burn and validate retention before scaling."
    if regime == "FRAGILE":
        return "Validate weekly: burn, MRR, and churn before committing fully."
    kill = brief.get("kill_criteria") or []
    if kill and isinstance(kill[0], dict):
        return f"Set a walk-away rule: {founder_kill_summary(kill[0])}"
    goal = (profile or {}).get("primary_goal") or "your goal"
    return f"Move forward in small steps toward {goal} — review numbers every month."


def _best_worst_case(final_vars: dict[str, float], profile: dict[str, Any] | None, brief: dict[str, Any]) -> tuple[str, str]:
    runway = final_vars.get("runway_months", 0)
    growth = final_vars.get("growth", 0)
    mrr = final_vars.get("mrr", 0)
    name = (profile or {}).get("startup_name") or "Your startup"
    state = humanize_regime(_regime_level(brief)).lower()
    best = f"{name} keeps ~{runway + 3:.0f}+ months runway, growth near {growth + 4:.0f}%, MRR toward ${mrr * 1.25:,.0f}."
    worst = f"Runway compresses toward {max(1, runway - 3):.0f} months, churn spikes, business stays {state}."
    return best, worst


def _top_risks(brief: dict[str, Any], profile: dict[str, Any] | None) -> list[str]:
    risks: list[str] = []
    for item in brief.get("kill_criteria") or []:
        if isinstance(item, dict):
            line = founder_kill_summary(item)
            if line and line not in risks:
                risks.append(defoundify(line))
    for item in brief.get("hidden_assumptions") or []:
        if isinstance(item, dict):
            risk = defoundify(str(item.get("risk_if_wrong") or item.get("assumption") or ""))
            if risk and risk not in risks:
                risks.append(risk)
    if not risks and profile:
        c = str(profile.get("key_constraint") or "").strip()
        if c:
            risks.append(c)
    return risks[:4]


def _runway_health_score(runway: float, regime: str) -> dict[str, Any]:
    """Directional runway health index — not a statistical survival forecast."""
    score = min(95, max(5, int(runway * 8)))
    if regime == "CRISIS":
        score = max(5, score - 35)
    elif regime == "FRAGILE":
        score = max(10, score - 15)
    score = min(99, score)
    if score >= 70:
        band = "Healthy"
    elif score >= 45:
        band = "Tight"
    else:
        band = "Critical"
    return {
        "score": score,
        "band": band,
        "label": "Runway health (directional)",
        "note": "Illustrative index from months of runway and stress level — not a probability forecast.",
    }


def build_calculation_explanation(
    initial_vars: dict[str, float],
    final_vars: dict[str, float],
    assumptions: list[dict[str, Any]] | None,
    verdict_basis: dict[str, Any],
    decision_label: str | None = None,
    archetype: str | None = None,
) -> dict[str, Any]:
    """Plain-English explainability for the founder product surface."""
    steps: list[str] = []
    rd = final_vars.get("runway_months", 0) - initial_vars.get("runway_months", 0)
    init_runway = initial_vars.get("runway_months", 0)
    init_burn = initial_vars.get("burn_rate", 0)
    final_burn = final_vars.get("burn_rate", init_burn)
    final_runway = final_vars.get("runway_months", 0)

    steps.append(
        f"Starting point: ~{init_runway:.0f} months runway, "
        f"${init_burn:,.0f}/mo burn, ${initial_vars.get('mrr', 0):,.0f} MRR."
    )

    if decision_label:
        steps.append(f"Decision modeled: {decision_label}.")

    for item in assumptions or []:
        label = item.get("label") or item.get("key")
        val = item.get("value")
        tk = item.get("tradeoff_key")
        if tk == "burn_rate" and isinstance(val, (int, float)) and val > 0:
            steps.append(f"Assumption: {label} = ${val:,.0f}/mo added to burn.")
        elif tk == "cash" and isinstance(val, (int, float)):
            steps.append(f"Assumption: {label} = ${val:,.0f} cash injected.")
        elif isinstance(val, (int, float)):
            steps.append(f"Assumption: {label} = {val}.")

    if abs(final_burn - init_burn) >= 100:
        steps.append(
            f"Burn moves from ${init_burn:,.0f} to ${final_burn:,.0f}/mo; "
            f"runway shifts {rd:+.1f} months to ~{final_runway:.0f} months."
        )
    elif abs(rd) >= 0.1:
        steps.append(f"After cascading effects, runway changes {rd:+.1f} months → ~{final_runway:.0f} months left.")

    if archetype:
        steps.append(f"Second-order effects use {archetype.replace('_', ' ')} causal links (burn → runway, growth → MRR, etc.).")

    for rule in verdict_basis.get("rules_triggered") or []:
        steps.append(f"Guidance rule: {rule.get('text', '')}")

    return {
        "steps": [s for s in steps if s],
        "assumptions": assumptions or [],
        "verdict_basis": verdict_basis,
        "disclaimer": PRODUCT_DISCLAIMER,
    }


def _confidence_label(brief: dict[str, Any]) -> str:
    level = str((brief.get("confidence") or {}).get("level") or "moderate").lower()
    return {"high": "High confidence", "moderate": "Moderate uncertainty", "low": "Low confidence — treat as directional"}.get(
        level, "Moderate uncertainty"
    )


def build_startup_outcomes(
    final_snapshot: dict[str, Any],
    provenance: list[dict[str, Any]],
    startup_profile: dict[str, Any] | None,
    brief: dict[str, Any],
    initial_snapshot: dict[str, Any] | None = None,
    decision_id: str | None = None,
    decision_label: str | None = None,
    assumptions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the full founder decision brief (screenshot-ready)."""
    final_vars = _vars(final_snapshot)
    initial_vars = _vars(initial_snapshot) if initial_snapshot else {}
    if not initial_vars and provenance:
        initial_vars = _vars((provenance[0] or {}).get("pre_state") or {}) or final_vars

    runway = final_vars.get("runway_months", 0)
    growth = final_vars.get("growth", 0)
    mrr = final_vars.get("mrr", 0)
    burn = final_vars.get("burn_rate", 0)
    regime = _regime_level(brief)
    rd = _runway_delta(initial_vars, final_vars)
    gd = _growth_delta(initial_vars, final_vars)
    risk = _risk_level(runway, regime, rd)
    best, worst = _best_worst_case(final_vars, startup_profile, brief)
    verdict_basis = _verdict_basis(decision_id, runway, rd, gd, regime, assumptions)
    runway_health = _runway_health_score(runway, regime)
    archetype = (startup_profile or {}).get("startup_type")
    calculation = build_calculation_explanation(
        initial_vars, final_vars, assumptions, verdict_basis, decision_label, archetype
    )

    return {
        "decision_id": decision_id or "",
        "decision_label": decision_label or "",
        "one_line_recommendation": _one_line_verdict(
            decision_id, runway, rd, regime, startup_profile, assumptions
        ),
        "verdict_basis": verdict_basis,
        "calculation_explanation": calculation,
        "disclaimer": PRODUCT_DISCLAIMER,
        "runway_health": runway_health,
        "runway_headline": _runway_headline(rd, runway),
        "runway_impact": _runway_headline(rd, runway),
        "runway_months": runway,
        "runway_delta": round(rd, 1),
        "growth_outlook": f"Growth {'+' if gd >= 0 else ''}{gd:.1f} pts → {growth:.1f}% · MRR ${mrr:,.0f}",
        "growth_rate": growth,
        "growth_delta": round(gd, 1),
        "mrr": mrr,
        "monthly_burn": burn,
        "risk_level": risk,
        "regime": humanize_regime(regime),
        "regime_level": regime,
        "outcome_summary": _outcome_summary(brief, runway, growth, rd, gd, decision_id),
        "why_now": _why_now(startup_profile, runway, decision_id),
        "best_case": f"(Illustrative) {best}",
        "worst_case": f"(Illustrative) {worst}",
        "recommended_action": _recommended_action(brief, startup_profile, final_vars),
        "next_step": _next_step(decision_id, runway, risk),
        "key_drivers": _humanize_drivers(brief),
        "second_order_effects": _second_order_plain(brief),
        "walk_away_signals": _top_risks(brief, startup_profile),
        "top_risks": _top_risks(brief, startup_profile),
        "confidence_level": (brief.get("confidence") or {}).get("level") or "moderate",
        "confidence_label": _confidence_label(brief),
    }


def build_comparison_card(
    decision_id: str,
    decision_label: str,
    final_snapshot: dict[str, Any],
    provenance: list[dict[str, Any]],
    startup_profile: dict[str, Any] | None,
    brief: dict[str, Any],
    initial_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact card for A/B decision comparison."""
    o = build_startup_outcomes(
        final_snapshot, provenance, startup_profile, brief, initial_snapshot,
        decision_id=decision_id, decision_label=decision_label,
    )
    return {
        "decision_id": decision_id,
        "label": decision_label,
        "one_line_recommendation": o["one_line_recommendation"],
        "runway_headline": o["runway_headline"],
        "runway_delta": o["runway_delta"],
        "risk_level": o["risk_level"],
        "next_step": o["next_step"],
        "regime": o["regime"],
    }
