"""
Synthesizer: Expected Utility and action diversity (v2.5 anti-toxic conservatism).
"""

from __future__ import annotations


def expected_utility(
    reward_potential: float,
    probability_of_success: float,
    tail_risk: float,
    probability_of_failure: float,
) -> float:
    """EU = (Reward_Potential * P_success) - (Tail_Risk * P_failure)."""
    return (reward_potential * probability_of_success) - (tail_risk * probability_of_failure)


def ensure_action_diversity(
    candidates: list[str],
    scores: dict[str, float],
    min_size: int = 2,
) -> list[str]:
    """Retain at least min_size options (top by score) to avoid single safe action."""
    if not candidates or len(candidates) <= min_size:
        return list(candidates)
    ordered = sorted(candidates, key=lambda a: scores.get(a, float("-inf")), reverse=True)
    return ordered[:min_size]
