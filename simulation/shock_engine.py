"""
Shock-Driven Global Simulation Mode: macro shock events (supply chain, financial,
political instability, information warfare). Probabilistically trigger shocks;
amplify entropy, perturb beliefs, degrade calibration, increase tail risk.
Lightweight: no nested Monte Carlo; simple parameterized deltas on world variables.
"""

from __future__ import annotations

import random
from typing import Any

# Macro shock type labels
SHOCK_SUPPLY_CHAIN = "supply_chain_shock"
SHOCK_FINANCIAL = "financial_shock"
SHOCK_POLITICAL = "political_instability"
SHOCK_INFO_WARFARE = "information_warfare"

# Default variable targets per shock type (can be overridden by world.variables keys)
_DEFAULT_SHOCK_TARGETS: dict[str, list[str]] = {
    SHOCK_SUPPLY_CHAIN: ["supply", "capacity", "inventory", "growth"],
    SHOCK_FINANCIAL: ["liquidity", "growth", "stability", "debt"],
    SHOCK_POLITICAL: ["stability", "dissatisfaction", "trust"],
    SHOCK_INFO_WARFARE: ["trust", "stability", "dissatisfaction"],
}


def _resolve_targets(world: Any, shock_type: str) -> list[str]:
    """Return variable names that exist in world and match the shock type targets."""
    variables = getattr(world, "variables", None)
    if not isinstance(variables, dict):
        return []
    world_vars = set(variables.keys())
    candidates = _DEFAULT_SHOCK_TARGETS.get(shock_type, [])
    return [v for v in candidates if v in world_vars] or list(world_vars)[:3]


def step_shock_engine(
    world: Any,
    turn: int,
    rng: random.Random | None = None,
    *,
    intensity: float = 0.3,
    frequency: float = 0.15,
    mode: str = "standard",
) -> dict[str, Any]:
    """
    If mode != "shock_global", return {"active": False}.
    Else probabilistically trigger one or more macro shocks; apply to world.variables;
    scale impact by intensity. Return {"active": True, "shocks": [...], "intensity": ..., "impact_delta": {var: delta}}.
    No nested heavy Monte Carlo; single draw per shock type.
    """
    if (mode or "standard").strip().lower() != "shock_global":
        return {"active": False, "shocks": [], "impact_delta": {}}
    rng = rng or random.Random()
    variables = getattr(world, "variables", None)
    if not isinstance(variables, dict):
        return {"active": False, "shocks": [], "impact_delta": {}}
    shock_types = [SHOCK_SUPPLY_CHAIN, SHOCK_FINANCIAL, SHOCK_POLITICAL, SHOCK_INFO_WARFARE]
    triggered: list[str] = []
    impact_delta: dict[str, float] = {}
    for st in shock_types:
        if rng.random() > frequency:
            continue
        targets = _resolve_targets(world, st)
        if not targets:
            continue
        triggered.append(st)
        # Magnitude: scale by intensity; negative for stability/dissatisfaction/trust (degradation)
        mag = (rng.gauss(0, 1.5) * intensity) * 2.0
        for var in targets:
            if var not in variables:
                continue
            current = variables.get(var)
            if not isinstance(current, (int, float)):
                continue
            # Direction: for "stability", "trust" we want negative shock effect; for "dissatisfaction" positive
            if var in ("stability", "trust"):
                delta = -abs(mag) * (0.5 + 0.5 * rng.random())
            elif var == "dissatisfaction":
                delta = abs(mag) * (0.5 + 0.5 * rng.random())
            else:
                delta = mag * (rng.random() - 0.3)
            variables[var] = current + delta
            impact_delta[var] = impact_delta.get(var, 0.0) + delta
    return {
        "active": len(triggered) > 0,
        "shocks": triggered,
        "intensity": intensity,
        "impact_delta": impact_delta,
    }
