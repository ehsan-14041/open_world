"""
Adaptive learning: strategy_weights(t+1) = f(strategy_weights(t), expected_outcome, actual_outcome, learning_rate, memory).
Do NOT overwrite objectives; only adjust action-preference/strategy weights. Bounded and traceable.
"""

from __future__ import annotations

from typing import Any

DEFAULT_LEARNING_RATE = 0.1
MIN_WEIGHT = 0.01
MAX_WEIGHT = 2.0


def update_strategy_weights(
    strategy_weights: dict[str, float],
    strategy_class: str,
    expected_utility: float,
    actual_utility: float,
    *,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    memory: list[dict[str, Any]] | None = None,
) -> dict[str, float]:
    """
    Update strategy_weights for strategy_class based on expected vs actual outcome.
    Returns new dict; does not mutate input. Weights clamped to [MIN_WEIGHT, MAX_WEIGHT].
    """
    out = dict(strategy_weights)
    current = out.get(strategy_class, 1.0)
    delta_u = actual_utility - expected_utility
    update = learning_rate * delta_u
    new_val = current + update
    new_val = max(MIN_WEIGHT, min(MAX_WEIGHT, new_val))
    out[strategy_class] = new_val
    return out


def update_strategy_weights_in_place(
    strategy_weights: dict[str, float],
    strategy_class: str,
    expected_utility: float,
    actual_utility: float,
    *,
    learning_rate: float = DEFAULT_LEARNING_RATE,
) -> None:
    """Mutate strategy_weights in place."""
    delta_u = actual_utility - expected_utility
    current = strategy_weights.get(strategy_class, 1.0)
    new_val = current + learning_rate * delta_u
    strategy_weights[strategy_class] = max(MIN_WEIGHT, min(MAX_WEIGHT, new_val))
