"""
Directional abstract templates for domain-agnostic narrative generation.
Focus on relational shifts and state transitions; no hardcoded domain strings.
"""

from __future__ import annotations

from typing import Any

# Relational: A and B direction
RELATIONAL_OPPOSITE = "{A} and {B} moved in opposite directions."
RELATIONAL_OPPOSITE_CAUSAL = "As a result, {A} rose while {B} fell, which triggered competing pressures."
RELATIONAL_OPPOSITE_BECAUSE = "Because {A} increased while {B} decreased, the system experienced a clear tradeoff."
RELATIONAL_COMOVED = "{A} and {B} co-moved."

# State transitions
STATE_TRANSITION = "State shifted from {phase_old} to {phase_new}."
TURNING_POINT = "Turn {t} marked the turning point ({description}), leading to a new trajectory."

# Trajectory classification -> consequence framing (abstract)
TRAJECTORY_CONSEQUENCE: dict[str, str] = {
    "Escalation": "Structural stress increased and the system became more brittle.",
    "Stabilization": "The system settled into a more coherent configuration.",
    "Adaptation": "Agents and variables moved toward a more sustainable configuration.",
    "Fragmentation": "Divergent variable movements left the system structurally fragmented.",
    "Illusory improvement": "Surface gains in one dimension masked deterioration elsewhere.",
    "Stalemate": "No clear resolution emerged; the system remained in tension.",
}

TRAJECTORY_PATTERN = "The outcome fits a {trajectory_class} pattern."


def template(key: str, lang: str = "en", **params: Any) -> str:
    """
    Return a filled template string. Keys: relational_opposite, relational_opposite_causal,
    relational_opposite_because, relational_comoved, state_transition, turning_point,
    trajectory_consequence, trajectory_pattern.
    """
    key = (key or "").strip().lower()
    if key == "relational_opposite":
        s = RELATIONAL_OPPOSITE
    elif key == "relational_opposite_causal":
        s = RELATIONAL_OPPOSITE_CAUSAL
    elif key == "relational_opposite_because":
        s = RELATIONAL_OPPOSITE_BECAUSE
    elif key == "relational_comoved":
        s = RELATIONAL_COMOVED
    elif key == "state_transition":
        s = STATE_TRANSITION
    elif key == "turning_point":
        s = TURNING_POINT
    elif key == "trajectory_consequence":
        trajectory_class = params.get("trajectory_class") or "Stalemate"
        s = TRAJECTORY_CONSEQUENCE.get(trajectory_class, TRAJECTORY_CONSEQUENCE["Stalemate"])
        return s
    elif key == "trajectory_pattern":
        s = TRAJECTORY_PATTERN
    else:
        return ""
    for k, v in params.items():
        s = s.replace("{" + k + "}", str(v))
    return s
