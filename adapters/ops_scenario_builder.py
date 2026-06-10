"""
Build validated engine scenarios from operations profiles and decision templates.

Skips LLM parsing — deterministic supply-chain scenarios for the product UI.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from schemas.scenario_schema import normalize_scenario
from schemas.decision_schema import normalize_decision_input
from schemas.ops_schema import normalize_ops_profile

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DECISIONS_PATH = _PROJECT_ROOT / "config" / "ops_decisions.json"

_BASE_AGENTS = [
    {"name": "ops_director", "role": "OperationsDirector", "objectives": {"service_level": 0.55, "cost_control": 0.45}},
    {"name": "supply_chain_lead", "role": "SupplyChainLead", "objectives": {"lead_time": 0.5, "supplier_risk": 0.5}},
    {"name": "finance_controller", "role": "FinanceController", "objectives": {"holding_cost": 0.5, "margin": 0.5}},
    {"name": "planning_manager", "role": "PlanningManager", "objectives": {"forecast_accuracy": 0.5, "allocation": 0.5}},
]

_BASE_ACTIONS = [
    "replenish_stock",
    "expedite_inbound",
    "rebalance_allocation",
    "reduce_buffer",
    "add_shift_capacity",
    "steady_operations",
]

_BASE_TRADEOFFS: dict[str, dict[str, float]] = {
    "replenish_stock": {"inventory_on_hand": 1500, "holding_cost_weekly": 400, "fill_rate": 0.02},
    "expedite_inbound": {"lead_time_days": -3, "unit_cost": 0.8, "fill_rate": 0.025},
    "rebalance_allocation": {"weekly_demand": -50, "capacity_utilization": -0.05, "fill_rate": 0.015},
    "reduce_buffer": {"inventory_on_hand": -1200, "holding_cost_weekly": -350, "fill_rate": -0.02, "stockout_risk": 0.05},
    "add_shift_capacity": {"capacity_utilization": -0.08, "unit_cost": 0.6, "fill_rate": 0.02, "backlog_weeks": -0.3},
    "steady_operations": {"fill_rate": -0.005, "stockout_risk": 0.01},
}

_BASE_VARIABLE_TRADEOFFS: dict[str, dict[str, float]] = {
    "weekly_demand": {"inventory_on_hand": -120, "capacity_utilization": 0.04, "backlog_weeks": 0.15},
    "inventory_on_hand": {"fill_rate": 0.0008, "holding_cost_weekly": 0.35, "stockout_risk": -0.02},
    "safety_stock": {"fill_rate": 0.0012, "stockout_risk": -0.015},
    "lead_time_days": {"fill_rate": -0.002, "stockout_risk": 0.012},
    "supplier_risk": {"lead_time_days": 0.8, "unit_cost": 0.15, "fill_rate": -0.003},
    "unit_cost": {"holding_cost_weekly": 0.2, "supplier_risk": 0.01},
    "capacity_utilization": {"backlog_weeks": 0.25, "fill_rate": -0.004},
    "fill_rate": {"stockout_risk": -0.06},
}

_ARCHETYPE_CAUSAL: dict[str, list[dict[str, Any]]] = {
    "distribution": [
        {"from": "weekly_demand", "to": "inventory_on_hand", "weight": -0.55},
        {"from": "inventory_on_hand", "to": "fill_rate", "weight": 0.65},
        {"from": "safety_stock", "to": "fill_rate", "weight": 0.45},
        {"from": "lead_time_days", "to": "fill_rate", "weight": -0.5},
        {"from": "supplier_risk", "to": "lead_time_days", "weight": 0.35},
        {"from": "unit_cost", "to": "holding_cost_weekly", "weight": 0.4},
        {"from": "inventory_on_hand", "to": "holding_cost_weekly", "weight": 0.5},
        {"from": "fill_rate", "to": "stockout_risk", "weight": -0.7},
        {"from": "capacity_utilization", "to": "backlog_weeks", "weight": 0.6},
        {"from": "weekly_demand", "to": "capacity_utilization", "weight": 0.35},
    ],
    "manufacturing": [
        {"from": "capacity_utilization", "to": "backlog_weeks", "weight": 0.75},
        {"from": "backlog_weeks", "to": "fill_rate", "weight": -0.55},
        {"from": "weekly_demand", "to": "capacity_utilization", "weight": 0.5},
        {"from": "inventory_on_hand", "to": "fill_rate", "weight": 0.5},
        {"from": "lead_time_days", "to": "fill_rate", "weight": -0.4},
        {"from": "supplier_risk", "to": "lead_time_days", "weight": 0.4},
        {"from": "fill_rate", "to": "stockout_risk", "weight": -0.65},
        {"from": "inventory_on_hand", "to": "holding_cost_weekly", "weight": 0.45},
    ],
    "retail": [
        {"from": "weekly_demand", "to": "inventory_on_hand", "weight": -0.6},
        {"from": "inventory_on_hand", "to": "fill_rate", "weight": 0.7},
        {"from": "lead_time_days", "to": "fill_rate", "weight": -0.45},
        {"from": "supplier_risk", "to": "lead_time_days", "weight": 0.38},
        {"from": "fill_rate", "to": "stockout_risk", "weight": -0.72},
        {"from": "unit_cost", "to": "holding_cost_weekly", "weight": 0.35},
    ],
    "multi_echelon": [
        {"from": "supplier_risk", "to": "lead_time_days", "weight": 0.5},
        {"from": "lead_time_days", "to": "fill_rate", "weight": -0.55},
        {"from": "inventory_on_hand", "to": "fill_rate", "weight": 0.55},
        {"from": "safety_stock", "to": "fill_rate", "weight": 0.4},
        {"from": "weekly_demand", "to": "inventory_on_hand", "weight": -0.5},
        {"from": "fill_rate", "to": "stockout_risk", "weight": -0.68},
        {"from": "unit_cost", "to": "supplier_risk", "weight": 0.2},
    ],
    "contract_manufacturing": [
        {"from": "supplier_risk", "to": "lead_time_days", "weight": 0.45},
        {"from": "lead_time_days", "to": "fill_rate", "weight": -0.48},
        {"from": "capacity_utilization", "to": "backlog_weeks", "weight": 0.55},
        {"from": "backlog_weeks", "to": "fill_rate", "weight": -0.4},
        {"from": "inventory_on_hand", "to": "fill_rate", "weight": 0.45},
    ],
    "general_ops": [
        {"from": "weekly_demand", "to": "inventory_on_hand", "weight": -0.5},
        {"from": "inventory_on_hand", "to": "fill_rate", "weight": 0.6},
        {"from": "lead_time_days", "to": "fill_rate", "weight": -0.45},
        {"from": "supplier_risk", "to": "lead_time_days", "weight": 0.35},
        {"from": "fill_rate", "to": "stockout_risk", "weight": -0.65},
        {"from": "capacity_utilization", "to": "backlog_weeks", "weight": 0.5},
    ],
}

_VARIABLE_SPECS: dict[str, dict[str, Any]] = {
    "inventory_on_hand": {"min": 0, "behavior_type": "STOCK", "inertia": 0.25},
    "safety_stock": {"min": 0, "behavior_type": "STOCK", "inertia": 0.2},
    "weekly_demand": {"min": 0, "behavior_type": "FLOW"},
    "lead_time_days": {"min": 1, "max": 90, "rate_limit": 8},
    "fill_rate": {"min": 0, "max": 1, "behavior_type": "FLOW"},
    "unit_cost": {"min": 0, "behavior_type": "STOCK"},
    "holding_cost_weekly": {"min": 0, "behavior_type": "FLOW"},
    "supplier_risk": {"min": 0, "max": 1, "behavior_type": "FLOW"},
    "capacity_utilization": {"min": 0, "max": 1, "behavior_type": "FLOW"},
    "stockout_risk": {"min": 0, "max": 1, "behavior_type": "FLOW"},
    "backlog_weeks": {"min": 0, "max": 12, "behavior_type": "FLOW"},
}


def load_decision_templates() -> list[dict[str, Any]]:
    try:
        data = json.loads(_DECISIONS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def get_decision_template(decision_id: str) -> dict[str, Any] | None:
    for t in load_decision_templates():
        if t.get("id") == decision_id:
            return t
    return None


ASSUMPTION_SPECS: dict[str, list[dict[str, Any]]] = {
    "increase_safety_stock": [
        {
            "key": "reorder_quantity",
            "tradeoff_key": "inventory_on_hand",
            "label": "Additional units to hold",
            "min": 500,
            "max": 8000,
            "step": 100,
            "default_from": "inventory_on_hand",
        },
        {
            "key": "weekly_holding_cost",
            "tradeoff_key": "holding_cost_weekly",
            "label": "Extra weekly holding cost ($)",
            "min": 200,
            "max": 5000,
            "step": 50,
            "default_from": "holding_cost_weekly",
        },
    ],
    "expedite_reorder": [
        {
            "key": "lead_time_reduction",
            "tradeoff_key": "lead_time_days",
            "label": "Lead time reduction (days)",
            "min": 2,
            "max": 14,
            "step": 1,
            "default_from": "lead_time_days",
            "absolute": True,
        },
        {
            "key": "expedite_premium_pct",
            "tradeoff_key": "unit_cost",
            "label": "Expedite premium per unit ($)",
            "min": 0.5,
            "max": 5,
            "step": 0.1,
            "default_from": "unit_cost",
        },
    ],
    "switch_supplier": [
        {
            "key": "lead_time_improvement",
            "tradeoff_key": "lead_time_days",
            "label": "Lead time improvement (days)",
            "min": 1,
            "max": 10,
            "step": 1,
            "default_from": "lead_time_days",
            "absolute": True,
        },
        {
            "key": "supplier_risk_delta",
            "tradeoff_key": "supplier_risk",
            "label": "Supplier risk change (pts)",
            "min": -0.2,
            "max": 0.2,
            "step": 0.02,
            "default_from": "supplier_risk",
        },
    ],
    "reallocate_demand": [
        {
            "key": "demand_shift_units",
            "tradeoff_key": "weekly_demand",
            "label": "Weekly demand shifted (units)",
            "min": 50,
            "max": 500,
            "step": 10,
            "default_from": "weekly_demand",
            "absolute": True,
        },
        {
            "key": "fill_rate_gain",
            "tradeoff_key": "fill_rate",
            "label": "Expected fill rate gain (pts)",
            "min": 0.005,
            "max": 0.05,
            "step": 0.005,
            "default_from": "fill_rate",
        },
    ],
    "emergency_reorder": [
        {
            "key": "reorder_quantity",
            "tradeoff_key": "inventory_on_hand",
            "label": "Emergency order quantity (units)",
            "min": 1000,
            "max": 10000,
            "step": 200,
            "default_from": "inventory_on_hand",
        },
        {
            "key": "demand_shock_pct",
            "tradeoff_key": "fill_rate",
            "label": "Expected fill rate gain (pts)",
            "min": 0.01,
            "max": 0.08,
            "step": 0.005,
            "default_from": "fill_rate",
        },
    ],
}


def get_editable_assumptions(decision_template: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not decision_template:
        return []
    did = str(decision_template.get("id") or "")
    specs = ASSUMPTION_SPECS.get(did)
    if not specs:
        return []
    hint = decision_template.get("tradeoff_hint") or {}
    out: list[dict[str, Any]] = []
    for spec in specs:
        tradeoff_key = spec["tradeoff_key"]
        raw = float(hint.get(tradeoff_key, 0))
        if spec.get("absolute") and tradeoff_key in ("lead_time_days", "weekly_demand") and raw < 0:
            default = abs(raw)
        else:
            default = raw
        out.append({
            "key": spec["key"],
            "tradeoff_key": tradeoff_key,
            "label": spec["label"],
            "min": spec["min"],
            "max": spec["max"],
            "step": spec.get("step", 1),
            "value": default,
            "unit": spec.get("unit", ""),
        })
    return out


def apply_assumption_overrides(
    tradeoff_hint: dict[str, float],
    decision_id: str,
    overrides: dict[str, Any] | None,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    hint = {k: float(v) for k, v in tradeoff_hint.items()}
    assumptions_used: list[dict[str, Any]] = []
    specs = ASSUMPTION_SPECS.get(decision_id or "", [])
    if not specs or not overrides:
        for spec in specs:
            tk = spec["tradeoff_key"]
            val = hint.get(tk, 0)
            if spec.get("absolute") and tk in ("lead_time_days", "weekly_demand") and val < 0:
                val = abs(val)
            assumptions_used.append({
                "key": spec["key"],
                "label": spec["label"],
                "value": val,
                "tradeoff_key": tk,
                "source": "default",
            })
        return hint, assumptions_used

    spec_by_key = {s["key"]: s for s in specs}
    for key, raw_val in overrides.items():
        spec = spec_by_key.get(str(key))
        if not spec:
            continue
        try:
            val = float(raw_val)
        except (TypeError, ValueError):
            continue
        tk = spec["tradeoff_key"]
        if spec.get("absolute") and tk in ("lead_time_days", "weekly_demand"):
            hint[tk] = -abs(val)
            display_val = abs(val)
        else:
            hint[tk] = val
            display_val = val
        assumptions_used.append({
            "key": key,
            "label": spec["label"],
            "value": display_val,
            "tradeoff_key": tk,
            "source": "user",
        })

    for spec in specs:
        if any(a["key"] == spec["key"] for a in assumptions_used):
            continue
        tk = spec["tradeoff_key"]
        val = hint.get(tk, 0)
        if spec.get("absolute") and tk in ("lead_time_days", "weekly_demand") and val < 0:
            val = abs(val)
        assumptions_used.append({
            "key": spec["key"],
            "label": spec["label"],
            "value": val,
            "tradeoff_key": tk,
            "source": "default",
        })
    return hint, assumptions_used


def _profile_to_initial_state(profile: dict[str, Any]) -> dict[str, float]:
    return {
        "inventory_on_hand": float(profile["inventory_on_hand"]),
        "safety_stock": float(profile["safety_stock"]),
        "weekly_demand": float(profile["weekly_demand"]),
        "lead_time_days": float(profile["lead_time_days"]),
        "fill_rate": float(profile["fill_rate"]),
        "unit_cost": float(profile["unit_cost"]),
        "holding_cost_weekly": float(profile.get("holding_cost_weekly") or 0),
        "supplier_risk": float(profile["supplier_risk"]),
        "capacity_utilization": float(profile["capacity_utilization"]),
        "stockout_risk": float(profile.get("stockout_risk") or 0.1),
        "backlog_weeks": float(profile.get("backlog_weeks") or 0.5),
    }


def _build_description(profile: dict[str, Any], decision: dict[str, Any] | None) -> str:
    site = profile.get("site_name") or "Operations site"
    but = profile.get("business_unit_type") or "operations"
    family = profile.get("product_family") or "product line"
    goal = profile.get("planning_goal") or ""
    constraint = profile.get("primary_constraint") or ""
    parts = [
        f"{site} ({but.replace('_', ' ')}) manages {family}.",
        f"Inventory: {profile.get('inventory_on_hand', 0):,.0f} units on hand, "
        f"safety stock {profile.get('safety_stock', 0):,.0f}, "
        f"weekly demand {profile.get('weekly_demand', 0):,.0f} units.",
        f"Service level: {float(profile.get('fill_rate', 0)) * 100:.1f}% fill rate, "
        f"lead time {profile.get('lead_time_days')} days, "
        f"supplier risk {float(profile.get('supplier_risk', 0)) * 100:.0f}%.",
        f"Capacity utilization: {float(profile.get('capacity_utilization', 0)) * 100:.0f}%. "
        f"Planning goal: {goal}. Key constraint: {constraint}.",
    ]
    if decision:
        move = decision.get("move_en") or decision.get("move") or ""
        parts.append(f"Decision under analysis: {move}")
    return " ".join(p for p in parts if p)


def decision_template_to_input(
    template: dict[str, Any],
    profile: dict[str, Any],
    *,
    lang: str = "en",
    horizon_override: int | None = None,
) -> dict[str, Any]:
    move = template.get("move_en") or template.get("move") or ""
    actors = template.get("actors_en") or template.get("actors") or []
    weeks = horizon_override or template.get("horizon_weeks") or 8
    horizon_months = max(1, int(round(weeks / 4)))
    context = (
        f"{profile.get('site_name')} ({profile.get('business_unit_type')}): "
        f"{profile.get('inventory_on_hand', 0):,.0f} units on hand, "
        f"{float(profile.get('fill_rate', 0)) * 100:.1f}% fill rate, "
        f"{profile.get('lead_time_days')} day lead time. Goal: {profile.get('planning_goal')}."
    )
    return normalize_decision_input({
        "move": move,
        "actors": list(actors),
        "horizon_months": horizon_months,
        "context": context,
        "constraints": {
            "service_level_target": f"{float(profile.get('fill_rate', 0)) * 100:.0f}%",
            "capacity": f"{float(profile.get('capacity_utilization', 0)) * 100:.0f}% utilization",
            "budget": f"${profile.get('holding_cost_weekly', 0):,.0f}/wk holding cost",
            "other": profile.get("primary_constraint") or "",
        },
    })


def build_scenario(
    profile: dict[str, Any],
    decision_template: dict[str, Any] | None = None,
    *,
    decision_input: dict[str, Any] | None = None,
    lang: str = "en",
    assumption_overrides: dict[str, Any] | None = None,
    fitted_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a normalized scenario JSON from an operations profile and optional decision template.

    If `fitted_links` is provided (causal weights estimated from the customer's own data
    via core.data_fitting.fit_weights), they REPLACE the archetype-guessed weights — the
    structure stays, the magnitudes become data-grounded. This is the single switch that
    turns the engine from "guessed coefficients" into a calibrated, per-customer model.
    """
    profile = normalize_ops_profile(profile)
    but = profile.get("business_unit_type") or "distribution"

    if decision_input is None and decision_template:
        decision_input = decision_template_to_input(decision_template, profile, lang=lang)

    action_tradeoffs = deepcopy(_BASE_TRADEOFFS)
    assumptions_used: list[dict[str, Any]] = []
    delayed_events: list[dict[str, Any]] = []

    if decision_template and isinstance(decision_template.get("tradeoff_hint"), dict):
        did = str(decision_template.get("id") or "")
        hint, assumptions_used = apply_assumption_overrides(
            decision_template["tradeoff_hint"],
            did,
            assumption_overrides,
        )
        decision_action = f"decision_{did or 'move'}"
        action_tradeoffs[decision_action] = hint
        # Decision first so dry-run agents always consider the user's chosen lever.
        allowed = [decision_action] + list(_BASE_ACTIONS)[:3]

        # Lead-time effects arrive 1–2 turns later (inbound shipment lag).
        if did in ("expedite_reorder", "switch_supplier", "emergency_reorder"):
            inv_boost = float(hint.get("inventory_on_hand", 0))
            if inv_boost > 0:
                delayed_events.append({
                    "trigger_turn": 2,
                    "effects": {"inventory_on_hand": inv_boost * 0.6, "fill_rate": float(hint.get("fill_rate", 0)) * 0.5},
                    "description": "Inbound replenishment arrives after lead-time lag",
                })
    else:
        allowed = list(_BASE_ACTIONS)

    initial_state = _profile_to_initial_state(profile)
    if fitted_links:
        # Data-fitted weights replace archetype guesses (structure preserved).
        causal_links = [{"from": l["from"], "to": l["to"], "weight": float(l["weight"])}
                        for l in fitted_links if l.get("from") and l.get("to")]
    else:
        causal_links = deepcopy(_ARCHETYPE_CAUSAL.get(but, _ARCHETYPE_CAUSAL["general_ops"]))

    scenario = normalize_scenario({
        "description": _build_description(profile, decision_template),
        "initial_agents": deepcopy(_BASE_AGENTS),
        "initial_state": initial_state,
        "relations": [
            {"from": "ops_director", "to": "supply_chain_lead", "type": "reports_to"},
            {"from": "planning_manager", "to": "ops_director", "type": "advises"},
            {"from": "finance_controller", "to": "ops_director", "type": "advises"},
        ],
        "allowed_actions": allowed,
        "action_tradeoffs": action_tradeoffs,
        "variable_tradeoffs": deepcopy(_BASE_VARIABLE_TRADEOFFS),
        "causal_links": causal_links,
        "variable_specs": deepcopy(_VARIABLE_SPECS),
        "governance": {
            "stability_variable": "fill_rate",
            "dissatisfaction_variable": "supplier_risk",
            "strictness_level": 1,
        },
    })

    if delayed_events:
        scenario["delayed_events"] = delayed_events

    scenario["ops_profile"] = profile
    if decision_input:
        scenario["decision_input"] = decision_input
    if decision_template:
        scenario["decision_template_id"] = decision_template.get("id")
        scenario["product_decision_action"] = f"decision_{decision_template.get('id') or 'move'}"
    if assumptions_used:
        scenario["assumptions_used"] = assumptions_used

    return scenario
