"""
Startup profile schema for the Startup Decision Simulator product layer.

Captures founder-facing company state and maps into engine scenarios via
adapters.startup_scenario_builder.
"""

from __future__ import annotations

from typing import Any

STARTUP_TYPES = (
    "b2b_saas",
    "ai_saas",
    "marketplace",
    "mobile_app",
    "agency",
    "consumer_subscription",
)

STAGES = ("idea", "pre_seed", "seed", "series_a", "growth")

FUNDRAISING_STATUSES = (
    "bootstrapped",
    "raising",
    "recently_funded",
    "not_raising",
)


def validate_startup_profile(data: Any) -> list[str]:
    """Return validation errors; empty list means valid."""
    if not isinstance(data, dict):
        return ["startup_profile must be a JSON object"]
    errors: list[str] = []

    st = str(data.get("startup_type") or "").strip().lower()
    if not st:
        errors.append("'startup_type' is required")
    elif st not in STARTUP_TYPES:
        errors.append(f"'startup_type' must be one of {list(STARTUP_TYPES)}")

    stage = str(data.get("stage") or "").strip().lower()
    if not stage:
        errors.append("'stage' is required")
    elif stage not in STAGES:
        errors.append(f"'stage' must be one of {list(STAGES)}")

    for key in ("team_size", "monthly_burn", "cash", "runway_months", "mrr"):
        val = data.get(key)
        if val is not None and val != "":
            try:
                n = float(val)
                if n < 0:
                    errors.append(f"'{key}' must be non-negative")
            except (TypeError, ValueError):
                errors.append(f"'{key}' must be a number")

    for key in ("growth_rate", "churn", "activation_rate"):
        val = data.get(key)
        if val is not None and val != "":
            try:
                n = float(val)
                if key == "churn" and (n < 0 or n > 100):
                    errors.append("'churn' must be between 0 and 100")
                elif n < 0:
                    errors.append(f"'{key}' must be non-negative")
            except (TypeError, ValueError):
                errors.append(f"'{key}' must be a number")

    fs = data.get("fundraising_status")
    if fs is not None and str(fs).strip():
        if str(fs).strip().lower() not in FUNDRAISING_STATUSES:
            errors.append(f"'fundraising_status' must be one of {list(FUNDRAISING_STATUSES)}")

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


def normalize_startup_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Return a clean startup profile with derived defaults."""
    cash = _to_float(data.get("cash"), 100_000.0) or 100_000.0
    burn = _to_float(data.get("monthly_burn"), None)
    runway = _to_int(data.get("runway_months"), None)

    if runway is None and burn and burn > 0:
        runway = max(1, int(cash / burn))
    if runway is None:
        runway = 12
    if burn is None and runway > 0:
        burn = max(1.0, cash / runway)

    return {
        "startup_name": str(data.get("startup_name") or "My Startup").strip() or "My Startup",
        "startup_type": str(data.get("startup_type") or "b2b_saas").strip().lower(),
        "stage": str(data.get("stage") or "seed").strip().lower(),
        "market": str(data.get("market") or "").strip(),
        "team_size": _to_int(data.get("team_size"), 8) or 8,
        "monthly_burn": burn or 10_000.0,
        "cash": cash,
        "runway_months": runway,
        "mrr": _to_float(data.get("mrr"), 0.0) or 0.0,
        "growth_rate": _to_float(data.get("growth_rate"), 10.0) or 10.0,
        "churn": _to_float(data.get("churn"), 5.0) or 5.0,
        "activation_rate": _to_float(data.get("activation_rate"), 30.0) or 30.0,
        "cac": _to_float(data.get("cac"), 200.0) or 200.0,
        "ltv": _to_float(data.get("ltv"), 1200.0) or 1200.0,
        "fundraising_status": str(data.get("fundraising_status") or "bootstrapped").strip().lower(),
        "primary_goal": str(data.get("primary_goal") or "reach profitability").strip(),
        "key_constraint": str(data.get("key_constraint") or "limited runway").strip(),
        "users": _to_int(data.get("users"), None),
    }
