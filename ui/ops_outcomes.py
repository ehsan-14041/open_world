"""
Enterprise operations decision brief — screenshot-ready copy for supply chain / inventory wedge.
"""

from __future__ import annotations

import re
from typing import Any

VAR_LABELS: dict[str, str] = {
    "inventory_on_hand": "Inventory on hand",
    "safety_stock": "Safety stock",
    "weekly_demand": "Weekly demand",
    "lead_time_days": "Lead time",
    "fill_rate": "Fill rate (service level)",
    "unit_cost": "Unit cost",
    "holding_cost_weekly": "Weekly holding cost",
    "supplier_risk": "Supplier risk",
    "capacity_utilization": "Capacity utilization",
    "stockout_risk": "Stockout risk",
    "backlog_weeks": "Backlog (weeks)",
    "system_stability": "Operational stability",
    "dissatisfaction": "Stakeholder dissatisfaction",
}

REGIME_LABELS: dict[str, str] = {"NORMAL": "Stable", "FRAGILE": "Constrained", "CRISIS": "Critical"}

FEATURED_DECISIONS = (
    "increase_safety_stock",
    "expedite_reorder",
    "switch_supplier",
    "reallocate_demand",
)

PRODUCT_DISCLAIMER = (
    "Directional decision support — not a prediction engine. "
    "Numbers illustrate tradeoffs from your inputs and stated assumptions, not demand forecasts."
)

_JARGON_REWRITES: list[tuple[str, str]] = [
    (r"kill criterion", "walk-away signal"),
    (r"CRISIS regime", "critical operational stress"),
    (r"CRISIS territory", "critical operational stress"),
    (r"system_stability", "operational stability"),
    (r"simulation flags", "analysis suggests"),
    (r"in this simulation", "in this scenario"),
    (r"primary driver", "key driver"),
    (r"multi-agent", "cross-functional"),
    (r"simulation engine", "decision analysis"),
]


def humanize_var(name: str) -> str:
    key = (name or "").strip().lower()
    return VAR_LABELS.get(key, key.replace("_", " ").title())


def humanize_regime(level: str) -> str:
    return REGIME_LABELS.get(str(level or "").upper(), str(level or "Stable").title())


def dejargonize(text: str) -> str:
    out = str(text or "").strip()
    for pattern, replacement in _JARGON_REWRITES:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out


def ops_kill_summary(item: dict[str, Any]) -> str:
    var = humanize_var(str(item.get("watch_variable") or ""))
    signal = dejargonize(str(item.get("signal") or item.get("why") or ""))
    if var and signal:
        return f"{var}: {signal}"
    return dejargonize(signal or var or "A key operational metric moves against you")


def _vars(snapshot: dict[str, Any]) -> dict[str, float]:
    v = snapshot.get("variables") or snapshot.get("global_state") or {}
    return {k: float(val) for k, val in v.items() if isinstance(val, (int, float))}


def _regime_level(brief: dict[str, Any]) -> str:
    regime = brief.get("regime") or {}
    if isinstance(regime, dict):
        return str(regime.get("level") or "NORMAL").upper()
    return "NORMAL"


def _fill_delta(initial: dict[str, float], final: dict[str, float]) -> float:
    return (final.get("fill_rate", 0) - initial.get("fill_rate", 0)) * 100


def _cost_delta(initial: dict[str, float], final: dict[str, float]) -> float:
    return final.get("holding_cost_weekly", 0) - initial.get("holding_cost_weekly", 0)


def _risk_delta(initial: dict[str, float], final: dict[str, float]) -> float:
    return (final.get("stockout_risk", 0) - initial.get("stockout_risk", 0)) * 100


def _risk_level(fill_rate: float, regime: str, stockout_risk: float, fill_delta: float) -> str:
    if fill_rate < 0.88 or regime == "CRISIS" or stockout_risk > 0.35:
        return "High"
    if fill_rate < 0.93 or regime == "FRAGILE" or fill_delta < -1.5 or stockout_risk > 0.2:
        return "Medium"
    return "Low"


