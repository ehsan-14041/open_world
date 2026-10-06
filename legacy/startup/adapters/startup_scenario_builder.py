"""
Build validated engine scenarios from startup profiles and decision templates.

Skips LLM parsing — deterministic startup-flavored scenarios for the product UI.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from schemas.scenario_schema import normalize_scenario
from schemas.decision_schema import normalize_decision_input
from schemas.startup_schema import normalize_startup_profile

_LEGACY_STARTUP_ROOT = Path(__file__).resolve().parent.parent
_DECISIONS_PATH = _LEGACY_STARTUP_ROOT / "config" / "startup_decisions.json"

# Base startup agents (from demo_scenario.json pattern)
_BASE_AGENTS = [
    {"name": "founder", "role": "Founder", "objectives": {"growth": 0.6, "conserve_cash": 0.4}},
    {"name": "investor", "role": "Investor", "objectives": {"runway": 0.5, "governance": 0.5}},
    {"name": "customer_success", "role": "CustomerSuccess", "objectives": {"retention": 0.6, "engagement": 0.4}},
]

_BASE_ACTIONS = [
    "invest_in_growth",
    "cut_costs",
    "request_investment",
    "investor_update",
    "steady_finance",
    "improve_retention",
    "hire_team",
]

_BASE_TRADEOFFS: dict[str, dict[str, float]] = {
    "invest_in_growth": {"growth": 4, "burn_rate": 3000, "cash": -3000},
    "cut_costs": {"burn_rate": -4000, "growth": -2, "runway_months": 2},
    "request_investment": {"cash": 150000, "runway_months": 6, "growth": 1},
    "investor_update": {"growth": 0.5, "cash": -500},
    "steady_finance": {"cash": 1500, "growth": -0.5},
    "improve_retention": {"churn": -2, "mrr": 1500, "burn_rate": 1000},
    "hire_team": {"burn_rate": 7000, "growth": 2, "team_size": 1},
}

_BASE_VARIABLE_TRADEOFFS: dict[str, dict[str, float]] = {
    "growth": {"burn_rate": 500, "cash": -500},
    "burn_rate": {"runway_months": -0.3, "cash": -1000},
    "cash": {"runway_months": -0.15},
    "runway_months": {"growth": -0.3},
    "churn": {"mrr": -800, "growth": -1},
    "mrr": {"cash": 500, "growth": 0.5},
    "cac": {"growth": 1, "burn_rate": 300},
    "population": {"growth": 0.3, "burn_rate": 100},
}

_ARCHETYPE_CAUSAL: dict[str, list[dict[str, Any]]] = {
    "b2b_saas": [
        {"from": "churn", "to": "mrr", "weight": -0.7},
        {"from": "burn_rate", "to": "runway_months", "weight": -0.8},
        {"from": "growth", "to": "mrr", "weight": 0.6},
        {"from": "mrr", "to": "cash", "weight": 0.5},
    ],
    "ai_saas": [
        {"from": "burn_rate", "to": "runway_months", "weight": -0.9},
        {"from": "growth", "to": "mrr", "weight": 0.8},
        {"from": "growth", "to": "burn_rate", "weight": 0.4},
        {"from": "churn", "to": "mrr", "weight": -0.6},
    ],
    "marketplace": [
        {"from": "population", "to": "growth", "weight": 0.7},
        {"from": "growth", "to": "mrr", "weight": 0.5},
        {"from": "churn", "to": "population", "weight": -0.5},
        {"from": "burn_rate", "to": "runway_months", "weight": -0.7},
    ],
    "mobile_app": [
        {"from": "activation_rate", "to": "growth", "weight": 0.6},
        {"from": "churn", "to": "growth", "weight": -0.7},
        {"from": "growth", "to": "population", "weight": 0.8},
        {"from": "population", "to": "mrr", "weight": 0.3},
    ],
    "agency": [
        {"from": "burn_rate", "to": "runway_months", "weight": -0.85},
        {"from": "mrr", "to": "cash", "weight": 0.7},
        {"from": "growth", "to": "burn_rate", "weight": 0.3},
    ],
    "consumer_subscription": [
        {"from": "churn", "to": "mrr", "weight": -0.8},
        {"from": "cac", "to": "growth", "weight": 0.5},
        {"from": "ltv", "to": "mrr", "weight": 0.4},
        {"from": "growth", "to": "mrr", "weight": 0.6},
    ],
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


# User-editable assumption fields mapped to tradeoff_hint keys (product UI).
ASSUMPTION_SPECS: dict[str, list[dict[str, Any]]] = {
    "hire_engineer": [
        {
            "key": "monthly_hire_cost",
            "tradeoff_key": "burn_rate",
            "label": "Monthly hire cost ($)",
            "min": 3000,
            "max": 25000,
            "step": 500,
            "default_from": "burn_rate",
        },
        {
            "key": "growth_boost",
            "tradeoff_key": "growth",
            "label": "Expected growth boost (pts)",
            "min": 0,
            "max": 8,
            "step": 0.5,
            "default_from": "growth",
        },
    ],
    "hire_salesperson": [
        {
            "key": "monthly_hire_cost",
            "tradeoff_key": "burn_rate",
            "label": "Monthly hire cost ($)",
            "min": 3000,
            "max": 20000,
            "step": 500,
            "default_from": "burn_rate",
        },
        {
            "key": "mrr_boost",
            "tradeoff_key": "mrr",
            "label": "Expected MRR boost ($/mo)",
            "min": 0,
            "max": 15000,
            "step": 500,
            "default_from": "mrr",
        },
    ],
    "cut_burn": [
        {
            "key": "monthly_savings",
            "tradeoff_key": "burn_rate",
            "label": "Monthly savings ($)",
            "min": 1000,
            "max": 30000,
            "step": 500,
            "default_from": "burn_rate",
            "absolute": True,
        },
        {
            "key": "runway_gain",
            "tradeoff_key": "runway_months",
            "label": "Runway gained (months)",
            "min": 0,
            "max": 12,
            "step": 0.5,
            "default_from": "runway_months",
        },
    ],
    "raise_pre_seed": [
        {
            "key": "raise_amount",
            "tradeoff_key": "cash",
            "label": "Raise amount ($)",
            "min": 100000,
            "max": 1500000,
            "step": 25000,
            "default_from": "cash",
        },
        {
            "key": "runway_gain",
            "tradeoff_key": "runway_months",
            "label": "Runway gained (months)",
            "min": 3,
            "max": 24,
            "step": 1,
            "default_from": "runway_months",
        },
    ],
    "raise_seed": [
        {
            "key": "raise_amount",
            "tradeoff_key": "cash",
            "label": "Raise amount ($)",
            "min": 500000,
            "max": 5000000,
            "step": 50000,
            "default_from": "cash",
        },
        {
            "key": "runway_gain",
            "tradeoff_key": "runway_months",
            "label": "Runway gained (months)",
            "min": 6,
            "max": 36,
            "step": 1,
            "default_from": "runway_months",
        },
    ],
    "increase_price": [
        {
            "key": "mrr_boost",
            "tradeoff_key": "mrr",
            "label": "Expected MRR boost ($/mo)",
            "min": 500,
            "max": 20000,
            "step": 500,
            "default_from": "mrr",
        },
        {
            "key": "churn_increase",
            "tradeoff_key": "churn",
            "label": "Churn increase (pts)",
            "min": 0,
            "max": 10,
            "step": 0.5,
            "default_from": "churn",
        },
    ],
}


def get_editable_assumptions(decision_template: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return UI-ready assumption field specs with defaults from the decision template."""
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
        if spec.get("absolute") and tradeoff_key == "burn_rate" and raw < 0:
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
    """
    Apply user assumption overrides to a tradeoff_hint copy.
    Returns (updated_hint, assumptions_used list for explainability).
    """
    hint = {k: float(v) for k, v in tradeoff_hint.items()}
    assumptions_used: list[dict[str, Any]] = []
    specs = ASSUMPTION_SPECS.get(decision_id or "", [])
    if not specs or not overrides:
        for spec in specs:
            tk = spec["tradeoff_key"]
            val = hint.get(tk, 0)
            if spec.get("absolute") and tk == "burn_rate" and val < 0:
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
        if spec.get("absolute") and tk == "burn_rate":
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
        if spec.get("absolute") and tk == "burn_rate" and val < 0:
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
    users = profile.get("users")
    population = float(users) if users else max(100.0, profile.get("mrr", 0) / 10)
    return {
        "cash": float(profile["cash"]),
        "runway_months": float(profile["runway_months"]),
        "burn_rate": float(profile["monthly_burn"]),
        "mrr": float(profile["mrr"]),
        "growth": float(profile["growth_rate"]),
        "churn": float(profile["churn"]),
        "team_size": float(profile["team_size"]),
        "activation_rate": float(profile["activation_rate"]),
        "cac": float(profile["cac"]),
        "ltv": float(profile["ltv"]),
        "population": population,
    }


