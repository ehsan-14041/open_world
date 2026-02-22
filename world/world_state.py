"""
Thin helper for cloning world state (for planning/simulation). No dependency on agents.
Canonical cloning: use clone_world_state(snapshot, include_causal_links=...) only; no other deep copies of world state.
"""

from __future__ import annotations

import copy
from typing import Any


def clone_world_state(snapshot: dict[str, Any], *, include_causal_links: bool = False) -> dict[str, Any]:
    """
    Canonical world state clone. Use this for all cloning; avoid deep copies elsewhere.
    - Planning: call with include_causal_links=False (structural state only, no causal_links).
    - Execution / full state: call with include_causal_links=True (includes causal_links for propagation).
    """
    variables = copy.deepcopy(snapshot.get("variables") or snapshot.get("global_state") or {})
    out: dict[str, Any] = {
        "entities": copy.deepcopy(snapshot.get("entities") or {}),
        "relations": copy.deepcopy(snapshot.get("relations") or []),
        "variables": variables,
        "global_state": variables,
        "narrative": list(snapshot.get("narrative") or []),
        "ontology": dict(snapshot.get("ontology") or {}),
        "version": int(snapshot.get("version", 0)),
        "turn": int(snapshot.get("turn", 0)),
    }
    if include_causal_links:
        out["causal_links"] = copy.deepcopy(snapshot.get("causal_links") or [])
    return out


def clone_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a full deep copy of world snapshot (includes causal_links). Thin wrapper around clone_world_state(..., include_causal_links=True)."""
    return clone_world_state(snapshot, include_causal_links=True)