def _service_level_headline(delta_pts: float, fill_rate: float) -> str:
    pct = fill_rate * 100
    if abs(delta_pts) < 0.15:
        return f"Fill rate holds at ~{pct:.1f}%"
    if delta_pts > 0:
        return f"+{delta_pts:.1f} pts fill rate → {pct:.1f}% projected"
    return f"{delta_pts:.1f} pts fill rate → {pct:.1f}% projected"


def _cost_headline(delta: float, holding: float) -> str:
    if abs(delta) < 10:
        return f"Holding cost steady at ~${holding:,.0f}/week"
    if delta > 0:
        return f"+${delta:,.0f}/wk holding cost → ${holding:,.0f}/week"
    return f"−${abs(delta):,.0f}/wk holding cost → ${holding:,.0f}/week"


def _risk_headline(delta_pts: float, stockout: float) -> str:
    pct = stockout * 100
    if abs(delta_pts) < 0.2:
        return f"Stockout risk ~{pct:.0f}%"
    if delta_pts > 0:
        return f"+{delta_pts:.1f} pts stockout risk → {pct:.0f}%"
    return f"{delta_pts:.1f} pts stockout risk → {pct:.0f}%"


def _lead_time_headline(initial: dict[str, float], final: dict[str, float]) -> str:
    init_lt = initial.get("lead_time_days", 0)
    final_lt = final.get("lead_time_days", 0)
    delta = final_lt - init_lt
    if abs(delta) < 0.5:
        return f"Lead time holds at ~{final_lt:.0f} days"
    if delta < 0:
        return f"−{abs(delta):.0f} days lead time → {final_lt:.0f} days"
    return f"+{delta:.0f} days lead time → {final_lt:.0f} days"


def _bottleneck_headline(initial: dict[str, float], final: dict[str, float]) -> str:
    init_bl = initial.get("backlog_weeks", 0)
    final_bl = final.get("backlog_weeks", 0)
    init_cap = initial.get("capacity_utilization", 0) * 100
    final_cap = final.get("capacity_utilization", 0) * 100
    bl_delta = final_bl - init_bl
    cap_delta = final_cap - init_cap
    if abs(bl_delta) >= 0.05:
        if bl_delta > 0:
            return f"+{bl_delta:.1f} wk backlog → {final_bl:.1f} weeks"
        return f"−{abs(bl_delta):.1f} wk backlog → {final_bl:.1f} weeks"
    if abs(cap_delta) >= 1.0:
        if cap_delta > 0:
            return f"+{cap_delta:.0f} pts utilization → {final_cap:.0f}%"
        return f"−{abs(cap_delta):.0f} pts utilization → {final_cap:.0f}%"
    if final_cap >= 92:
        return f"Capacity tight at {final_cap:.0f}% utilization"
    if final_bl >= 0.5:
        return f"Backlog ~{final_bl:.1f} weeks"
    return "No material bottleneck shift"


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
    fill_rate: float,
    fill_delta: float,
    cost_delta: float,
    stockout_risk: float,
    regime: str,
    assumptions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    did = (decision_id or "").lower()
    rules: list[dict[str, str]] = []

    if did == "increase_safety_stock":
        if fill_rate >= 0.95 and cost_delta > 500:
            rules.append({"id": "high_fill_high_cost", "text": f"Fill rate already {fill_rate * 100:.1f}% — buffer adds cost without service gain."})
        if cost_delta > 800:
            rules.append({"id": "holding_cost_spike", "text": f"Holding cost rises ~${cost_delta:,.0f}/week."})
    elif did == "expedite_reorder":
        if fill_rate >= 0.94 and cost_delta > 200:
            rules.append({"id": "expedite_not_justified", "text": "Service level already acceptable — expedite premium hard to justify."})
        if fill_delta > 2:
            rules.append({"id": "fill_gain", "text": f"Scenario shows +{fill_delta:.1f} pts fill rate improvement."})
    elif did == "switch_supplier":
        if stockout_risk > 0.3:
            rules.append({"id": "supplier_transition_risk", "text": "Supplier transition adds execution risk during elevated stockout exposure."})
    elif did == "reduce_safety_stock":
        if fill_delta < -2:
            rules.append({"id": "service_drop", "text": f"Fill rate drops {abs(fill_delta):.1f} pts — service target at risk."})
    elif did == "hold_inventory":
        if fill_rate < 0.9:
            rules.append({"id": "inaction_risk", "text": f"Fill rate at {fill_rate * 100:.1f}% — holding position may miss recovery window."})
    if fill_rate < 0.88:
        rules.append({"id": "fill_critical", "text": f"Fill rate below 88% ({fill_rate * 100:.1f}%)."})
    if regime == "CRISIS":
        rules.append({"id": "critical_stress", "text": "Operations under critical stress in the scenario."})

    has_simulation = abs(fill_delta) >= 0.1 or abs(cost_delta) >= 50 or abs(stockout_risk) >= 0.02
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
            "fill_rate_after": round(fill_rate * 100, 1),
            "fill_rate_delta_pts": round(fill_delta, 1),
            "holding_cost_delta_weekly": round(cost_delta, 0),
            "stockout_risk_after_pct": round(stockout_risk * 100, 1),
        },
        "rules_triggered": rules,
        "primary_source": primary,
    }


