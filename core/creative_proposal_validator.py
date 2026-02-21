"""
Creative proposal validator: validate propose_action/event/rule from weak model.
Rejects unknown variables, numeric literals in effects. Qualitative only: magnitude, direction.
"""

from __future__ import annotations

from typing import Any

VALID_MAGNITUDES = {"tiny", "small", "medium", "large"}
VALID_DIRECTIONS = {"up", "down"}


def validate_creative_proposal(
    proposal: dict[str, Any],
    known_variables: set[str],
    proposal_type: str = "propose_action",
) -> tuple[bool, list[str]]:
    """
    Validate creative proposal. Returns (valid, errors).
    Rejects: unknown variables, numeric literals in effects, invalid magnitude/direction.
    """
    errors: list[str] = []

    if proposal_type == "propose_action":
        effects = proposal.get("effects") or []
        if not isinstance(effects, list):
            errors.append("effects must be a list")
            return False, errors
        for i, eff in enumerate(effects):
            if not isinstance(eff, dict):
                errors.append(f"effects[{i}] must be an object")
                continue
            var = eff.get("var") or eff.get("variable")
            if not var or not isinstance(var, str):
                errors.append(f"effects[{i}] must have var/variable")
                continue
            if known_variables and var not in known_variables:
                errors.append(f"effects[{i}] references unknown variable '{var}'")
            mag = eff.get("magnitude")
            if mag is not None and str(mag).lower() not in VALID_MAGNITUDES:
                errors.append(f"effects[{i}] magnitude must be one of {VALID_MAGNITUDES}")
            direction = eff.get("direction")
            if direction is not None and str(direction).lower() not in VALID_DIRECTIONS:
                errors.append(f"effects[{i}] direction must be one of {VALID_DIRECTIONS}")
            if isinstance(eff.get("delta"), (int, float)):
                errors.append(f"effects[{i}] must not contain numeric delta (use magnitude+direction)")
            if isinstance(eff.get("change"), (int, float)):
                errors.append(f"effects[{i}] must not contain numeric change (use magnitude+direction)")

        if not proposal.get("capability_tags"):
            errors.append("capability_tags required")
        if not proposal.get("strategy_class"):
            errors.append("strategy_class required")
        if not proposal.get("rationale"):
            errors.append("rationale required")

    elif proposal_type == "propose_event":
        effects = proposal.get("effects") or []
        if isinstance(effects, list):
            for i, eff in enumerate(effects):
                if isinstance(eff, dict):
                    var = eff.get("var") or eff.get("variable")
                    if var and known_variables and var not in known_variables:
                        errors.append(f"effects[{i}] references unknown variable '{var}'")

    return len(errors) == 0, errors


def has_numeric_literal_in_effects(proposal: dict[str, Any]) -> bool:
    """Check if proposal contains numeric literals in effects (reject for firewall)."""
    effects = proposal.get("effects") or []
    if not isinstance(effects, list):
        return False
    for eff in effects:
        if not isinstance(eff, dict):
            continue
        if isinstance(eff.get("delta"), (int, float)):
            return True
        if isinstance(eff.get("change"), (int, float)):
            return True
    return False
