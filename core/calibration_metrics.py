"""
Calibration metrics computed from provenance. Core-only; no UI/dashboard dependency.
Used by core/calibration.py (recalibration trigger) and by dashboard payload builder.
"""

from __future__ import annotations

import math
from typing import Any


def _extract_actual_delta(provenance_entry: dict[str, Any]) -> dict[str, float]:
    """Extract actual variable deltas from a single provenance entry. Public for dashboard payload."""
    out: dict[str, float] = {}
    tr = provenance_entry.get("turn_record") or {}
    for ch in provenance_entry.get("variable_changes") or []:
        if isinstance(ch, dict):
            var = ch.get("var") or ch.get("variable")
            delta = ch.get("delta") or ch.get("change")
            if var and isinstance(delta, (int, float)):
                out[str(var)] = float(delta)
    delta_applied = tr.get("delta_applied") or {}
    if isinstance(delta_applied, dict):
        for k, v in delta_applied.items():
            if isinstance(v, (int, float)):
                out[str(k)] = out.get(str(k), 0.0) + float(v)
    return out


def _extract_predicted_deltas(provenance_entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Aggregate predicted deltas per variable from predicted_deltas (agent, action_type, delta)."""
    agg: dict[str, float] = {}
    for pd in provenance_entry.get("predicted_deltas") or []:
        if not isinstance(pd, dict):
            continue
        d = pd.get("delta")
        if isinstance(d, dict):
            updates = d.get("numeric_updates") or d
            if isinstance(updates, dict):
                for var, val in updates.items():
                    if isinstance(val, (int, float)):
                        agg[str(var)] = agg.get(str(var), 0.0) + float(val)
    return [{"variable": k, "predicted": v} for k, v in agg.items()]


def compute_calibration_from_provenance(
    provenance_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compute calibration metrics from a list of provenance entries.
    Returns prediction_vs_realized, rmse_over_time, overconfidence_flags, health.
    """
    prediction_vs_realized: list[dict[str, Any]] = []
    rmse_per_turn: list[float] = []
    overconfidence_flags: list[dict[str, Any]] = []

    for idx, entry in enumerate(provenance_entries):
        actual = _extract_actual_delta(entry)
        predicted_list = _extract_predicted_deltas(entry)
        if not actual and not predicted_list:
            continue

        turn = entry.get("turn", idx)
        pred_by_var: dict[str, float] = {p["variable"]: p["predicted"] for p in predicted_list}
        all_vars = set(actual.keys()) | set(pred_by_var.keys())
        sq_errors: list[float] = []
        for var in all_vars:
            pred_v = pred_by_var.get(var, 0.0)
            act_v = actual.get(var, 0.0)
            prediction_vs_realized.append({
                "turn": turn,
                "variable": var,
                "predicted": pred_v,
                "realized": act_v,
            })
            sq_errors.append((pred_v - act_v) ** 2)
            if abs(pred_v) > 1e-6 and abs(act_v) < abs(pred_v) * 0.3:
                overconfidence_flags.append({
                    "turn": turn,
                    "variable": var,
                    "predicted": pred_v,
                    "realized": act_v,
                })

        if sq_errors:
            rmse_per_turn.append(math.sqrt(sum(sq_errors) / len(sq_errors)))
        else:
            rmse_per_turn.append(0.0)

    mean_rmse = sum(rmse_per_turn) / len(rmse_per_turn) if rmse_per_turn else 0.0
    if mean_rmse < 1.0 and not overconfidence_flags:
        health = "green"
    elif mean_rmse < 3.0 and len(overconfidence_flags) < 3:
        health = "yellow"
    else:
        health = "red"

    return {
        "prediction_vs_realized": prediction_vs_realized[-100:],
        "rmse_over_time": rmse_per_turn,
        "overconfidence_flags": overconfidence_flags[-20:],
        "health": health,
    }