def _one_line_verdict(
    decision_id: str | None,
    fill_rate: float,
    fill_delta: float,
    cost_delta: float,
    stockout_risk: float,
    regime: str,
    profile: dict[str, Any] | None,
    assumptions: list[dict[str, Any]] | None = None,
) -> str:
    site = (profile or {}).get("site_name") or "This site"
    did = (decision_id or "").lower()
    holding_add = _assumption_value(assumptions, "weekly_holding_cost", 850)

    if did == "increase_safety_stock":
        if fill_rate >= 0.95:
            return f"Don't add buffer yet — {site} is already at {fill_rate * 100:.1f}% fill rate; holding cost rises ~${holding_add:,.0f}/week."
        if fill_delta > 1.5 and cost_delta < 1200:
            return f"Increase safety stock — projects +{fill_delta:.1f} pts fill rate with manageable holding cost."
        return f"Increase buffer cautiously — service gain of +{max(0, fill_delta):.1f} pts must justify ~${abs(cost_delta):,.0f}/wk extra cost."

    if did == "expedite_reorder":
        if fill_rate >= 0.94 and cost_delta > 150:
            return "Don't expedite — service gain doesn't justify premium freight at current fill rate."
        if fill_delta > 2:
            return f"Expedite reorder — cuts lead-time exposure and lifts fill rate ~{fill_delta:.1f} pts."
        return f"Expedite only if customer penalties exceed ~${abs(cost_delta):,.0f}/wk in added cost."

    if did == "switch_supplier":
        if stockout_risk > 0.3:
            return "Defer supplier switch — transition risk is too high while stockout exposure is elevated."
        if fill_delta > 1:
            return f"Switch supplier mix — shorter lead time lifts fill rate ~{fill_delta:.1f} pts."
        return "Pilot supplier switch on 10–15% volume before full reallocation."

    if did == "reallocate_demand":
        if fill_delta > 1:
            return f"Reallocate demand — relieves bottleneck and improves fill rate ~{fill_delta:.1f} pts."
        return "Reallocate demand to sites with available capacity — validate logistics cost first."

    if did == "reduce_safety_stock":
        if fill_delta < -2:
            return f"Don't cut safety stock — fill rate drops {abs(fill_delta):.1f} pts below service target."
        return f"Reduce buffer only if finance needs cash — saves ~${abs(cost_delta):,.0f}/wk holding cost."

    if did == "add_capacity":
        if fill_delta > 1.5:
            return f"Add capacity — clears backlog and lifts fill rate ~{fill_delta:.1f} pts."
        return "Add overtime/temp line if backlog exceeds 1 week — watch unit cost impact."

    if did == "hold_inventory":
        if fill_rate < 0.9:
            return f"Don't hold position — fill rate at {fill_rate * 100:.1f}% needs active intervention."
        return "Hold and monitor — stable service level allows 2-week watch period."

    if fill_rate < 0.88:
        return f"Act now — fill rate at {fill_rate * 100:.1f}% is below acceptable service threshold."
    if regime == "CRISIS":
        return "Stabilize service level and supplier reliability before any major operational bet."
    if fill_delta < -1.5:
        return f"This decision pressures service level — fill rate drops to ~{fill_rate * 100:.1f}%."
    return f"This decision looks manageable — fill rate projects ~{fill_rate * 100:.1f}% with moderate risk."


