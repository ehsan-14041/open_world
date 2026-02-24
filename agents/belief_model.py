"""
Advanced Belief Modeling Layer: structured belief-aware agents.
Lightweight probabilistic belief tracking, fully explainable; no deep learning or vector stores.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Callable

# Default baseline uncertainty (entropy-like) per key when not set
DEFAULT_UNCERTAINTY = 0.3
UNCERTAINTY_CAP = 1.0
UNCERTAINTY_FLOOR = 0.05


class BeliefState:
    """
    Structured belief state: strength per proposition/variable,
    entropy-like uncertainty per key, and global confidence.
    """

    __slots__ = ("beliefs", "uncertainty", "confidence")

    def __init__(
        self,
        beliefs: dict[str, float] | None = None,
        uncertainty: dict[str, float] | None = None,
        confidence: float = 0.5,
    ) -> None:
        self.beliefs: dict[str, float] = dict(beliefs or {})
        self.uncertainty: dict[str, float] = dict(uncertainty or {})
        self.confidence: float = max(0.0, min(1.0, float(confidence)))
        for k in self.beliefs:
            if k not in self.uncertainty:
                self.uncertainty[k] = DEFAULT_UNCERTAINTY

    def copy(self) -> BeliefState:
        return BeliefState(
            beliefs=dict(self.beliefs),
            uncertainty=dict(self.uncertainty),
            confidence=self.confidence,
        )


def belief_state_from_memory_beliefs(memory_beliefs: dict[str, Any]) -> BeliefState:
    """
    Build BeliefState from existing AgentMemory.beliefs (variables + confidence).
    belief strength = variables; uncertainty = 1 - per_var_confidence, global confidence = mean(confidence).
    """
    variables = memory_beliefs.get("variables") or {}
    conf_per_var = memory_beliefs.get("confidence") or {}
    if not isinstance(variables, dict):
        variables = {}
    if not isinstance(conf_per_var, dict):
        conf_per_var = {}
    beliefs = {k: float(v) for k, v in variables.items() if isinstance(v, (int, float))}
    uncertainty = {}
    for k in beliefs:
        c = conf_per_var.get(k)
        if isinstance(c, (int, float)):
            uncertainty[k] = max(UNCERTAINTY_FLOOR, min(UNCERTAINTY_CAP, 1.0 - float(c)))
        else:
            uncertainty[k] = DEFAULT_UNCERTAINTY
    confidence = 0.5
    if conf_per_var:
        vals = [float(c) for c in conf_per_var.values() if isinstance(c, (int, float))]
        if vals:
            confidence = sum(vals) / len(vals)
    return BeliefState(beliefs=beliefs, uncertainty=uncertainty, confidence=confidence)


def belief_alignment(
    action_type: str,
    belief_state: BeliefState,
    rule_based_deltas: dict[str, dict[str, float]] | None = None,
    get_delta: Callable[[str], Any] | None = None,
) -> float:
    """
    Score in [0, 1] for consistency of action with agent beliefs.
    Action that moves variable toward believed value is rewarded; contradictory penalized.
    No LLM; uses rule_based_deltas or get_delta to infer direction of change.
    """
    if not belief_state.beliefs:
        return 0.5
    delta_map: dict[str, float] = {}
    if rule_based_deltas and action_type in rule_based_deltas:
        delta_map = dict(rule_based_deltas[action_type])
    elif get_delta and callable(get_delta):
        d = get_delta(action_type)
        if d is not None:
            if hasattr(d, "numeric_updates") and d.numeric_updates:
                delta_map = dict(d.numeric_updates)
            elif isinstance(d, dict):
                delta_map = dict(d.get("numeric_updates") or d)
    if not delta_map:
        return 0.5
    alignments: list[float] = []
    for var, delta in delta_map.items():
        if not isinstance(delta, (int, float)):
            continue
        belief_val = belief_state.beliefs.get(var)
        if belief_val is None:
            alignments.append(0.5)
            continue
        # Heuristic: if we believe var is "high", increase_var is aligned; decrease_var is contradictory.
        # Generic: alignment = how much the delta moves state toward belief (simplified: sign agreement with objective direction).
        # Simple rule: action that increases var when belief is high -> good; decrease when belief is low -> good.
        # We don't have "target" so use: consistency = 1 - (penalty for large deviation). 
        # Simpler: reward same sign (delta and belief - 50) so increase when belief>50 is good.
        mid = 50.0
        belief_above = belief_val > mid
        delta_positive = float(delta) > 0
        if belief_above and delta_positive:
            alignments.append(1.0)
        elif not belief_above and not delta_positive:
            alignments.append(1.0)
        elif belief_above and not delta_positive:
            alignments.append(0.2)
        else:
            alignments.append(0.2)
    return sum(alignments) / len(alignments) if alignments else 0.5


def update_belief_state(
    belief_state: BeliefState,
    observation: dict[str, float],
    actual_delta: dict[str, float] | None = None,
    *,
    instability_mode: bool = False,
    shock_active: bool = False,
    world_entropy: float | None = None,
    belief_update_rate: float = 0.7,
) -> None:
    """
    Bayesian-lite update: weight adjustment toward observation; step size from confidence.
    belief_update_rate < 1.0 causes belief drift (beliefs lag world state).
    Increase uncertainty when entropy high, instability_mode true, or shock_active true.
    """
    observation = observation or {}
    actual_delta = actual_delta or {}
    step = (0.1 + 0.4 * belief_state.confidence) * max(0.01, min(1.0, float(belief_update_rate)))
    entropy_factor = 1.0
    if world_entropy is not None and world_entropy > 5.0:
        entropy_factor += 0.3
    if instability_mode:
        entropy_factor += 0.4
    if shock_active:
        entropy_factor += 0.5
    for var, obs_val in observation.items():
        if not isinstance(obs_val, (int, float)):
            continue
        obs_val = float(obs_val)
        prev = belief_state.beliefs.get(var)
        if prev is not None:
            belief_state.beliefs[var] = prev + step * (obs_val - prev)
        else:
            belief_state.beliefs[var] = obs_val
        u = belief_state.uncertainty.get(var, DEFAULT_UNCERTAINTY)
        belief_state.uncertainty[var] = min(UNCERTAINTY_CAP, u * entropy_factor)
    if actual_delta and belief_state.beliefs:
        for var, delta in actual_delta.items():
            if var in belief_state.beliefs and isinstance(delta, (int, float)):
                belief_state.beliefs[var] = belief_state.beliefs[var] + 0.2 * float(delta)
    conf_list = [1.0 - belief_state.uncertainty.get(k, DEFAULT_UNCERTAINTY) for k in belief_state.beliefs]
    belief_state.confidence = sum(conf_list) / len(conf_list) if conf_list else 0.5
    belief_state.confidence = max(0.0, min(1.0, belief_state.confidence))


def uncertainty_decay(belief_state: BeliefState, decay_rate: float = 0.95) -> None:
    """Decay uncertainty toward baseline each turn."""
    baseline = DEFAULT_UNCERTAINTY
    for k in list(belief_state.uncertainty):
        u = belief_state.uncertainty[k]
        belief_state.uncertainty[k] = max(UNCERTAINTY_FLOOR, u * decay_rate + baseline * (1 - decay_rate))


def shock_impact_on_belief_variance(belief_state: BeliefState, shock_intensity: float) -> None:
    """Scale uncertainty by shock intensity (lightweight)."""
    scale = 1.0 + max(0.0, min(1.0, float(shock_intensity))) * 0.8
    for k in list(belief_state.uncertainty):
        belief_state.uncertainty[k] = min(UNCERTAINTY_CAP, belief_state.uncertainty[k] * scale)


def belief_entropy_aggregate(belief_state: BeliefState) -> float:
    """Single entropy-like scalar from uncertainty dict (mean of uncertainties)."""
    if not belief_state.uncertainty:
        return 0.0
    return sum(belief_state.uncertainty.values()) / len(belief_state.uncertainty)


def dominant_belief(belief_state: BeliefState) -> tuple[str | None, float]:
    """Return (key with max belief strength, value)."""
    if not belief_state.beliefs:
        return (None, 0.0)
    k = max(belief_state.beliefs, key=lambda x: abs(belief_state.beliefs[x]))
    return (k, belief_state.beliefs[k])
