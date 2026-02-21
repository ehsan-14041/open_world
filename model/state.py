"""
Snapshot versioning, world_state vs belief_state shapes.
Domain-agnostic; values conform to ValueSpec (including null/unknown).
"""

from __future__ import annotations

import copy
from typing import Any


def create_versioned_snapshot(
    variables: dict[str, Any],
    *,
    causal_links: list[dict[str, Any]] | None = None,
    entities: dict[str, Any] | None = None,
    relations: list[dict[str, Any]] | None = None,
    version: int = 0,
    turn: int = 0,
    **extra: Any,
) -> dict[str, Any]:
    snap: dict[str, Any] = {
        "variables": copy.deepcopy(variables or {}),
        "global_state": copy.deepcopy(variables or {}),
        "causal_links": list(causal_links or []),
        "entities": dict(entities or {}),
        "relations": list(relations or []),
        "version": version,
        "turn": turn,
    }
    for k, v in extra.items():
        if k not in snap:
            snap[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v
    return snap


def clone_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(snapshot)
    if "variables" in out and "global_state" not in out:
        out["global_state"] = out["variables"]
    if "global_state" in out and "variables" not in out:
        out["variables"] = out["global_state"]
    return out


def belief_state_shape(variables: dict[str, Any], variable_specs: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"variables": {}, "confidence": {}}
    for var_id in variables.keys():
        out["variables"][var_id] = variables.get(var_id)
        out["confidence"][var_id] = 0.6
    return out


def commit_snapshot(world: Any, *, version_increment: bool = True) -> dict[str, Any]:
    version = getattr(world, "version", 0)
    turn = getattr(world, "turn", 0)
    if version_increment:
        version += 1
    variables = getattr(world, "variables", None) or {}
    causal_links = getattr(world, "causal_links", None) or []
    entities = getattr(world, "entities", None) or {}
    relations = getattr(world, "relations", None) or []
    return create_versioned_snapshot(
        dict(variables),
        causal_links=list(causal_links),
        entities=dict(entities),
        relations=list(relations),
        version=version,
        turn=turn,
    )