def _why_now(profile: dict[str, Any] | None, fill_rate: float, decision_id: str | None) -> str:
    constraint = str((profile or {}).get("primary_constraint") or "").strip()
    lead = float((profile or {}).get("lead_time_days") or 14)
    capacity = float((profile or {}).get("capacity_utilization") or 0.75)
    parts = [f"Current fill rate is {fill_rate * 100:.1f}% with {lead:.0f}-day lead times."]
    if fill_rate < 0.92:
        parts.append("Service level is below target — weekly planning meetings need a clear lever.")
    elif capacity > 0.9:
        parts.append(f"Capacity at {capacity * 100:.0f}% — any demand spike hits backlog fast.")
    elif constraint:
        parts.append(f"Binding constraint: {constraint}.")
    else:
        parts.append("Metrics are stable, but lead-time and demand uncertainty still warrant a pre-decision check.")
    return " ".join(parts)


def _next_step(decision_id: str | None, fill_rate: float, risk: str) -> str:
    did = (decision_id or "").lower()
    if did == "increase_safety_stock":
        if fill_rate >= 0.95:
            return "Next: validate demand forecast accuracy before adding buffer; model holding cost vs stockout penalty."
        return "Next: confirm reorder quantity with planning team, set fill-rate floor (e.g. 94%), review in 2 weeks."
    if did == "expedite_reorder":
        return "Next: get expedite quote from top 2 suppliers, compare premium vs stockout cost, approve PO within 48 hours."
    if did == "switch_supplier":
        return "Next: run quality audit on alternate supplier, pilot 15% volume for 4 weeks, define rollback trigger."
    if did == "reallocate_demand":
        return "Next: map demand by DC/channel, identify sites with <80% utilization, align with sales on customer impact."
    if did == "reduce_safety_stock":
        return "Next: model stockout cost per SKU, cut buffer on low-velocity items first, monitor fill rate daily."
    if did == "add_capacity":
        return "Next: confirm overtime availability, calculate incremental unit cost, set 4-week backlog clearance target."
    if risk == "High":
        return "Next: stabilize fill rate above 90% before committing — escalate to supply chain director this week."
    return "Next: pick one KPI to review weekly (fill rate, lead time, or holding cost) and set a 30-day checkpoint."


def _outcome_summary(
    brief: dict[str, Any],
    fill_rate: float,
    fill_delta: float,
    cost_delta: float,
    decision_id: str | None,
) -> str:
    what = dejargonize(str(brief.get("what_likely_happens") or "").strip())
    if what:
        return what[:400]
    direction = "improves" if fill_delta >= 0 else "pressures"
    cost_dir = "rises" if cost_delta > 0 else "falls"
    return (
        f"Over the planning horizon, this move {direction} fill rate to ~{fill_rate * 100:.1f}% "
        f"and weekly holding cost {cost_dir} by ~${abs(cost_delta):,.0f}."
    )