def _build_description(profile: dict[str, Any], decision: dict[str, Any] | None) -> str:
    name = profile.get("startup_name") or "Startup"
    stype = profile.get("startup_type") or "startup"
    stage = profile.get("stage") or "seed"
    market = profile.get("market") or "general market"
    goal = profile.get("primary_goal") or ""
    constraint = profile.get("key_constraint") or ""
    parts = [
        f"{name} is a {stage}-stage {stype.replace('_', ' ')} startup in {market}.",
        f"Cash: ${profile.get('cash', 0):,.0f}, monthly burn: ${profile.get('monthly_burn', 0):,.0f}, "
        f"runway: {profile.get('runway_months')} months, MRR: ${profile.get('mrr', 0):,.0f}.",
        f"Growth rate: {profile.get('growth_rate')}%, churn: {profile.get('churn')}%, team: {profile.get('team_size')}.",
        f"Primary goal: {goal}. Key constraint: {constraint}.",
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
    """Convert a decision template + profile into a DecisionInput dict."""
    fa = lang == "fa"
    move = template.get("move_fa" if fa else "move_en") or template.get("move_en") or ""
    actors = template.get("actors_fa" if fa else "actors_en") or template.get("actors_en") or []
    horizon = horizon_override or template.get("horizon_months") or 6
    context = (
        f"{profile.get('startup_name')} ({profile.get('startup_type')}, {profile.get('stage')}): "
        f"${profile.get('cash', 0):,.0f} cash, {profile.get('runway_months')}mo runway, "
        f"${profile.get('mrr', 0):,.0f} MRR. Goal: {profile.get('primary_goal')}."
    )
    return normalize_decision_input({
        "move": move,
        "actors": list(actors),
        "horizon_months": horizon,
        "context": context,
        "constraints": {
            "team_size": profile.get("team_size"),
            "runway_months": profile.get("runway_months"),
            "budget": f"${profile.get('cash', 0):,.0f} cash",
            "other": profile.get("key_constraint") or "",
        },
    })


def build_scenario(
    profile: dict[str, Any],
    decision_template: dict[str, Any] | None = None,
    *,
    decision_input: dict[str, Any] | None = None,
    lang: str = "en",
    assumption_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a normalized scenario JSON from a startup profile and optional decision template.
    """
    profile = normalize_startup_profile(profile)
    stype = profile.get("startup_type") or "b2b_saas"

    if decision_input is None and decision_template:
        decision_input = decision_template_to_input(decision_template, profile, lang=lang)

    action_tradeoffs = deepcopy(_BASE_TRADEOFFS)
    assumptions_used: list[dict[str, Any]] = []
    if decision_template and isinstance(decision_template.get("tradeoff_hint"), dict):
        did = str(decision_template.get("id") or "")
        hint, assumptions_used = apply_assumption_overrides(
            decision_template["tradeoff_hint"],
            did,
            assumption_overrides,
        )
        decision_action = f"decision_{did or 'move'}"
        action_tradeoffs[decision_action] = hint
        allowed = list(_BASE_ACTIONS) + [decision_action]
    else:
        allowed = list(_BASE_ACTIONS)

    initial_state = _profile_to_initial_state(profile)
    causal_links = _ARCHETYPE_CAUSAL.get(stype, _ARCHETYPE_CAUSAL["b2b_saas"])

    scenario = normalize_scenario({
        "description": _build_description(profile, decision_template),
        "initial_agents": deepcopy(_BASE_AGENTS),
        "initial_state": initial_state,
        "relations": [
            {"from": "founder", "to": "investor", "type": "reports_to"},
            {"from": "customer_success", "to": "founder", "type": "advises"},
        ],
        "allowed_actions": allowed,
        "action_tradeoffs": action_tradeoffs,
        "variable_tradeoffs": deepcopy(_BASE_VARIABLE_TRADEOFFS),
        "causal_links": causal_links,
    })

    scenario["startup_profile"] = profile
    if decision_input:
        scenario["decision_input"] = decision_input
    if decision_template:
        scenario["decision_template_id"] = decision_template.get("id")
    if assumptions_used:
        scenario["assumptions_used"] = assumptions_used

    return scenario
