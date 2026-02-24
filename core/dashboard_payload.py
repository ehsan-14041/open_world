"""
Dashboard payload builder: computes state_snapshot, risk_report, calibration_metrics,
selected_action, explanation, assumption_summary from snapshot, provenance, and scenario.
No simulation or UI imports; lightweight arithmetic only. Dashboard payload is produced
from (snapshot, provenance_entry, scenario, agents_list, provenance_history) with no UI
dependency—suitable for API or external consumers. Used by the Live Enterprise Dashboard.
"""

from __future__ import annotations

import math
from typing import Any


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


def oracle_analysis_to_legacy(analysis: dict[str, Any] | None) -> dict[str, Any]:
    """
    Map v2.5 Oracle schema to legacy keys for dashboard display.
    If analysis already has legacy keys (action_reviewed, confidence_score), return as-is.
    """
    if not analysis or not isinstance(analysis, dict):
        return {}
    if "action_reviewed" in analysis or "confidence_score" in analysis:
        return dict(analysis)
    # v2.5 schema: advisory_only, action_id, confidence, expected_utility, tail_risk, mitigation_variant, ...
    tail = analysis.get("tail_risk", 0.5)
    eu = analysis.get("expected_utility", 0.0)
    mv = analysis.get("mitigation_variant") or {}
    risk_factors: list[str] = [f"Tail risk: {float(tail):.2f}", f"Expected utility: {float(eu):.2f}"]
    if isinstance(mv, dict) and mv.get("description"):
        risk_factors.append(str(mv.get("description", ""))[:200])
    return {
        "action_reviewed": str(analysis.get("action_id", "Proposed action"))[:500],
        "confidence_score": max(0, min(100, int(analysis.get("confidence", 50)))),
        "risk_factors": risk_factors[:6],
        "tail_risk_assessment": f"Tail risk: {float(tail):.2f}. Expected utility: {float(eu):.2f}. Mitigation: {str(mv)[:200]}.",
        "alternative_outlook_next_turn": {
            "optimistic": "See expected_utility and mitigation.",
            "most_likely": "Outcome depends on tail risk.",
            "pessimistic": "See tail_risk and mitigation_variant.",
        },
        "suspected_hidden_factors": [],
    }


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
    instability_mode = bool(provenance_entry.get("instability_mode", False))
    entropy_history = provenance_entry.get("entropy_history") or []
    entropy_rising = (
        len(entropy_history) >= 2
        and isinstance(entropy_history[-1], (int, float))
        and isinstance(entropy_history[-2], (int, float))
        and float(entropy_history[-1]) > float(entropy_history[-2])
    )

    uncertainty = min(
        100,
        (100 - stability) * 0.3
        + dissatisfaction * 0.2
        + min(100, entropy) * 0.2
        + (30 if turn_degraded else 0)
        + (15 if instability_mode else 0)
        + (10 if entropy_rising else 0),
    )
    constraint_risk = 15.0 if turn_degraded else 5.0
    assumption_risk = 10.0
    score = min(100, max(0, uncertainty + constraint_risk + assumption_risk))

    if turn_degraded or instability_mode or stability < 50:
        tail_risk_summary = "Elevated instability and turn degradation; consider stabilizing key variables."
    elif entropy_rising or dissatisfaction > 50 or entropy > 5:
        tail_risk_summary = "Moderate risk; monitor dissatisfaction and entropy."
    else:
        tail_risk_summary = "System within normal bounds."

    risk_report = {
        "score": round(score, 1),
        "breakdown": {
            "uncertainty": round(uncertainty, 1),
            "constraint": round(constraint_risk, 1),
            "assumption": round(assumption_risk, 1),
        },
        "tail_risk_summary": tail_risk_summary,
    }
    try:
        from core.risk_assessment import enrich_risk_report
        risk_report = enrich_risk_report(
            risk_report,
            provenance_history,
            agents_list,
            snapshot,
            provenance_entry,
            scenario,
            include_mc_tail=False,
        )
    except ImportError:
        pass

    calibration_metrics = compute_calibration_from_provenance(provenance_history)
    try:
        from core.calibration import get_recalibration_state
        cal_state = get_recalibration_state()
        calibration_metrics["recalibration_triggered"] = cal_state.get("recalibration_triggered", False)
        calibration_metrics["last_recalibration_turn"] = cal_state.get("last_recalibration_turn", -1)
    except ImportError:
        calibration_metrics["recalibration_triggered"] = False
        calibration_metrics["last_recalibration_turn"] = -1

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
        "agent": selected_agent or "N/A",
        "action_type": selected_action_type or "N/A",
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

    try:
        from config.settings import ASSUMPTION_HIGH_IMPACT_THRESHOLD
        high_impact_threshold = ASSUMPTION_HIGH_IMPACT_THRESHOLD
    except ImportError:
        high_impact_threshold = 0.5
    stability_var = (scenario.get("governance") or {}).get("stability_variable") if isinstance(scenario.get("governance"), dict) else "system_stability"
    diss_var = (scenario.get("governance") or {}).get("dissatisfaction_variable") if isinstance(scenario.get("governance"), dict) else "public_dissatisfaction"

    assumption_summary = []
    for var, spec in (variable_specs if isinstance(variable_specs, dict) else {}).items():
        aff = affected_by.get(var, [var])
        impact_score = len(aff) * 0.1
        if var == stability_var or var == diss_var:
            impact_score += 0.4
        impact_score = min(1.0, impact_score)
        high_impact = impact_score >= high_impact_threshold
        refinement_path = "human_review" if high_impact else "auto_reestimate"
        assumption_summary.append({
            "assumption": f"{var} in [{spec.get('min', '?')}, {spec.get('max', '?')}]",
            "confidence": 0.8,
            "risk_if_wrong": "Bounds violation or clipping",
            "affected_variables": aff,
            "impact_score": round(impact_score, 2),
            "high_impact": high_impact,
            "refinement_path": refinement_path,
        })
    if not assumption_summary and variables:
        for var in list(variables.keys())[:5]:
            if isinstance(variables.get(var), (int, float)):
                aff = affected_by.get(var, [var])
                impact_score = min(1.0, len(aff) * 0.1 + (0.4 if var in (stability_var, diss_var) else 0))
                assumption_summary.append({
                    "assumption": f"{var} is numeric",
                    "confidence": 0.7,
                    "risk_if_wrong": "Model drift",
                    "affected_variables": aff,
                    "impact_score": round(impact_score, 2),
                    "high_impact": impact_score >= high_impact_threshold,
                    "refinement_path": "human_review" if impact_score >= high_impact_threshold else "auto_reestimate",
                })

    edition_label = "Research Edition"
    try:
        from enterprise.positioning import get_current_tier
        edition_label = get_current_tier()
    except Exception:
        pass

    belief_alignment_section: dict[str, Any] = {}
    try:
        from config.settings import ENABLE_BELIEF_LAYER
        if ENABLE_BELIEF_LAYER and agents_list:
            from agents.belief_model import (
                BeliefState,
                belief_entropy_aggregate,
                dominant_belief,
            )
            entropies: list[float] = []
            dominants: list[tuple[str, str, float]] = []
            confidences: list[float] = []
            belief_vectors: list[dict[str, float]] = []
            for ag in agents_list:
                bs_dict = ag.get("belief_state") if isinstance(ag, dict) else None
                if not bs_dict or not isinstance(bs_dict, dict):
                    continue
                bs = BeliefState(
                    beliefs=bs_dict.get("beliefs") or {},
                    uncertainty=bs_dict.get("uncertainty") or {},
                    confidence=float(bs_dict.get("confidence", 0.5)),
                )
                entropies.append(belief_entropy_aggregate(bs))
                key, val = dominant_belief(bs)
                dominants.append((ag.get("name", "Agent"), key or "—", val))
                confidences.append(bs.confidence)
                belief_vectors.append(dict(bs.beliefs))
            if entropies:
                mean_entropy = sum(entropies) / len(entropies)
                divergence = 0.0
                if len(belief_vectors) > 1 and belief_vectors[0]:
                    vars_list = list(belief_vectors[0].keys())
                    for v in vars_list:
                        vals = [bv.get(v) for bv in belief_vectors if bv.get(v) is not None]
                        if len(vals) >= 2:
                            mean_v = sum(vals) / len(vals)
                            divergence += sum((x - mean_v) ** 2 for x in vals) / len(vals)
                    divergence = (divergence / len(vars_list)) ** 0.5 if vars_list else 0.0
                belief_alignment_section = {
                    "belief_entropy": round(mean_entropy, 3),
                    "dominant_belief": dominants[0] if dominants else ("—", "—", 0.0),
                    "dominant_beliefs_per_agent": dominants,
                    "divergence_index": round(divergence, 3),
                    "confidence_trend": round(sum(confidences) / len(confidences), 3) if confidences else 0.5,
                }
    except (ImportError, TypeError, ValueError):
        pass

    shock_section: dict[str, Any] = {}
    shock_data = provenance_entry.get("shock")
    if isinstance(shock_data, dict) and shock_data.get("active"):
        shock_section = {
            "shock_active": True,
            "shock_intensity": float(shock_data.get("intensity", 0)),
            "shock_impact_delta": dict(shock_data.get("impact_delta") or {}),
            "shock_types": list(shock_data.get("shocks") or []),
        }
        prev_vars = (provenance_history[-2] or {}).get("turn_record") or {}
        prev_state = prev_vars.get("post_state") or prev_vars.get("pre_state") or {}
        baseline_vars = prev_state.get("variables") or prev_state.get("global_state") or {}
        if isinstance(baseline_vars, dict) and shock_section.get("shock_impact_delta"):
            impact = shock_section["shock_impact_delta"]
            impact_delta_vs_baseline = {
                var: {"baseline": baseline_vars.get(var), "delta": impact.get(var)}
                for var in impact if var in baseline_vars
            }
            shock_section["impact_delta_vs_baseline"] = impact_delta_vs_baseline
    else:
        shock_section = {"shock_active": False, "shock_intensity": 0, "shock_impact_delta": {}}

    payload = {
        "state_snapshot": state_snapshot,
        "risk_report": risk_report,
        "calibration_metrics": calibration_metrics,
        "selected_action": selected_action,
        "explanation": explanation,
        "assumption_summary": assumption_summary,
        "edition": edition_label,
        "belief_alignment": belief_alignment_section,
        "shock": shock_section,
    }
    oracle_data = provenance_entry.get("oracle_analysis")
    if isinstance(oracle_data, dict) and oracle_data:
        payload["oracle_analysis"] = _make_json_safe(oracle_analysis_to_legacy(oracle_data))
    result = _make_json_safe(payload)
    return result if result is not None else payload