def _humanize_drivers(brief: dict[str, Any], limit: int = 3) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for d in brief.get("top_drivers") or []:
        if not isinstance(d, dict):
            continue
        name = humanize_var(d.get("name") or "")
        why = dejargonize(d.get("why_it_matters") or d.get("direction") or "")
        if name:
            out.append({"name": name, "why": why})
        if len(out) >= limit:
            break
    if not out:
        out = [
            {"name": "Fill rate", "why": "Direct measure of customer service level"},
            {"name": "Lead time", "why": "Drives replenishment lag and stockout exposure"},
            {"name": "Holding cost", "why": "Every inventory decision hits working capital"},
        ]
    return out


def _second_order_plain(brief: dict[str, Any], limit: int = 3) -> list[str]:
    lines: list[str] = []
    for e in brief.get("second_order_effects") or []:
        if not isinstance(e, dict):
            continue
        effect = dejargonize(str(e.get("effect") or ""))
        trigger = dejargonize(str(e.get("trigger") or ""))
        if effect:
            lines.append(f"{effect}" + (f" (after {trigger})" if trigger else ""))
        if len(lines) >= limit:
            break
    return lines


def _recommended_action(brief: dict[str, Any], profile: dict[str, Any] | None, final_vars: dict[str, float]) -> str:
    fill_rate = final_vars.get("fill_rate", 0.94)
    regime = _regime_level(brief)
    if fill_rate < 0.88:
        return f"Protect service level first — fill rate near {fill_rate * 100:.1f}%."
    if regime == "CRISIS":
        return "Escalate to executive team — stabilize supplier reliability and clear backlog before scaling."
    if regime == "FRAGILE":
        return "Validate weekly: fill rate, lead time, and holding cost before full commitment."
    kill = brief.get("kill_criteria") or []
    if kill and isinstance(kill[0], dict):
        return f"Set a walk-away rule: {ops_kill_summary(kill[0])}"
    goal = (profile or {}).get("planning_goal") or "your planning goal"
    return f"Move forward in controlled steps toward {goal} — review metrics in the next S&OP cycle."


def _best_worst_case(final_vars: dict[str, float], profile: dict[str, Any] | None, brief: dict[str, Any]) -> tuple[str, str]:
    fill = final_vars.get("fill_rate", 0) * 100
    cost = final_vars.get("holding_cost_weekly", 0)
    stockout = final_vars.get("stockout_risk", 0) * 100
    site = (profile or {}).get("site_name") or "Operations"
    state = humanize_regime(_regime_level(brief)).lower()
    best = (
        f"{site} holds fill rate near {min(99, fill + 2):.1f}%, "
        f"stockout risk below {max(2, stockout - 5):.0f}%, holding cost ~${cost * 0.9:,.0f}/wk."
    )
    worst = (
        f"Fill rate drops toward {max(80, fill - 4):.1f}%, "
        f"stockout risk rises above {min(45, stockout + 8):.0f}% — operations stay {state}."
    )
    return best, worst


def _top_risks(brief: dict[str, Any], profile: dict[str, Any] | None) -> list[str]:
    risks: list[str] = []
    for item in brief.get("kill_criteria") or []:
        if isinstance(item, dict):
            line = ops_kill_summary(item)
            if line and line not in risks:
                risks.append(dejargonize(line))
    for item in brief.get("hidden_assumptions") or []:
        if isinstance(item, dict):
            risk = dejargonize(str(item.get("risk_if_wrong") or item.get("assumption") or ""))
            if risk and risk not in risks:
                risks.append(risk)
    if not risks and profile:
        c = str(profile.get("primary_constraint") or "").strip()
        if c:
            risks.append(c)
    return risks[:4]


def _service_health_score(fill_rate: float, stockout_risk: float, regime: str) -> dict[str, Any]:
    score = min(95, max(5, int(fill_rate * 100 - stockout_risk * 30)))
    if regime == "CRISIS":
        score = max(5, score - 30)
    elif regime == "FRAGILE":
        score = max(10, score - 12)
    score = min(99, score)
    if score >= 75:
        band = "Healthy"
    elif score >= 50:
        band = "At risk"
    else:
        band = "Critical"
    return {
        "score": score,
        "band": band,
        "label": "Service level health (directional)",
        "note": "Illustrative index from fill rate and stockout exposure — not a statistical forecast.",
    }


