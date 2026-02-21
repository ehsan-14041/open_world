"""
Action DSL: universal, domain-agnostic ops.
"""

from __future__ import annotations

from typing import Any

try:
    from model.valuespec import ORDINAL_LEVELS, _ordinal_index, _ordinal_delta
except ImportError:
    ORDINAL_LEVELS = ["very_low", "low", "medium", "high", "very_high"]
    def _ordinal_index(level: str) -> int:
        s = (level or "").strip().lower().replace(" ", "_")
        for i, lbl in enumerate(ORDINAL_LEVELS):
            if lbl == s: return i
        return 2
    def _ordinal_delta(direction: str, intensity: str) -> int:
        d = (direction or "").strip().lower()
        mag = max(0, min(4, _ordinal_index(intensity or "medium")))
        if d in ("increase", "up", "raise", "1"): return 1 + (mag // 2)
        if d in ("decrease", "down", "lower", "reduce", "-1"): return -(1 + (mag // 2))
        if d in ("stabilize", "stable", "0"): return 0
        if d == "shift": return 1 if mag >= 2 else -1
        return 0

DSL_OPS = frozenset({"intervene", "allocate", "communicate", "probe", "modify_constraint", "create_relation", "dissolve_relation", "noop"})
DEFAULT_MAGNITUDE = 5.0

def _magnitude_from_intensity(intensity: Any, default: float = DEFAULT_MAGNITUDE) -> float:
    if intensity is None: return default
    if isinstance(intensity, (int, float)): return max(0.1, float(intensity))
    idx = _ordinal_index(str(intensity))
    return default * (0.5 + 0.5 * idx / max(1, len(ORDINAL_LEVELS) - 1))

def interpret_dsl(action: dict, variable_specs=None, variables=None):
    if not isinstance(action, dict): return None
    op = (action.get("op") or action.get("type") or "").strip().lower()
    if op not in DSL_OPS: return None
    args = action.get("args") or action
    rationale = args.get("rationale") or action.get("rationale") or ""
    delta_raw = {}
    relation_updates = []
    if op == "noop":
        return {"delta_raw": {}, "relation_updates": [], "rationale": rationale}
    if op == "intervene":
        variable = args.get("variable") or args.get("target")
        if not variable: return None
        direction = (args.get("direction") or "increase").strip().lower()
        intensity = args.get("intensity") or args.get("magnitude") or "medium"
        mag = _magnitude_from_intensity(intensity)
        if direction in ("increase", "up", "raise", "1"): delta_raw[variable] = mag
        elif direction in ("decrease", "down", "lower", "reduce", "-1"): delta_raw[variable] = -mag
        elif direction in ("stabilize", "stable", "0"): delta_raw[variable] = 0
        else: delta_raw[variable] = mag
        return {"delta_raw": delta_raw, "relation_updates": [], "rationale": rationale}
    if op == "allocate":
        source, target = args.get("source"), args.get("target") or args.get("variable")
        level = args.get("level_or_amount") or args.get("level") or "medium"
        amount = _magnitude_from_intensity(level)
        if source and target: delta_raw[source], delta_raw[target] = -amount, amount
        elif target: delta_raw[target] = amount
        return {"delta_raw": delta_raw, "relation_updates": [], "rationale": rationale}
    if op in ("communicate", "probe"):
        return {"delta_raw": {}, "relation_updates": [], "rationale": rationale}
    if op == "modify_constraint":
        cid = args.get("constraint_id") or args.get("constraint")
        if cid and isinstance(variables, dict) and cid in variables:
            direction = (args.get("tighten") or args.get("direction") or "loosen").strip().lower()
            delta_raw[cid] = -DEFAULT_MAGNITUDE * 0.5 if "tighten" in direction or direction == "tighten" else DEFAULT_MAGNITUDE * 0.5
        return {"delta_raw": delta_raw, "relation_updates": [], "rationale": rationale}
    if op == "create_relation":
        a, b = args.get("a") or args.get("source"), args.get("b") or args.get("target")
        if a and b: relation_updates.append({"op": "create", "a": a, "b": b, "relation_type": args.get("relation_type") or "relation", "strength": args.get("strength")})
        return {"delta_raw": delta_raw, "relation_updates": relation_updates, "rationale": rationale}
    if op == "dissolve_relation":
        a, b = args.get("a") or args.get("source"), args.get("b") or args.get("target")
        if a and b: relation_updates.append({"op": "dissolve", "a": a, "b": b, "relation_type": args.get("relation_type") or "relation"})
        return {"delta_raw": delta_raw, "relation_updates": relation_updates, "rationale": rationale}
    return None

def dsl_to_delta_raw(action: dict, variable_specs=None, variables=None):
    result = interpret_dsl(action, variable_specs=variable_specs, variables=variables)
    return (result.get("delta_raw") or {}) if result else {}
