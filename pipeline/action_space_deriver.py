"""
Action Space Deriver: infers allowed actions from variables, causal graph, and incentives.
Replaces static allowed_actions_from_variables.
"""

from __future__ import annotations

from typing import Any


class ActionSpaceDeriver:
    """Derive action space from discovered model components."""

    @staticmethod
    def derive(
        variables: dict[str, float],
        causal_graph: list[dict[str, Any]],
        incentives: dict[str, dict[str, Any]],
        entities: list[dict[str, Any]],
    ) -> list[str]:
        """
        Derive allowed actions from variables, causal graph, and incentives.
        Returns list of action strings.
        """
        actions: set[str] = set()
        var_names = list(variables.keys())

        # Variable-driven actions: increase_X, decrease_X for each variable
        for v in var_names:
            actions.add(f"increase_{v}")
            actions.add(f"decrease_{v}")

        # Strategic actions from incentives (objectives that imply high-level actions)
        for ent_name, inc in incentives.items():
            obj = inc.get("objectives") or {}
            for key in obj:
                if key.startswith("increase_") or key.startswith("decrease_"):
                    actions.add(key)

        # Add domain-specific strategic actions based on variable names
        strategic = _infer_strategic_actions(variables, causal_graph)
        actions.update(strategic)

        # Generic adjust
        actions.add("adjust_variable")

        return sorted(actions)


def _infer_strategic_actions(
    variables: dict[str, float],
    causal_graph: list[dict[str, Any]],
) -> list[str]:
    """Infer 2-4 high-level strategic actions from variable names."""
    var_names = [v.lower() for v in variables.keys()]
    strategic: list[str] = []

    # Common patterns from variable names
    if any("tension" in v or "conflict" in v for v in var_names):
        strategic.extend(["deescalate", "propose_ceasefire", "hold_position"])
    if any("negotiation" in v or "progress" in v for v in var_names):
        strategic.extend(["increase_negotiation", "minor_concession"])
    if any("stability" in v or "trust" in v for v in var_names):
        strategic.extend(["build_trust", "stabilize"])
    if any("resource" in v or "cash" in v or "growth" in v for v in var_names):
        strategic.extend(["request_investment", "launch_discount_campaign", "cut_costs"])

    # Deduplicate and limit
    seen = set()
    out = []
    for s in strategic:
        if s not in seen and s not in variables:
            seen.add(s)
            out.append(s)
    return out[:4]