def build_calculation_explanation(
    initial_vars: dict[str, float],
    final_vars: dict[str, float],
    assumptions: list[dict[str, Any]] | None,
    verdict_basis: dict[str, Any],
    decision_label: str | None = None,
    archetype: str | None = None,
) -> dict[str, Any]:
    steps: list[str] = []
    fd = _fill_delta(initial_vars, final_vars)
    init_fill = initial_vars.get("fill_rate", 0) * 100
    final_fill = final_vars.get("fill_rate", 0) * 100
    init_cost = initial_vars.get("holding_cost_weekly", 0)
    final_cost = final_vars.get("holding_cost_weekly", 0)
    cd = final_cost - init_cost

    steps.append(
        f"Starting point: {init_fill:.1f}% fill rate, "
        f"${init_cost:,.0f}/wk holding cost, "
        f"{initial_vars.get('lead_time_days', 0):.0f}-day lead time."
    )
    if decision_label:
        steps.append(f"Decision modeled: {decision_label}.")
    for item in assumptions or []:
        label = item.get("label") or item.get("key")
        val = item.get("value")
        tk = item.get("tradeoff_key")
        if tk == "holding_cost_weekly" and isinstance(val, (int, float)):
            steps.append(f"Assumption: {label} = ${val:,.0f}/week.")
        elif tk == "inventory_on_hand" and isinstance(val, (int, float)):
            steps.append(f"Assumption: {label} = {val:,.0f} units.")
        elif isinstance(val, (int, float)):
            steps.append(f"Assumption: {label} = {val}.")

    if abs(cd) >= 50:
        steps.append(
            f"Holding cost moves from ${init_cost:,.0f} to ${final_cost:,.0f}/wk; "
            f"fill rate shifts {fd:+.1f} pts to {final_fill:.1f}%."
        )
    elif abs(fd) >= 0.1:
        steps.append(f"After cascading effects, fill rate changes {fd:+.1f} pts → {final_fill:.1f}%.")

    lt_headline = _lead_time_headline(initial_vars, final_vars)
    bn_headline = _bottleneck_headline(initial_vars, final_vars)
    if "holds at" not in lt_headline:
        steps.append(f"Lead time: {lt_headline}.")
    if "No material" not in bn_headline:
        steps.append(f"Bottleneck / delay: {bn_headline}.")

    if archetype:
        steps.append(
            f"Second-order effects use {archetype.replace('_', ' ')} causal links "
            "(demand → inventory → fill rate, lead time → service level, etc.)."
        )
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
    return {
        "high": "High confidence",
        "moderate": "Moderate uncertainty",
        "low": "Low confidence — treat as directional",
    }.get(level, "Moderate uncertainty")


