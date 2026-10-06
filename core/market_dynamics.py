"""
Market Dynamics Library (Phase 4 — shocks, contagion, network effects).

Phase 4 does NOT rewrite the engine. It adds *declarative* market primitives on top of
the existing rule engine so a scenario can express supply/demand/external shocks,
probabilistic shocks, and contagion cascades in pure JSON — grounded in the same
condition/effect contract as `core/threshold_rules.py`.

New CONDITION primitives (effects reuse threshold_rules' `scale_var` / `add_to_var`):
  - at_turn         params {turn}            fires once on that turn
  - after_turn      params {turn}            fires every turn >= turn (sustained shock)
  - with_probability params {p}              fires stochastically (seeded per ensemble member)

Network effects are reinforcing causal loops (causal_links cycles); contagion is a chain
of threshold rules where one variable crossing a bound trips the next. Builders below
emit the rule dicts so authors don't hand-write them.

Determinism: `with_probability` uses the global RNG, which the ensemble seeds per member
(`run_member`) and single runs pin via `RANDOM_SEED` — so shocks are reproducible.
"""

from __future__ import annotations

import random
from typing import Any

from core.rule_engine import register_condition

# ensure scale_var / add_to_var effects exist (threshold_rules registers them on import)
import core.threshold_rules  # noqa: F401


def _turn(snapshot: dict[str, Any]) -> int | None:
    t = (snapshot or {}).get("turn")
    return int(t) if isinstance(t, (int, float)) else None


# ---------------- conditions ----------------

def cond_at_turn(snapshot: dict[str, Any], params: dict[str, Any]) -> bool:
    """True exactly on the turn given by params['turn']."""
    t = _turn(snapshot)
    target = params.get("turn")
    return t is not None and isinstance(target, (int, float)) and t == int(target)


def cond_after_turn(snapshot: dict[str, Any], params: dict[str, Any]) -> bool:
    """True on every turn >= params['turn'] (a sustained shock/regime)."""
    t = _turn(snapshot)
    target = params.get("turn")
    return t is not None and isinstance(target, (int, float)) and t >= int(target)


def cond_with_probability(snapshot: dict[str, Any], params: dict[str, Any]) -> bool:
    """Fire stochastically with probability params['p'] (global RNG; seeded per member)."""
    p = params.get("p")
    if not isinstance(p, (int, float)):
        return False
    return random.random() < float(p)


_REGISTERED = False


def register_market_primitives() -> None:
    """Register market condition primitives (idempotent)."""
    global _REGISTERED
    if _REGISTERED:
        return
    register_condition("at_turn", cond_at_turn)
    register_condition("after_turn", cond_after_turn)
    register_condition("with_probability", cond_with_probability)
    _REGISTERED = True


# ---------------- declarative builders (emit rule dicts) ----------------

def supply_shock(turn: int, target: str, factor: float = 0.6, *, id: str | None = None) -> dict[str, Any]:
    """One-time multiplicative hit to a supply-side variable at `turn` (e.g. capacity ×0.6)."""
    return {
        "id": id or f"supply_shock_{target}_{turn}",
        "condition_key": "at_turn", "effect_key": "scale_var",
        "params": {"turn": int(turn), "target": target, "factor": float(factor)},
    }


def demand_shock(turn: int, target: str, amount: float, *, id: str | None = None) -> dict[str, Any]:
    """One-time additive shift to a demand variable at `turn` (e.g. demand −120)."""
    return {
        "id": id or f"demand_shock_{target}_{turn}",
        "condition_key": "at_turn", "effect_key": "add_to_var",
        "params": {"turn": int(turn), "target": target, "amount": float(amount)},
    }


def probabilistic_shock(p: float, target: str, factor: float = 0.7, *, id: str | None = None) -> dict[str, Any]:
    """Each turn, with probability `p`, multiply `target` by `factor` (random external event)."""
    return {
        "id": id or f"prob_shock_{target}",
        "condition_key": "with_probability", "effect_key": "scale_var",
        "params": {"p": float(p), "target": target, "factor": float(factor)},
    }


def contagion_cascade(chain: list[str], threshold: float, factor: float = 0.7) -> list[dict[str, Any]]:
    """
    Emit a contagion chain: when variable i crosses `threshold`, variable i+1 is hit
    (×factor). Models a failure spreading through coupled variables — the non-linear
    counterpart to a reinforcing causal loop.
    """
    rules: list[dict[str, Any]] = []
    for i in range(len(chain) - 1):
        src, dst = chain[i], chain[i + 1]
        rules.append({
            "id": f"contagion_{src}_to_{dst}",
            "condition_key": "var_above", "effect_key": "scale_var",
            "params": {"var": src, "threshold": float(threshold), "target": dst, "factor": float(factor)},
        })
    return rules


# Register on import so primitives are available wherever rules run.
register_market_primitives()
