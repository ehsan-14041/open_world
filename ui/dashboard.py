"""
Live Enterprise Dashboard: real-time visualization of world state, risk, calibration,
action selection, assumptions, and explainability. Reads only from structured JSON;
no direct coupling with simulation internals.
"""

from __future__ import annotations

import math
import threading
from typing import Any

from config.settings import DASHBOARD_HISTORY_SIZE, DASHBOARD_ENABLED

# In-memory buffer of dashboard payloads (last N turns)
_buffer: list[dict[str, Any]] = []
_lock = threading.Lock()
_MAX_HISTORY = max(1, DASHBOARD_HISTORY_SIZE)


def _make_json_safe(obj: object) -> object:
    """Replace float('nan')/inf with None for JSON."""
    if obj is None:
        return None
    if isinstance(obj, float):
        if obj != obj or obj == float("inf") or obj == float("-inf"):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    return obj


def _cap_words(text: str, max_words: int = 150) -> str:
    if not text or max_words <= 0:
        return ""
    words = text.split()
    return " ".join(words[:max_words]) + ("..." if len(words) > max_words else "")


def _extract_actual_delta(provenance_entry: dict[str, Any]) -> dict[str, float]:
    """Extract actual variable deltas from a single provenance entry."""
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


def build_dashboard_payload(
    snapshot: dict[str, Any],
    provenance_entry: dict[str, Any] | None,
    scenario: dict[str, Any],
    agents_list: list[dict[str, Any]],
    provenance_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build a single dashboard event payload from snapshot, current provenance entry,
    scenario, and optional full provenance history (for calibration).
    """
    provenance_entry = provenance_entry or {}
    provenance_history = provenance_history or []
    if provenance_entry and provenance_entry not in provenance_history:
        provenance_history = list(provenance_history) + [provenance_entry]

    variables = snapshot.get("variables") or snapshot.get("global_state") or {}
    if not isinstance(variables, dict):
        variables = {}
    derived = snapshot.get("derived") or provenance_entry.get("derived") or {}
    turn = snapshot.get("turn") or provenance_entry.get("turn") or 0

    world_entropy = provenance_entry.get("world_entropy")
    if world_entropy is not None and isinstance(world_entropy, (int, float)):
        derived = dict(derived)
        derived["world_entropy"] = float(world_entropy)
    state_snapshot = {
        "turn": turn,
        "variables": {k: v for k, v in variables.items() if isinstance(v, (int, float))},
        "derived": derived,
    }

    stability = float(derived.get("system_stability", 70.0)) if isinstance(derived.get("system_stability"), (int, float)) else 70.0
    dissatisfaction = float(derived.get("dissatisfaction", 30.0)) if isinstance(derived.get("dissatisfaction"), (int, float)) else 30.0
    entropy = float(provenance_entry.get("world_entropy", 0.0)) if isinstance(provenance_entry.get("world_entropy"), (int, float)) else 0.0
    turn_degraded = bool(provenance_entry.get("turn_degraded", False))

    uncertainty = min(100, (100 - stability) * 0.3 + dissatisfaction * 0.2 + min(100, entropy) * 0.2 + (30 if turn_degraded else 0))
    constraint_risk = 15.0 if turn_degraded else 5.0
    assumption_risk = 10.0
    score = min(100, max(0, uncertainty + constraint_risk + assumption_risk))

    risk_report = {
        "score": round(score, 1),
        "breakdown": {
            "uncertainty": round(uncertainty, 1),
            "constraint": round(constraint_risk, 1),
            "assumption": round(assumption_risk, 1),
        },
        "tail_risk_summary": (
            "Elevated instability and turn degradation; consider stabilizing key variables."
            if (turn_degraded or stability < 50) else
            "Moderate risk; monitor dissatisfaction and entropy."
            if (dissatisfaction > 50 or entropy > 5) else
            "System within normal bounds."
        ),
    }

    calibration_metrics = compute_calibration_from_provenance(provenance_history)

    actions = provenance_entry.get("actions") or provenance_entry.get("proposals") or []
    turn_record = provenance_entry.get("turn_record") or {}
    chosen = turn_record.get("chosen_actions") or []
    candidates: list[str] = []
    for a in actions:
        if isinstance(a, dict):
            t = a.get("action_type", "")
        else:
            t = getattr(a, "action_type", "") or (a.to_dict() if hasattr(a, "to_dict") else {}).get("action_type", "")
        if t and t not in candidates:
            candidates.append(t)

    selected_agent = ""
    selected_action_type = ""
    if chosen:
        c = chosen[0]
        if isinstance(c, dict):
            selected_agent = c.get("agent", "")
            selected_action_type = c.get("action_id") or c.get("action", "")
        else:
            selected_agent = getattr(c, "agent", "") or getattr(c, "agent_id", "")
            selected_action_type = getattr(c, "action_id", "") or getattr(c, "action", "")
    if not selected_action_type and actions:
        first = actions[0]
        if isinstance(first, dict):
            selected_agent = first.get("agent_name", "")
            selected_action_type = first.get("action_type", "")
        else:
            selected_agent = getattr(first, "agent_name", "")
            selected_action_type = getattr(first, "action_type", "")

    selected_action = {
        "agent": selected_agent,
        "action_type": selected_action_type,
        "candidates": candidates,
        "probabilities": [],
        "rl_influence": None,
    }

    top_drivers: list[str] = []
    try:
        from core.attribution_layer import build_attribution_sentences
        top_drivers = build_attribution_sentences(
            [provenance_entry],
            allow_numbers=False,
            max_sentences=3,
        )
    except Exception:
        pass
    if not top_drivers and (provenance_entry.get("causal_edges") or turn_record.get("delta_applied")):
        delta_applied = turn_record.get("delta_applied") or {}
        for var, d in list(delta_applied.items())[:3]:
            if isinstance(d, (int, float)) and abs(d) > 1e-6:
                top_drivers.append(f"Change in {var}: {d:+.1f}")

    outcome = provenance_entry.get("outcome") or {}
    primary_effect = outcome.get("primary_effect") or {}
    if isinstance(primary_effect, dict):
        primary_var = primary_effect.get("var", "")
        primary_delta = primary_effect.get("delta", 0)
        primary_effect_str = f"{primary_var}: {primary_delta:+.1f}" if primary_var else ""
    else:
        primary_effect_str = str(primary_effect) if primary_effect else ""

    narrative_parts: list[str] = []
    for le in provenance_entry.get("turn_log") or []:
        if isinstance(le, dict) and le.get("justification"):
            narrative_parts.append(le["justification"])
        elif isinstance(le, dict) and le.get("reasoning"):
            narrative_parts.append(le["reasoning"])
    narrative_summary = _cap_words(" ".join(narrative_parts), 150) or "No narrative for this turn."

    explanation = {
        "top_drivers": top_drivers[:3],
        "primary_effect": primary_effect_str,
        "confidence_level": "moderate" if stability > 50 else "low",
        "narrative_summary": narrative_summary,
    }

    variable_specs = scenario.get("variable_specs") or {}
    causal_links = scenario.get("causal_links") or []
    affected_by: dict[str, list[str]] = {}
    for link in causal_links:
        if isinstance(link, dict) and link.get("from") and link.get("to"):
            to_var = link.get("to")
            from_var = link.get("from")
            if to_var not in affected_by:
                affected_by[to_var] = []
            if from_var not in affected_by[to_var]:
                affected_by[to_var].append(from_var)

    assumption_summary: list[dict[str, Any]] = []
    for var, spec in (variable_specs if isinstance(variable_specs, dict) else {}).items():
        assumption_summary.append({
            "assumption": f"{var} in [{spec.get('min', '?')}, {spec.get('max', '?')}]",
            "confidence": 0.8,
            "risk_if_wrong": "Bounds violation or clipping",
            "affected_variables": affected_by.get(var, [var]),
        })
    if not assumption_summary and variables:
        for var in list(variables.keys())[:5]:
            if isinstance(variables.get(var), (int, float)):
                assumption_summary.append({
                    "assumption": f"{var} is numeric",
                    "confidence": 0.7,
                    "risk_if_wrong": "Model drift",
                    "affected_variables": affected_by.get(var, [var]),
                })

    payload = {
        "state_snapshot": state_snapshot,
        "risk_report": risk_report,
        "calibration_metrics": calibration_metrics,
        "selected_action": selected_action,
        "explanation": explanation,
        "assumption_summary": assumption_summary,
    }
    return _make_json_safe(payload) or payload


def on_turn_complete(event_payload: dict[str, Any]) -> None:
    """Append a dashboard event payload to the history buffer (bounded by DASHBOARD_HISTORY_SIZE)."""
    if not DASHBOARD_ENABLED:
        return
    with _lock:
        _buffer.append(dict(event_payload))
        while len(_buffer) > _MAX_HISTORY:
            _buffer.pop(0)


def get_latest_payload() -> dict[str, Any] | None:
    """Return the most recent dashboard payload, or None if empty."""
    with _lock:
        return _buffer[-1] if _buffer else None


def get_history_payloads() -> list[dict[str, Any]]:
    """Return the last N dashboard payloads (for time-series and calibration)."""
    with _lock:
        return list(_buffer)


def register_routes(app: Any) -> None:
    """Register dashboard Flask routes on the given app."""
    if not DASHBOARD_ENABLED:
        return

    @app.route("/dashboard")
    def dashboard_page():
        from flask import render_template
        return render_template("dashboard.html")

    @app.route("/api/dashboard/latest")
    def api_dashboard_latest():
        from flask import jsonify
        payload = get_latest_payload()
        return jsonify(payload if payload is not None else {})

    @app.route("/api/dashboard/history")
    def api_dashboard_history():
        from flask import jsonify
        return jsonify(get_history_payloads())
