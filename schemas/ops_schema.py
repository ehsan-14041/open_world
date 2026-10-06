"""
Operations profile schema for the Enterprise Operations Decision Simulator.

Captures supply-chain / inventory planning state and maps into engine scenarios
via adapters.ops_scenario_builder.
"""

from __future__ import annotations

from typing import Any

BUSINESS_UNIT_TYPES = (
    "manufacturing",
    "distribution",
    "retail",
    "multi_echelon",
    "contract_manufacturing",
    "general_ops",
)

PLANNING_HORIZONS = (4, 8, 12, 26)


def validate_ops_profile(data: Any) -> list[str]:
    """Return validation errors; empty list means valid."""
    if not isinstance(data, dict):
        return ["ops_profile must be a JSON object"]
    errors: list[str] = []

    but = str(data.get("business_unit_type") or "").strip().lower()
    if not but:
        errors.append("'business_unit_type' is required")
    elif but not in BUSINESS_UNIT_TYPES:
        errors.append(f"'business_unit_type' must be one of {list(BUSINESS_UNIT_TYPES)}")

    horizon = data.get("planning_horizon_weeks")
    if horizon is not None and horizon != "":
        try:
            h = int(horizon)
            if h not in PLANNING_HORIZONS:
                errors.append(f"'planning_horizon_weeks' must be one of {list(PLANNING_HORIZONS)}")
        except (TypeError, ValueError):
            errors.append("'planning_horizon_weeks' must be an integer")

    for key in (
        "inventory_on_hand",
        "safety_stock",
        "weekly_demand",
        "lead_time_days",
        "unit_cost",
        "holding_cost_pct",
    ):
        val = data.get(key)
        if val is not None and val != "":
            try:
                n = float(val)
                if n < 0:
                    errors.append(f"'{key}' must be non-negative")
            except (TypeError, ValueError):
                errors.append(f"'{key}' must be a number")

    for key in ("fill_rate", "supplier_risk", "capacity_utilization"):
        val = data.get(key)
        if val is not None and val != "":
            try:
                n = float(val)
                if n < 0 or n > 1:
                    errors.append(f"'{key}' must be between 0 and 1")
            except (TypeError, ValueError):
                errors.append(f"'{key}' must be a number")

    return errors


def _to_float(val: Any, default: float | None = None) -> float | None:
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _to_int(val: Any, default: int | None = None) -> int | None:
    f = _to_float(val, None)
    if f is None:
        return default
    return int(round(f))


def _derive_stockout_risk(fill_rate: float, safety_stock: float, on_hand: float, demand: float) -> float:
    """Directional stockout risk from buffer coverage vs service level."""
    weeks_cover = on_hand / demand if demand > 0 else 4.0
    target_cover = safety_stock / demand if demand > 0 else 2.0
    gap = max(0.0, target_cover - weeks_cover)
    base = max(0.0, 1.0 - fill_rate)
    return min(0.95, max(0.05, base + gap * 0.08))


def normalize_ops_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Return a clean operations profile with derived defaults."""
    on_hand = _to_float(data.get("inventory_on_hand"), 12000.0) or 12000.0
    demand = _to_float(data.get("weekly_demand"), 800.0) or 800.0
    safety = _to_float(data.get("safety_stock"), None)
    if safety is None:
        safety = max(demand * 2, on_hand * 0.15)

    fill_rate = _to_float(data.get("fill_rate"), 0.94) or 0.94
    lead_time = _to_float(data.get("lead_time_days"), 14.0) or 14.0
    unit_cost = _to_float(data.get("unit_cost"), 12.5) or 12.5
    holding_pct = _to_float(data.get("holding_cost_pct"), 0.18) or 0.18
    supplier_risk = _to_float(data.get("supplier_risk"), 0.25) or 0.25
    capacity = _to_float(data.get("capacity_utilization"), 0.78) or 0.78

    stockout_risk = _to_float(data.get("stockout_risk"), None)
    if stockout_risk is None:
        stockout_risk = _derive_stockout_risk(fill_rate, safety, on_hand, demand)

    holding_cost = on_hand * unit_cost * holding_pct / 52.0
    backlog = max(0.0, (demand * capacity - demand * 0.85) / max(demand, 1) * 2) if capacity > 0.85 else 0.5

    horizon = _to_int(data.get("planning_horizon_weeks"), 8) or 8
    if horizon not in PLANNING_HORIZONS:
        horizon = 8

    return {
        "site_name": str(data.get("site_name") or "Regional DC").strip() or "Regional DC",
        "business_unit_type": str(data.get("business_unit_type") or "distribution").strip().lower(),
        "product_family": str(data.get("product_family") or "Core SKU line").strip(),
        "planning_horizon_weeks": horizon,
        "inventory_on_hand": on_hand,
        "safety_stock": safety,
        "weekly_demand": demand,
        "lead_time_days": lead_time,
        "fill_rate": fill_rate,
        "unit_cost": unit_cost,
        "holding_cost_pct": holding_pct,
        "holding_cost_weekly": holding_cost,
        "supplier_risk": supplier_risk,
        "capacity_utilization": capacity,
        "stockout_risk": stockout_risk,
        "backlog_weeks": backlog,
        "primary_constraint": str(data.get("primary_constraint") or "inventory buffer vs service target").strip(),
        "planning_goal": str(data.get("planning_goal") or "hit service level without excess inventory cost").strip(),
    }
