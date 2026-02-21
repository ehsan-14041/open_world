"""
Adaptive learning: strategy weight update; bounded and traceable. Objectives are never overwritten.
"""

from learning.adaptive_kernel import (
    update_strategy_weights,
    DEFAULT_LEARNING_RATE,
)

__all__ = ["update_strategy_weights", "DEFAULT_LEARNING_RATE"]
