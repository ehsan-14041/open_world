"""
Thin helper for cloning world state (for planning/simulation). No dependency on agents.
"""

from __future__ import annotations

import copy
from typing import Any


def clone_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of world snapshot for simulation only (no side effects on real world). Includes variables, causal_links; global_state is alias of variables for planners."""
    variables = copy.deepcopy(snapshot.get("variables") or snapshot.get("global_state") or {})
    return {
        "entities": copy.deepcopy(snapshot.get("entities") or {}),
        "relations": copy.deepcopy(snapshot.get("relations") or []),
        "variables": variables,
        "global_state": variables,
        "causal_links": copy.deepcopy(snapshot.get("causal_links") or []),
        "narrative": list(snapshot.get("narrative") or []),
        "ontology": dict(snapshot.get("ontology") or {}),
        "version": int(snapshot.get("version", 0)),
        "turn": int(snapshot.get("turn", 0)),
    }
