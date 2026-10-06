"""
Kill criteria derivation for the Strategic Decision Intelligence layer.

Derives a short list of "watch conditions" — if any is triggered, the decision
being analyzed is no longer viable. Sources:
  - Regime thresholds (FRAGILE/CRISIS crossings from world variables)
  - High-risk assumptions identified in the narrative
  - Top drivers trending in the wrong direction
"""

from __future__ import annotations

from typing import Any


_MAGNITUDE_LABELS = {
    "high": (0.6, float("inf")),
    "medium": (0.25, 0.6),
    "low": (0.0, 0.25),
}


def _magnitude_label(value: float) -> str:
    abs_v = abs(value)
    for label, (lo, hi) in _MAGNITUDE_LABELS.items():
        if lo <= abs_v < hi:
            return label
    return "low"


def _get_variable_bounds(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return variable specs keyed by variable name."""
    specs: dict[str, dict[str, Any]] = {}
    for var in (scenario or {}).get("variables") or []:
        if isinstance(var, dict) and var.get("name"):
            specs[str(var["name"])] = var
    return specs


def derive_kill_criteria(
    final_snapshot: dict[str, Any],
    provenance: list[dict[str, Any]],
    scenario: dict[str, Any],
    decision_input: dict[str, Any] | None = None,
    max_criteria: int = 3,
) -> list[dict[str, Any]]:
    """
    Derive kill criteria from available engine output.

    Returns a list of dicts: [{watch_variable, threshold, signal, why}].
    Each entry describes a condition that, if met, invalidates the decision.
    """
    criteria: list[dict[str, Any]] = []
    seen_vars: set[str] = set()
    var_specs = _get_variable_bounds(scenario)
    snapshot_vars: dict[str, Any] = (final_snapshot or {}).get("variables") or {}
    derived_vars: dict[str, Any] = (final_snapshot or {}).get("derived") or {}

    # 1. Regime-based criteria: stability and dissatisfaction thresholds
    stability_now = float(derived_vars.get("system_stability", 70.0))
    if "system_stability" not in seen_vars:
        threshold = 40.0
        criteria.append({
            "watch_variable": "system_stability",
            "threshold": f"< {threshold}",
            "signal": "System stability falls below 40 — regime enters CRISIS territory",
            "why": "At this level the operating environment becomes too volatile for the decision's assumptions to hold",
        })
        seen_vars.add("system_stability")

    dissatisfaction_now = float(derived_vars.get("dissatisfaction", 30.0))
    if "dissatisfaction" not in seen_vars and len(criteria) < max_criteria:
        threshold = 70.0
        criteria.append({
            "watch_variable": "dissatisfaction",
            "threshold": f"> {threshold}",
            "signal": "Stakeholder dissatisfaction exceeds 70 — systemic resistance emerges",
            "why": "High dissatisfaction typically reverses the gains from any operational decision within 1–2 periods",
        })
        seen_vars.add("dissatisfaction")

    if len(criteria) >= max_criteria:
        return criteria[:max_criteria]

    # 2. Scenario variable bounds — pick variables closest to their declared bounds
    # that are also relevant to the decision move (keyword match)
    move_keywords: set[str] = set()
    if decision_input:
        move_text = (decision_input.get("move") or "").lower()
        move_keywords = {w for w in move_text.split() if len(w) > 3}

    candidate_vars: list[tuple[float, str, dict]] = []
    for vname, spec in var_specs.items():
        if vname in seen_vars:
            continue
        min_v = spec.get("min")
        max_v = spec.get("max")
        current = snapshot_vars.get(vname)
        if current is None:
            current = derived_vars.get(vname)
        if not isinstance(current, (int, float)):
            continue
        current = float(current)
        proximity = 0.0
        threshold_val = None
        direction = None
        if isinstance(min_v, (int, float)) and isinstance(max_v, (int, float)):
            range_size = float(max_v) - float(min_v)
            if range_size > 0:
                dist_to_min = (current - float(min_v)) / range_size
                dist_to_max = (float(max_v) - current) / range_size
                if dist_to_min < dist_to_max:
                    proximity = 1.0 - dist_to_min
                    threshold_val = float(min_v)
                    direction = "falls below"
                else:
                    proximity = 1.0 - dist_to_max
                    threshold_val = float(max_v)
                    direction = "exceeds"
        # Boost if variable name shares keywords with the move
        relevance_bonus = sum(1 for kw in move_keywords if kw in vname.lower()) * 0.2
        candidate_vars.append((proximity + relevance_bonus, vname, spec))

    candidate_vars.sort(key=lambda x: x[0], reverse=True)
    for _, vname, spec in candidate_vars:
        if len(criteria) >= max_criteria:
            break
        if vname in seen_vars:
            continue
        current = snapshot_vars.get(vname) or derived_vars.get(vname)
        if not isinstance(current, (int, float)):
            continue
        min_v = spec.get("min")
        max_v = spec.get("max")
        if not isinstance(min_v, (int, float)) or not isinstance(max_v, (int, float)):
            continue
        range_size = float(max_v) - float(min_v)
        if range_size <= 0:
            continue
        dist_to_min = (float(current) - float(min_v)) / range_size
        dist_to_max = (float(max_v) - float(current)) / range_size
        if dist_to_min < dist_to_max:
            threshold_val = float(min_v) + range_size * 0.1
            direction = "falls below"
        else:
            threshold_val = float(max_v) - range_size * 0.1
            direction = "exceeds"
        label = spec.get("label") or vname
        criteria.append({
            "watch_variable": vname,
            "threshold": f"{direction} {round(threshold_val, 2)}",
            "signal": f"{label} {direction} its critical bound",
            "why": f"This variable is currently near its boundary — a further move in this direction would break the scenario's structural assumptions",
        })
        seen_vars.add(vname)

    # 3. Fallback: last-resort generic criterion when we have fewer than 1
    if not criteria:
        criteria.append({
            "watch_variable": "regime",
            "threshold": "CRISIS",
            "signal": "System enters CRISIS regime",
            "why": "CRISIS-level regime invalidates the assumptions underlying most operational decisions",
        })

    return criteria[:max_criteria]
