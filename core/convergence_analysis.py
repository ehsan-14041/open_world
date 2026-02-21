"""
Convergence analysis: determine whether the system is converging to a steady state or oscillating.
Uses turn_record pre_state/post_state or variable_changes and delta_applied over time.
"""

from __future__ import annotations

from typing import Any

# Number of recent turns to consider for variance and sign-flip analysis
DEFAULT_LOOKBACK = 5
# Threshold: if max abs delta in last N turns is below this, consider stable
STABLE_DELTA_THRESHOLD = 0.5
# If fraction of consecutive deltas with sign flips is above this, consider oscillating
OSCILLATION_SIGN_FLIP_RATIO = 0.5


def _extract_variable_series(
    provenance: list[dict[str, Any]],
) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """
    Extract per-variable value series and delta series from provenance.
    Returns (values_per_var, deltas_per_var). values_per_var[var] = [v0, v1, ...] from post_state or reconstructed.
    """
    values_per_var: dict[str, list[float]] = {}
    deltas_per_var: dict[str, list[float]] = {}

    for entry in provenance:
        tr = entry.get("turn_record")
        if not isinstance(tr, dict):
            continue
        post = tr.get("post_state")
        pre = tr.get("pre_state")
        delta_applied = tr.get("delta_applied") or {}

        # Prefer post_state variables
        if isinstance(post, dict):
            vars_snapshot = post.get("variables") or post.get("global_state") or post
        else:
            vars_snapshot = {}

        if isinstance(vars_snapshot, dict):
            for var, val in vars_snapshot.items():
                if isinstance(val, (int, float)):
                    if var not in values_per_var:
                        values_per_var[var] = []
                    values_per_var[var].append(float(val))

        for var, d in (delta_applied if isinstance(delta_applied, dict) else {}).items():
            if isinstance(d, (int, float)):
                if var not in deltas_per_var:
                    deltas_per_var[var] = []
                deltas_per_var[var].append(float(d))

    return values_per_var, deltas_per_var


def _sign_flip_ratio(series: list[float]) -> float:
    """Fraction of consecutive pairs that have opposite signs (excluding zeros)."""
    if len(series) < 2:
        return 0.0
    flips = 0
    count = 0
    for i in range(1, len(series)):
        a, b = series[i - 1], series[i]
        if abs(a) < 1e-12 and abs(b) < 1e-12:
            continue
        count += 1
        if (a > 0 and b < 0) or (a < 0 and b > 0):
            flips += 1
    return flips / count if count else 0.0


def _variance(series: list[float]) -> float:
    if len(series) < 2:
        return 0.0
    mean = sum(series) / len(series)
    return sum((x - mean) ** 2 for x in series) / len(series)


def analyze_convergence(
    provenance: list[dict[str, Any]],
    *,
    lookback: int = DEFAULT_LOOKBACK,
) -> dict[str, Any]:
    """
    Analyze whether the system is converging, oscillating, diverging, or stable.
    Returns:
      - per_variable: dict[var, { "label": "converging"|"oscillating"|"diverging"|"stable", "reason": str }]
      - system_label: overall label
      - system_reason: short explanation
    """
    values_per_var, deltas_per_var = _extract_variable_series(provenance)
    per_variable: dict[str, dict[str, Any]] = {}
    all_labels: list[str] = []

    # Analyze each variable that has enough delta history
    for var, deltas in deltas_per_var.items():
        recent = deltas[-lookback:] if len(deltas) >= lookback else deltas
        if not recent:
            per_variable[var] = {"label": "unknown", "reason": "Insufficient delta history."}
            continue

        max_abs_delta = max(abs(d) for d in recent)
        flip_ratio = _sign_flip_ratio(recent)
        values = values_per_var.get(var) or []
        recent_values = values[-lookback:] if len(values) >= lookback else values
        var_variance = _variance(recent_values) if len(recent_values) >= 2 else 0.0

        if max_abs_delta < STABLE_DELTA_THRESHOLD:
            label = "stable"
            reason = f"Variable {var} changed very little in the last {len(recent)} turns."
        elif flip_ratio >= OSCILLATION_SIGN_FLIP_RATIO:
            label = "oscillating"
            reason = f"Variable {var} shows repeated direction changes (sign flips) in recent turns."
        elif var_variance > 10.0 and len(recent_values) >= 2:
            # High variance in level might indicate divergence or volatility
            label = "diverging"
            reason = f"Variable {var} has high variance in recent values."
        else:
            label = "converging"
            reason = f"Variable {var} is moving in a consistent direction without strong oscillation."

        per_variable[var] = {"label": label, "reason": reason}
        all_labels.append(label)

    # System overall: if any oscillating, report oscillating; else if any diverging, diverging; else converging or stable
    if not all_labels:
        system_label = "unknown"
        system_reason = "Insufficient turn data for convergence analysis."
    elif "oscillating" in all_labels:
        system_label = "oscillating"
        system_reason = "The system shows oscillation in one or more variables; actions are not clearly leading to a steady state."
    elif "diverging" in all_labels:
        system_label = "diverging"
        system_reason = "Some variables show diverging or high-variance behavior."
    elif all(l == "stable" for l in all_labels):
        system_label = "stable"
        system_reason = "The system is in a steady state with little recent change."
    else:
        system_label = "converging"
        system_reason = "The system appears to be moving toward a more stable state."

    return {
        "per_variable": per_variable,
        "system_label": system_label,
        "system_reason": system_reason,
    }