def build_ops_outcomes(
    final_snapshot: dict[str, Any],
    provenance: list[dict[str, Any]],
    ops_profile: dict[str, Any] | None,
    brief: dict[str, Any],
    initial_snapshot: dict[str, Any] | None = None,
    decision_id: str | None = None,
    decision_label: str | None = None,
    assumptions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the full enterprise operations decision brief (screenshot-ready)."""
    final_vars = _vars(final_snapshot)
    initial_vars = _vars(initial_snapshot) if initial_snapshot else {}
    if not initial_vars and provenance:
        initial_vars = _vars((provenance[0] or {}).get("pre_state") or {}) or final_vars

    fill_rate = final_vars.get("fill_rate", 0)
    holding = final_vars.get("holding_cost_weekly", 0)
    stockout = final_vars.get("stockout_risk", 0)
    lead = final_vars.get("lead_time_days", 0)
    regime = _regime_level(brief)
    fd = _fill_delta(initial_vars, final_vars)
    cd = _cost_delta(initial_vars, final_vars)
    rd = _risk_delta(initial_vars, final_vars)
    backlog_delta = final_vars.get("backlog_weeks", 0) - initial_vars.get("backlog_weeks", 0)
    lead_time_delta = final_vars.get("lead_time_days", 0) - initial_vars.get("lead_time_days", 0)
    risk = _risk_level(fill_rate, regime, stockout, fd)
    best, worst = _best_worst_case(final_vars, ops_profile, brief)
    verdict_basis = _verdict_basis(decision_id, fill_rate, fd, cd, stockout, regime, assumptions)
    service_health = _service_health_score(fill_rate, stockout, regime)
    archetype = (ops_profile or {}).get("business_unit_type")
    calculation = build_calculation_explanation(
        initial_vars, final_vars, assumptions, verdict_basis, decision_label, archetype
    )

    return {
        "decision_id": decision_id or "",
        "decision_label": decision_label or "",
        "one_line_recommendation": _one_line_verdict(
            decision_id, fill_rate, fd, cd, stockout, regime, ops_profile, assumptions
        ),
        "verdict_basis": verdict_basis,
        "calculation_explanation": calculation,
        "disclaimer": PRODUCT_DISCLAIMER,
        "service_health": service_health,
        "service_level_headline": _service_level_headline(fd, fill_rate),
        "cost_headline": _cost_headline(cd, holding),
        "risk_headline": _risk_headline(rd, stockout),
        "lead_time_headline": _lead_time_headline(initial_vars, final_vars),
        "bottleneck_headline": _bottleneck_headline(initial_vars, final_vars),
        "backlog_weeks_delta": round(backlog_delta, 2),
        "lead_time_days_delta": round(lead_time_delta, 1),
        "fill_rate": fill_rate,
        "fill_rate_pct": round(fill_rate * 100, 1),
        "fill_rate_delta_pts": round(fd, 1),
        "holding_cost_weekly": holding,
        "cost_delta_weekly": round(cd, 0),
        "stockout_risk": stockout,
        "stockout_risk_pct": round(stockout * 100, 1),
        "stockout_risk_delta_pts": round(rd, 1),
        "lead_time_days": lead,
        "risk_level": risk,
        "regime": humanize_regime(regime),
        "regime_level": regime,
        "outcome_summary": _outcome_summary(brief, fill_rate, fd, cd, decision_id),
        "why_now": _why_now(ops_profile, fill_rate, decision_id),
        "best_case": f"(Illustrative) {best}",
        "worst_case": f"(Illustrative) {worst}",
        "recommended_action": _recommended_action(brief, ops_profile, final_vars),
        "next_step": _next_step(decision_id, fill_rate, risk),
        "key_drivers": _humanize_drivers(brief),
        "second_order_effects": _second_order_plain(brief),
        "walk_away_signals": _top_risks(brief, ops_profile),
        "top_risks": _top_risks(brief, ops_profile),
        "confidence_level": (brief.get("confidence") or {}).get("level") or "moderate",
        "confidence_label": _confidence_label(brief),
    }


def build_comparison_card(
    decision_id: str,
    decision_label: str,
    final_snapshot: dict[str, Any],
    provenance: list[dict[str, Any]],
    ops_profile: dict[str, Any] | None,
    brief: dict[str, Any],
    initial_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    o = build_ops_outcomes(
        final_snapshot, provenance, ops_profile, brief, initial_snapshot,
        decision_id=decision_id, decision_label=decision_label,
    )
    return {
        "decision_id": decision_id,
        "label": decision_label,
        "one_line_recommendation": o["one_line_recommendation"],
        "service_level_headline": o["service_level_headline"],
        "cost_headline": o["cost_headline"],
        "fill_rate_delta_pts": o["fill_rate_delta_pts"],
        "risk_level": o["risk_level"],
        "next_step": o["next_step"],
        "regime": o["regime"],
    }
