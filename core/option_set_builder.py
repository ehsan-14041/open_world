"""
Deterministic OptionSet builder: max 3 actions, capability/availability filtering,
scoring by dot(objectives, delta_vector), safe stabilizer slot, creative slot.
Never fall back to full action list.
"""

from __future__ import annotations

from typing import Any

from schemas.meta_schema import evaluate_predicate


def _objectives_signed(objectives: dict[str, float], variables: set[str]) -> dict[str, float]:
    """Convert objectives to signed preferences over variables. increase_X -> +1 for X, decrease_X -> -1."""
    signed: dict[str, float] = {v: 0.0 for v in variables}
    for key, weight in objectives.items():
        if not isinstance(weight, (int, float)) or weight <= 0:
            continue
        key_lower = (key or "").lower()
        for var in variables:
            if f"increase_{var}" in key_lower or key_lower == f"increase_{var}":
                signed[var] = signed.get(var, 0) + weight
                break
            if f"decrease_{var}" in key_lower or key_lower == f"decrease_{var}":
                signed[var] = signed.get(var, 0) - weight
                break
            if key_lower == var:
                signed[var] = signed.get(var, 0) + weight * 0.5
                break
    return signed


def _eval_availability(
    conditions: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> bool:
    """Evaluate availability_conditions against snapshot. Empty = available."""
    import re
    if not conditions:
        return True
    vars_dict = snapshot.get("variables") or snapshot.get("global_state") or {}
    for c in conditions:
        if isinstance(c, dict) and "raw" in c:
            raw = (c.get("raw") or "").strip()
            if not raw:
                continue
            try:
                m = re.match(r"(\w+)\s*(>|<|>=|<=|==|!=)\s*([\d.]+)", raw)
                if m:
                    key, op, val_str = m.group(1), m.group(2), m.group(3)
                    actual = vars_dict.get(key)
                    val = float(val_str) if val_str.replace(".", "").isdigit() else None
                    if isinstance(actual, (int, float)) and isinstance(val, (int, float)):
                        if op == ">" and not (actual > val):
                            return False
                        if op == "<" and not (actual < val):
                            return False
                        if op == ">=" and not (actual >= val):
                            return False
                        if op == "<=" and not (actual <= val):
                            return False
                        if op == "==" and not (actual == val):
                            return False
                        if op == "!=" and not (actual != val):
                            return False
            except Exception:
                pass
        elif isinstance(c, dict) and ("key" in c or "fact" in c):
            if not evaluate_predicate(c, snapshot):
                return False
    return True


def build_option_set(
    agent_name: str,
    agent_capabilities: list[str],
    agent_objectives: dict[str, float],
    agent_risk_tolerance: float,
    strategy_class_weights: dict[str, float],
    action_definitions: dict[str, dict[str, Any]],
    snapshot: dict[str, Any],
    *,
    instability_mode: bool = False,
    newly_accepted_proposed_actions: list[str] | None = None,
) -> list[str]:
    """
    Build OptionSet of at most 3 action IDs.
    - Filter by capability_tags (match or general+stabilize)
    - Filter by availability_conditions
    - Score: dot(objectives_signed, delta_vector) - risk_penalty + strategy_bias
    - Select: top-2 by score + 1 safe stabilizer
    - Creative slot: 1 proposed action if relevant
    """
    variables = set((snapshot.get("variables") or snapshot.get("global_state") or {}).keys())
    agent_caps = set((c or "").lower() for c in (agent_capabilities or []))
    objectives_signed = _objectives_signed(agent_objectives, variables)

    # Filter by capability and availability
    candidates: list[tuple[str, dict[str, Any]]] = []
    for aid, adef in action_definitions.items():
        tags = set((t or "").lower() for t in (adef.get("capability_tags") or []))
        strat = (adef.get("strategy_class") or "general").lower()
        if tags and "general" not in tags and "stabilize" not in tags:
            if not (agent_caps & tags):
                continue
        if not _eval_availability(adef.get("availability_conditions") or [], snapshot):
            continue
        delta_vec = adef.get("delta_vector") or {}
        if not delta_vec:
            continue
        candidates.append((aid, adef))

    if not candidates:
        # Fallback: single stabilizer (min total |delta|)
        best = min(
            action_definitions.items(),
            key=lambda x: sum(abs(v) for v in (x[1].get("delta_vector") or {}).values()) or 1e9,
        )
        return [best[0]]

    # Score each candidate
    def score(aid: str, adef: dict[str, Any]) -> float:
        dv = adef.get("delta_vector") or {}
        dot_val = sum(objectives_signed.get(v, 0) * d for v, d in dv.items())
        strat = adef.get("strategy_class") or "general"
        bias = strategy_class_weights.get(strat, 0.0)
        total_delta = sum(abs(d) for d in dv.values())
        risk_penalty = 0.0
        if instability_mode and total_delta > 5:
            risk_penalty = (1.0 - agent_risk_tolerance) * total_delta * 0.1
        return dot_val - risk_penalty + bias

    scored = [(score(aid, adef), aid, adef) for aid, adef in candidates]
    scored.sort(key=lambda x: -x[0])

    # Safe stabilizer: min total |delta| or reduce most volatility-driving var
    def total_abs_delta(adef: dict[str, Any]) -> float:
        return sum(abs(v) for v in (adef.get("delta_vector") or {}).values())

    stabilizer = min(candidates, key=lambda x: total_abs_delta(x[1]))
    stabilizer_id = stabilizer[0]

    # Select: top-2 + stabilizer (if not in top-2)
    selected: list[str] = []
    for _, aid, _ in scored[:2]:
        if aid not in selected:
            selected.append(aid)
    if stabilizer_id not in selected:
        selected.append(stabilizer_id)

    # Creative slot: displace weakest non-stabilizer with proposed action if relevant
    newly = newly_accepted_proposed_actions or []
    for prop_id in newly:
        if prop_id in action_definitions and prop_id not in selected:
            if len(selected) >= 3:
                weakest = min(
                    (s for s in selected if s != stabilizer_id),
                    key=lambda s: score(s, action_definitions[s]) if s in action_definitions else 0,
                    default=None,
                )
                if weakest:
                    selected = [x for x in selected if x != weakest] + [prop_id]
            else:
                selected.append(prop_id)
            break

    return selected[:3]
