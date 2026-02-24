"""
Monte Carlo evaluation and probabilistic action selection (LLM + MC + RL).
Lightweight: shallow sims on key state variables only; no neural networks.
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable

from agents.utility import utility_function
from agents.planner import apply_delta_to_state
from world.world_state import clone_world_state


def run_mc_evaluation(
    snapshot: dict[str, Any],
    candidates: list[str],
    get_delta: Callable[[str], Any] | None,
    rule_based_deltas: dict[str, dict[str, float]] | None,
    objectives: dict[str, float],
    beliefs: dict[str, Any],
    *,
    n_sims: int = 4,
) -> dict[str, float]:
    """
    MC value per action: average reward over n_sims shallow sims (key state only).
    Each sim: clone snapshot, apply action delta, compute utility; average.
    """
    mc_values: dict[str, float] = {}
    for action_type in candidates:
        rewards: list[float] = []
        for _ in range(n_sims):
            clone = clone_world_state(snapshot)
            if get_delta:
                d = get_delta(action_type)
                if d is None:
                    continue
                delta = d.to_dict() if hasattr(d, "to_dict") else d
            else:
                delta = {"numeric_updates": (rule_based_deltas or {}).get(action_type, {})}
            apply_delta_to_state(clone, delta)
            r = utility_function(clone, beliefs, objectives)
            rewards.append(r)
        mc_values[action_type] = sum(rewards) / len(rewards) if rewards else 0.0
    return mc_values


def get_planner_scores(
    snapshot: dict[str, Any],
    candidates: list[str],
    get_delta: Callable[[str], Any] | None,
    rule_based_deltas: dict[str, dict[str, float]] | None,
    objectives: dict[str, float],
    beliefs: dict[str, Any],
) -> dict[str, float]:
    """Planner/LLM score per candidate (one apply + utility)."""
    scores: dict[str, float] = {}
    for action_type in candidates:
        clone = clone_world_state(snapshot)
        if get_delta:
            d = get_delta(action_type)
            if d is None:
                continue
            delta = d.to_dict() if hasattr(d, "to_dict") else d
        else:
            delta = {"numeric_updates": (rule_based_deltas or {}).get(action_type, {})}
        apply_delta_to_state(clone, delta)
        scores[action_type] = utility_function(clone, beliefs, objectives)
    return scores


def softmax_select(
    candidates: list[str],
    llm_scores: dict[str, float],
    mc_values: dict[str, float],
    rl_weights: dict[str, float],
    *,
    w_llm: float = 0.4,
    w_mc: float = 0.4,
    temperature: float = 0.5,
    belief_scores: dict[str, float] | None = None,
    belief_weight: float = 0.0,
) -> str:
    """Combine LLM, MC, RL, and optional belief alignment with softmax; sample to preserve creativity."""
    try:
        from config.settings import MC_RL_TEMPERATURE_MIN
        temperature = max(float(temperature), MC_RL_TEMPERATURE_MIN)
    except ImportError:
        temperature = max(float(temperature), 0.1)
    def _norm(d: dict[str, float]) -> dict[str, float]:
        if not d:
            return d
        lo, hi = min(d.values()), max(d.values())
        span = (hi - lo) or 1.0
        return {k: (v - lo) / span for k, v in d.items()}

    n_llm = _norm(llm_scores)
    n_mc = _norm(mc_values)
    n_belief: dict[str, float] = {}
    if belief_scores and belief_weight > 0:
        n_belief = _norm(belief_scores)
    combined = []
    for a in candidates:
        s = w_llm * n_llm.get(a, 0) + w_mc * n_mc.get(a, 0) + rl_weights.get(a, 0.0)
        if n_belief is not None and belief_weight > 0:
            s += belief_weight * n_belief.get(a, 0.5)
        combined.append((a, s))
    logits = [s / max(temperature, 1e-6) for _, s in combined]
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    total = sum(exps)
    probs = [e / total for e in exps]
    actions = [a for a, _ in combined]
    return random.choices(actions, weights=probs, k=1)[0]
