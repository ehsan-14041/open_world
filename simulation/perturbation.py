"""
Scenario perturbation for the Robustness & Failure-Mode engine.

Core idea: we do NOT pretend to know the causal coefficients, agent priorities,
or exact starting conditions. We *sweep* them. Each ensemble member receives a
perturbed copy of the scenario; aggregating across members reveals how much the
conclusion depends on each uncertain assumption.

This module is a pure function over data — it does not run the simulation and
does not modify the original scenario.
"""

from __future__ import annotations

import copy
import random
from typing import Any


# Default jitter ranges (fractional, ±). All identity (0.0) means "no perturbation".
# distribution: "truncated_gaussian" (default) concentrates samples near the center
# (small deviations more likely, as in a real belief) while keeping bounded support
# at ±frac (= ±2σ); "uniform" gives flat coverage of the range (more tail probing).
DEFAULT_PERTURB_CONFIG: dict[str, Any] = {
    "causal_jitter": 0.40,      # ± on causal link strength/weight — the primary sweep
    "objective_jitter": 0.30,   # ± on agent objective weights
    "state_jitter": 0.15,       # ± on numeric initial_state values
    "distribution": "truncated_gaussian",
}


def _sample_multiplier(frac: float, rng: random.Random, distribution: str) -> float:
    """Return a perturbation multiplier in [1-frac, 1+frac]."""
    if frac <= 0:
        return 1.0
    if distribution == "uniform":
        return 1.0 + rng.uniform(-frac, frac)
    # truncated gaussian: sigma chosen so ±2σ == ±frac, then clamp to that bound.
    sigma = frac / 2.0
    delta = rng.gauss(0.0, sigma)
    delta = max(-frac, min(frac, delta))  # truncate to bounded support
    return 1.0 + delta


def _jitter(value: float, frac: float, rng: random.Random, distribution: str = "truncated_gaussian") -> tuple[float, float]:
    """Return (new_value, multiplier) where multiplier in [1-frac, 1+frac]."""
    mult = _sample_multiplier(frac, rng, distribution)
    return value * mult, mult


def perturb_scenario(
    scenario: dict[str, Any],
    rng: random.Random,
    config: dict[str, float] | None = None,
) -> tuple[dict[str, Any], dict[str, float]]:
    """
    Return (perturbed_scenario_copy, perturbation_record).

    perturbation_record maps a dimension name -> the multiplier applied, used
    later to correlate inputs with outcomes (pivotal-assumption detection).
    Dimension names:
      causal:<from>-><to>     causal link strength
      obj:<agent>:<key>       agent objective weight
      state:<var>             initial_state numeric value
    """
    cfg = {**DEFAULT_PERTURB_CONFIG, **(config or {})}
    dist = str(cfg.get("distribution", "truncated_gaussian"))
    sc = copy.deepcopy(scenario or {})
    record: dict[str, float] = {}

    # 1. Causal link strengths (primary sweep)
    cj = float(cfg.get("causal_jitter", 0.0))
    for link in sc.get("causal_links") or []:
        if not isinstance(link, dict):
            continue
        frm = link.get("from")
        to = link.get("to")
        if not frm or not to:
            continue
        key = f"causal:{frm}->{to}"
        if isinstance(link.get("weight"), (int, float)):
            new_v, mult = _jitter(float(link["weight"]), cj, rng, dist)
            link["weight"] = new_v
            record[key] = mult
        elif isinstance(link.get("strength"), (int, float)):
            new_v, mult = _jitter(float(link["strength"]), cj, rng, dist)
            # keep strength within a sane [0, 1] band but allow the sweep
            link["strength"] = max(0.0, min(1.0, new_v))
            record[key] = mult

    # 2. Agent objective weights (re-normalized to preserve total weight)
    oj = float(cfg.get("objective_jitter", 0.0))
    for agent in sc.get("initial_agents") or []:
        if not isinstance(agent, dict):
            continue
        name = agent.get("name") or "agent"
        objectives = agent.get("objectives")
        if not isinstance(objectives, dict) or not objectives:
            continue
        original_total = sum(float(v) for v in objectives.values() if isinstance(v, (int, float)))
        jittered: dict[str, float] = {}
        for k, v in objectives.items():
            if isinstance(v, (int, float)):
                new_v, mult = _jitter(float(v), oj, rng, dist)
                jittered[k] = max(0.0, new_v)
                record[f"obj:{name}:{k}"] = mult
            else:
                jittered[k] = v
        # Re-normalize numeric weights back to the original total
        new_total = sum(val for val in jittered.values() if isinstance(val, (int, float)))
        if original_total > 0 and new_total > 0:
            scale = original_total / new_total
            for k in jittered:
                if isinstance(jittered[k], (int, float)):
                    jittered[k] = jittered[k] * scale
        agent["objectives"] = jittered

    # 3. Initial conditions
    sj = float(cfg.get("state_jitter", 0.0))
    state = sc.get("initial_state")
    if isinstance(state, dict):
        for var, v in list(state.items()):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                new_v, mult = _jitter(float(v), sj, rng, dist)
                state[var] = new_v
                record[f"state:{var}"] = mult

    return sc, record
