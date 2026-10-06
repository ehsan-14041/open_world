"""
Dashboard payload builder: lives under ui/ (presentation layer). Builds state_snapshot, risk_report,
calibration_metrics, selected_action, explanation, assumption_summary from snapshot, provenance, scenario.
Imports compute_calibration_from_provenance from core.calibration_metrics. Used by the Live Enterprise Dashboard.
"""

from __future__ import annotations

import math
from typing import Any

from core.calibration_metrics import (
    compute_calibration_from_provenance,
    _extract_actual_delta,
    _extract_predicted_deltas,
)


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

    # Presentation language (Persian when the scenario description is Persian).
    try:
        from core.world_summarizer import detect_language as _detect_lang
        _dp_fa = _detect_lang(str((scenario or {}).get("description") or "")) == "fa"
    except Exception:
        _dp_fa = False
    _dp_lang = "fa" if _dp_fa else "en"

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

    ssi = float(provenance_entry.get("ssi", 0)) if isinstance(provenance_entry.get("ssi"), (int, float)) else 0.0
    volatility_decomposition = provenance_entry.get("volatility_decomposition")
    if isinstance(volatility_decomposition, dict) and isinstance(volatility_decomposition.get("volatility"), (int, float)):
        volatility = float(volatility_decomposition["volatility"])
    else:
        volatility = 0.0
        if len(provenance_history) >= 2 and provenance_history:
            prev_vars = (provenance_history[-2] or {}).get("state_snapshot") or {}
            prev_v = prev_vars.get("variables") if isinstance(prev_vars, dict) else {}
            if isinstance(prev_v, dict) and variables:
                diffs = [abs(float(variables.get(k, 0)) - float(prev_v.get(k, 0))) for k in set(variables) | set(prev_v) if isinstance(variables.get(k), (int, float)) and isinstance(prev_v.get(k), (int, float))]
                volatility = (sum(diffs) / len(diffs)) if diffs else 0.0
    risk_report = {
        "score": round(score, 1),
        "breakdown": {
            "uncertainty": round(uncertainty, 1),
            "constraint": round(constraint_risk, 1),
            "assumption": round(assumption_risk, 1),
        },
        "tail_risk_summary": tail_risk_summary,
        "stability_index": round(ssi, 2),
        "volatility_meter": round(volatility, 2),
        "tail_risk_gauge": min(1.0, score / 100.0),
        "uncertainty_band": {"low": max(0, score - 15), "high": min(100, score + 15)},
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
    try:
        from core.prediction_calibration import get_metrics as get_prediction_calibration_metrics
        per_agent_calibration: dict[str, Any] = {}
        for ag in agents_list or []:
            name = ag.get("name") if isinstance(ag, dict) else getattr(ag, "name", None)
            if name:
                m = get_prediction_calibration_metrics(name)
                per_agent_calibration[str(name)] = {
                    "rolling_mse": m.get("rolling_mse"),
                    "bias": m.get("bias"),
                    "calibration_weight": m.get("calibration_weight"),
                }
        calibration_metrics["per_agent_calibration"] = per_agent_calibration
    except ImportError:
        calibration_metrics["per_agent_calibration"] = {}

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

    # Prefer engine-generated turn narrative as the primary explanation source.
    narrative_obj = provenance_entry.get("narrative")
    if isinstance(narrative_obj, dict) and narrative_obj.get("turn_summary"):
        narrative_summary = str(narrative_obj.get("turn_summary") or "")
    else:
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
            "risk_if_wrong": ("نقضِ کران‌ها یا برش (clipping)" if _dp_fa else "Bounds violation or clipping"),
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
                    "risk_if_wrong": ("روند‌رفتگیِ مدل (model drift)" if _dp_fa else "Model drift"),
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

    belief_alignment_metrics: dict[str, Any] = {}
    if agents_list and variables:
        per_agent: dict[str, Any] = {}
        all_errors: list[float] = []
        for ag in agents_list:
            name = ag.get("name") if isinstance(ag, dict) else getattr(ag, "name", None)
            if not name:
                continue
            bs_dict = ag.get("belief_state") if isinstance(ag, dict) else None
            if not bs_dict or not isinstance(bs_dict, dict):
                continue
            beliefs_dict = bs_dict.get("beliefs") or {}
            if not isinstance(beliefs_dict, dict):
                continue
            belief_drift: dict[str, dict[str, Any]] = {}
            errors_this: list[float] = []
            all_vars = set(variables.keys()) | set(beliefs_dict.keys())
            for var in all_vars:
                bv = beliefs_dict.get(var)
                av = variables.get(var)
                if not isinstance(bv, (int, float)):
                    bv = 0.0
                if not isinstance(av, (int, float)):
                    av = 0.0
                bv = float(bv)
                av = float(av)
                err = bv - av
                abs_err = abs(err)
                normalized_error = abs_err / (abs(av) + 1e-6)
                belief_drift[str(var)] = {"belief": bv, "actual": av, "error": err, "abs_error": abs_err, "normalized_error": normalized_error}
                errors_this.append(abs_err)
            agg = sum(errors_this) / len(errors_this) if errors_this else 0.0
            per_agent[str(name)] = {
                "belief_drift": belief_drift,
                "aggregate_belief_error": agg,
                "aggregate_error": agg,
                "per_variable": belief_drift,
            }
            all_errors.extend(errors_this)
        belief_alignment_metrics["per_agent"] = per_agent
        belief_alignment_metrics["aggregate_belief_error"] = (
            sum(all_errors) / len(all_errors) if all_errors else 0.0
        )

    variable_specs_dict = scenario.get("variable_specs") or {}
    if not isinstance(variable_specs_dict, dict):
        variable_specs_dict = {}
    variable_dynamics: list[dict[str, Any]] = []
    bound_violations: list[dict[str, Any]] = []
    for var_name in list(variables.keys())[:20]:
        spec = variable_specs_dict.get(var_name) if isinstance(variable_specs_dict.get(var_name), dict) else {}
        v_type = str(spec.get("behavior_type", spec.get("v_type", "STOCK"))).upper()
        if v_type not in ("STOCK", "FLOW"):
            v_type = "STOCK"
        val = variables.get(var_name)
        v_min = spec.get("min")
        v_max = spec.get("max")
        if isinstance(spec.get("scale"), dict):
            v_min = v_min if v_min is not None else spec["scale"].get("min")
            v_max = v_max if v_max is not None else spec["scale"].get("max")
        saturation_pct = 0.0
        if isinstance(v_max, (int, float)) and float(v_max) > 0 and isinstance(val, (int, float)):
            saturation_pct = min(100.0, 100.0 * float(val) / float(v_max))
        if isinstance(val, (int, float)) and (v_min is not None or v_max is not None):
            v_f = float(val)
            if isinstance(v_min, (int, float)) and v_f < float(v_min):
                bound_violations.append({"var": var_name, "value": v_f, "min": float(v_min), "max": float(v_max) if isinstance(v_max, (int, float)) else None})
            if isinstance(v_max, (int, float)) and v_f > float(v_max):
                bound_violations.append({"var": var_name, "value": v_f, "min": float(v_min) if isinstance(v_min, (int, float)) else None, "max": float(v_max)})
        variable_dynamics.append({
            "var": var_name,
            "v_type": v_type,
            "inertia": float(spec.get("inertia", 0.2)) if isinstance(spec.get("inertia"), (int, float)) else 0.2,
            "decay": float(spec.get("decay", 0.01)) if isinstance(spec.get("decay"), (int, float)) else 0.01,
            "value": val,
            "saturation_pct": round(saturation_pct, 1),
        })

    belief_vs_reality: list[dict[str, Any]] = []
    try:
        from core.prediction_calibration import get_metrics as get_cal_metrics
        actual_delta = _extract_actual_delta(provenance_entry)
        for ag in agents_list or []:
            name = ag.get("name") if isinstance(ag, dict) else getattr(ag, "name", None)
            if not name:
                continue
            m = get_cal_metrics(name)
            pred_list = _extract_predicted_deltas(provenance_entry)
            pred_by_var = {p["variable"]: p["predicted"] for p in pred_list if isinstance(p, dict)}
            health = "green"
            if m.get("rolling_mse", 0) > 2.0 or abs(m.get("bias", 0)) > 1.0:
                health = "red"
            elif m.get("rolling_mse", 0) > 0.5 or abs(m.get("bias", 0)) > 0.3:
                health = "yellow"
            belief_vs_reality.append({
                "agent": name,
                "predicted_delta": pred_by_var,
                "actual_delta": actual_delta,
                "rolling_calibration_score": 1.0 / (1.0 + (m.get("rolling_mse") or 0)) if (m.get("rolling_mse") or 0) >= 0 else 0.5,
                "health": health,
            })
    except ImportError:
        pass

    propagation_trace = (turn_record.get("propagation_trace") or []) if isinstance(turn_record.get("propagation_trace"), list) else []
    causal_influence: list[dict[str, Any]] = []
    for e in propagation_trace[:30]:
        if isinstance(e, dict) and e.get("from") and e.get("to"):
            causal_influence.append({
                "from": e.get("from"),
                "to": e.get("to"),
                "delta_contrib": e.get("delta_contrib"),
                "hop": e.get("hop"),
                "decay_factor": e.get("decay_factor"),
            })
    if not causal_influence:
        for ch in (provenance_entry.get("variable_changes") or [])[:10]:
            if isinstance(ch, dict):
                causal_influence.append({"var": ch.get("var") or ch.get("variable"), "delta": ch.get("delta") or ch.get("change")})

    regime = str(provenance_entry.get("regime", "NORMAL"))
    if regime not in ("NORMAL", "FRAGILE", "CRISIS"):
        regime = "NORMAL"

    oracle_tier_used = provenance_entry.get("oracle_tier_used") or "Off"
    impact_score = float(provenance_entry.get("impact_score", 0)) if isinstance(provenance_entry.get("impact_score"), (int, float)) else 0.0
    oracle_analysis_raw = provenance_entry.get("oracle_analysis")
    raw_confidence = 50
    confidence_pct = 50
    tail_risk_raw = 0.5
    tail_risk_pct = 50
    if isinstance(oracle_analysis_raw, dict):
        raw_confidence = max(0, min(100, int(oracle_analysis_raw.get("confidence", 50))))
        confidence_pct = raw_confidence
        tail_risk_raw = max(0.0, min(1.0, float(oracle_analysis_raw.get("tail_risk", 0.5))))
        tail_risk_pct = int(tail_risk_raw * 100)
    calibration_score_agg = 0.5
    try:
        from core.prediction_calibration import get_calibration_score
        scores = [get_calibration_score(ag.get("name") if isinstance(ag, dict) else getattr(ag, "name", "")) for ag in (agents_list or []) if (ag.get("name") if isinstance(ag, dict) else getattr(ag, "name", None))]
        calibration_score_agg = (sum(scores) / len(scores)) if scores else 0.5
    except ImportError:
        pass
    effective_confidence = max(0, min(100, int(raw_confidence * calibration_score_agg)))
    if calibration_score_agg < 0.2:
        effective_confidence = min(effective_confidence, 20)
    tail_risk_adjusted = min(1.0, tail_risk_raw + (1.0 - calibration_score_agg) * 0.2)
    tail_risk_pct = int(tail_risk_adjusted * 100)
    oracle_tier_badge = {
        "oracle_tier": oracle_tier_used,
        "confidence_pct": effective_confidence,
        "tail_risk_pct": tail_risk_pct,
        "impact_score": round(impact_score, 2),
        "raw_confidence": raw_confidence,
        "effective_confidence": effective_confidence,
        "calibration_score": round(calibration_score_agg, 3),
    }

    delta_lifecycle_stages = ["Collection", "Normalization", "Cross-Validation", "Synthesis", "Propagation", "Drift/Noise", "Commit"]
    outcome_dict = provenance_entry.get("outcome") or {}
    stages_modified: list[str] = []
    if outcome_dict.get("primary_effect"):
        stages_modified.append("Propagation")
    if outcome_dict.get("noise_component"):
        stages_modified.append("Drift/Noise")
    if turn_record.get("delta_applied"):
        stages_modified.append("Synthesis")
    delta_lifecycle = {"stages": delta_lifecycle_stages, "stages_modified": stages_modified or ["Synthesis", "Propagation", "Commit"]}

    vol_decomp = provenance_entry.get("volatility_decomposition")
    if not isinstance(vol_decomp, dict):
        vol_decomp = {}

    narrative_payload: dict[str, Any] = {}
    narrative = provenance_entry.get("narrative")
    if isinstance(narrative, dict):
        narrative_payload = {
            "narrative": narrative,
            "turn_intelligence": {
                "turn_summary": narrative.get("turn_summary"),
                "outcome_assessment": narrative.get("outcome_assessment"),
                "regime_commentary": narrative.get("regime_commentary"),
            },
            "actor_ranking": narrative.get("actor_analysis") or [],
            "causal_story": narrative.get("causal_chain") or [],
            "hidden_costs": narrative.get("hidden_costs") or [],
        }
    else:
        try:
            from core.narrative_engine import generate_turn_narrative
            from core.narrative_memory import append_narrative
            previous_state = {}
            if len(provenance_history) >= 2:
                prev_entry = provenance_history[-2] or {}
                tr_prev = prev_entry.get("turn_record") or {}
                previous_state = tr_prev.get("pre_state") or tr_prev.get("post_state") or {}
            current_state = {"variables": variables, "global_state": variables, **state_snapshot}
            delta_applied = turn_record.get("delta_applied") or {}
            propagation_trace = turn_record.get("propagation_trace") or []
            causal_edges = provenance_entry.get("causal_edges") or []
            causal_trace = list(propagation_trace) + [e for e in causal_edges if isinstance(e, dict) and (e.get("from") or e.get("to") or e.get("variable"))]
            calibration_data = dict(calibration_metrics)
            try:
                from core.prediction_calibration import get_calibration_score
                scores = [get_calibration_score(ag.get("name") if isinstance(ag, dict) else getattr(ag, "name", "")) for ag in (agents_list or []) if (ag.get("name") if isinstance(ag, dict) else getattr(ag, "name", None))]
                calibration_data["calibration_score_agg"] = (sum(scores) / len(scores)) if scores else 0.5
            except ImportError:
                calibration_data["calibration_score_agg"] = 0.5
            chosen_actions = turn_record.get("chosen_actions") or []
            goals_per_agent: dict[str, dict[str, Any]] = {}
            initial_agents = (scenario or {}).get("initial_agents") or []
            for ag in agents_list or []:
                name = ag.get("name") if isinstance(ag, dict) else getattr(ag, "name", None)
                if name:
                    goals_per_agent[str(name)] = {
                        "objectives": ag.get("objectives") if isinstance(ag, dict) else getattr(ag, "objectives", {}),
                        "long_term_goals": ag.get("long_term_goals") if isinstance(ag, dict) else getattr(ag, "long_term_goals", []),
                    }
            for ia in initial_agents:
                if not isinstance(ia, dict):
                    continue
                name = ia.get("name")
                if name and name not in goals_per_agent:
                    goals_per_agent[str(name)] = {
                        "objectives": ia.get("objectives") or {},
                        "long_term_goals": ia.get("long_term_goals") or [],
                    }
            narrative = generate_turn_narrative(
                previous_state,
                current_state,
                delta_applied,
                causal_trace,
                regime,
                calibration_data,
                chosen_actions,
                goals_per_agent,
                scenario or {},
                self_effect_per_agent=turn_record.get("self_effect_per_agent") or {},
                propagation_trace=propagation_trace,
                delta_applied=delta_applied,
            )
            append_narrative(narrative, turn)
            narrative_payload = {
                "narrative": narrative,
                "turn_intelligence": {
                    "turn_summary": narrative.get("turn_summary"),
                    "outcome_assessment": narrative.get("outcome_assessment"),
                    "regime_commentary": narrative.get("regime_commentary"),
                },
                "actor_ranking": narrative.get("actor_analysis") or [],
                "causal_story": narrative.get("causal_chain") or [],
                "hidden_costs": narrative.get("hidden_costs") or [],
            }
        except Exception:
            narrative_payload = {}
    try:
        from core.narrative_memory import generate_longitudinal_story
        narrative_payload["longitudinal_story"] = generate_longitudinal_story(5, lang=_dp_lang)
    except Exception:
        narrative_payload["longitudinal_story"] = ""

    payload = {
        "state_snapshot": state_snapshot,
        "risk_report": risk_report,
        "calibration_metrics": calibration_metrics,
        "selected_action": selected_action,
        "explanation": explanation,
        "assumption_summary": assumption_summary,
        "edition": edition_label,
        "belief_alignment": belief_alignment_section,
        "belief_alignment_metrics": belief_alignment_metrics,
        "shock": shock_section,
        "variable_dynamics": variable_dynamics,
        "belief_vs_reality": belief_vs_reality,
        "causal_influence": causal_influence,
        "oracle_tier_badge": oracle_tier_badge,
        "delta_lifecycle": delta_lifecycle,
        "regime": regime,
        "volatility_decomposition": vol_decomp,
        "bound_violations": bound_violations,
        **narrative_payload,
    }
    oracle_data = provenance_entry.get("oracle_analysis")
    if isinstance(oracle_data, dict) and oracle_data:
        payload["oracle_analysis"] = _make_json_safe(oracle_analysis_to_legacy(oracle_data))
    result = _make_json_safe(payload)
    return result if result is not None else payload
