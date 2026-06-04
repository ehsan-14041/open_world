"""
Simulation Core Evaluation Runner.

Runs evaluation tests (determinism, nonlinearity, regime sensitivity, calibration,
generality, attribution stability), aggregates scores, and outputs structured JSON
plus a human-readable report. Does not modify core engine logic.
"""

from __future__ import annotations

import copy
import json
import math
import random
import sys
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Step 1 — Engine entry and run_engine helper
# ---------------------------------------------------------------------------


def run_engine(
    initial_state: dict[str, Any],
    actions: list[dict[str, Any]],
    turns: int = 1,
    noise: bool = False,
    *,
    variable_specs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Run engine from initial_state applying actions[0], ..., actions[turns-1].
    initial_state: snapshot-shaped (variables or global_state, optional causal_links, entities, relations).
    actions: list of delta-shaped dicts (numeric_updates, optional action_type, primary_variable).
    noise: if False, use physics_core.apply_delta_deterministic; if True, use WorldModel.apply_delta with ENABLE_UNCERTAINTY=True.
    Returns: final snapshot (with variables/global_state, turn, etc.).
    """
    from core.world_model import WorldModel
    from schemas.delta_schema import Delta

    vars_in = initial_state.get("variables") or initial_state.get("global_state") or {}
    causal_links = list(initial_state.get("causal_links") or [])
    specs = variable_specs or initial_state.get("variable_specs") or {}

    world = WorldModel(
        global_state=dict(vars_in),
        causal_links=causal_links,
    )
    world.load_snapshot(initial_state)

    n = min(turns, len(actions)) if actions else 0
    if n == 0 and turns > 0:
        return world.snapshot()

    if noise:
        with patch("config.settings.ENABLE_UNCERTAINTY", True), patch(
            "core.world_model.ENABLE_UNCERTAINTY", True
        ):
            for i in range(n):
                delta = Delta.from_dict(actions[i])
                world.apply_delta(delta, variable_specs=specs or None)
                world.turn += 1
        return world.snapshot()

    # Noise off: use apply_delta_deterministic and load result back
    from core.physics_core import apply_delta_deterministic

    for i in range(n):
        snapshot = world.snapshot()
        result = apply_delta_deterministic(
            snapshot,
            actions[i],
            causal_links,
            variable_specs=specs or None,
            action_type=actions[i].get("action_type"),
        )
        merged = dict(snapshot)
        merged["variables"] = result.get("variables") or result.get("global_state") or merged["variables"]
        merged["global_state"] = merged["variables"]
        merged["turn"] = snapshot.get("turn", 0) + 1
        merged["version"] = snapshot.get("version", 0) + 1
        world.load_snapshot(merged)
    return world.snapshot()


# ---------------------------------------------------------------------------
# Step 2 — Deterministic integrity test
# ---------------------------------------------------------------------------


def deterministic_test(
    initial_state: dict[str, Any],
    actions: list[dict[str, Any]],
    num_runs: int = 5,
    turns: int | None = None,
    tolerance: float = 1e-9,
    seed: int = 42,
) -> dict[str, Any]:
    """Run engine num_runs times with identical inputs and noise=False; compare final states."""
    t = turns if turns is not None else len(actions)
    if t <= 0:
        t = max(1, len(actions))
    action_slice = actions[:t]
    finals = []
    for _ in range(num_runs):
        random.seed(seed)
        try:
            with patch("config.settings.RANDOM_SEED", seed):
                fin = run_engine(
                    copy.deepcopy(initial_state),
                    [copy.deepcopy(a) for a in action_slice],
                    turns=t,
                    noise=False,
                )
            finals.append(fin.get("variables") or fin.get("global_state") or {})
        except Exception:
            finals.append({})
    max_diff = 0.0
    for i in range(len(finals)):
        for j in range(i + 1, len(finals)):
            va, vb = finals[i], finals[j]
            all_keys = set(va) | set(vb)
            for k in all_keys:
                a = va.get(k)
                b = vb.get(k)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    max_diff = max(max_diff, abs(float(a) - float(b)))
                elif a != b:
                    max_diff = max(max_diff, float("inf"))
    deterministic = max_diff < tolerance if max_diff != float("inf") else False
    if max_diff == float("inf"):
        max_diff = -1.0  # non-numeric or mismatch
    return {"max_diff": max_diff, "deterministic": deterministic}


# ---------------------------------------------------------------------------
# Step 3 — Nonlinearity test
# ---------------------------------------------------------------------------


def nonlinearity_test(
    initial_state: dict[str, Any],
    magnitudes: list[float] = (10, 20, 40, 80),
    variable_specs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply increasing delta magnitudes to one variable V; measure impact on dependent W; compute curvature."""
    vars_d = initial_state.get("variables") or initial_state.get("global_state") or {}
    causal_links = initial_state.get("causal_links") or []
    if not vars_d:
        return {"curvature_score": 0.0, "ratios": {}, "linear": True, "error": "no_variables"}
    V = next(iter(vars_d))
    # Find dependent W: first link from V to W
    W = None
    for link in causal_links:
        if isinstance(link, dict) and link.get("from") == V:
            W = link.get("to")
            break
    if not W:
        W = next((k for k in vars_d if k != V), V)
    impacts = []
    base_vars = dict(vars_d)
    for mag in magnitudes:
        state_copy = copy.deepcopy(initial_state)
        state_copy["variables"] = dict(base_vars)
        state_copy["global_state"] = state_copy["variables"]
        actions = [{"numeric_updates": {V: mag}, "action_type": f"increase_{V}", "primary_variable": V}]
        try:
            final = run_engine(state_copy, actions, turns=1, noise=False, variable_specs=variable_specs)
            fv = final.get("variables") or final.get("global_state") or {}
            impact_w = (fv.get(W) or 0) - (base_vars.get(W) or 0)
            impacts.append(abs(impact_w))
        except Exception:
            impacts.append(0.0)
    ratios = {}
    if len(impacts) >= 2 and impacts[0] > 1e-12:
        ratios["impact_ratio_20_vs_10"] = impacts[1] / impacts[0] if len(impacts) > 1 else 0
    if len(impacts) >= 3 and impacts[1] > 1e-12:
        ratios["impact_ratio_40_vs_20"] = impacts[2] / impacts[1] if len(impacts) > 2 else 0
    if len(impacts) >= 4 and impacts[2] > 1e-12:
        ratios["impact_ratio_80_vs_40"] = impacts[3] / impacts[2] if len(impacts) > 3 else 0
    avg_ratio = sum(ratios.values()) / len(ratios) if ratios else 1.0
    if avg_ratio <= 1.0 or not ratios:
        curvature_score = 0.0
        linear = True
    else:
        linear = avg_ratio < 1.2
        curvature_score = min(5.0, (avg_ratio - 1.0) * 2.5)
    return {"curvature_score": round(curvature_score, 4), "ratios": ratios, "linear": linear, "impacts": impacts}


# ---------------------------------------------------------------------------
# Step 4 — Regime sensitivity test
# ---------------------------------------------------------------------------


def regime_sensitivity_test(
    base_initial_state: dict[str, Any],
    variable_specs: dict[str, dict[str, Any]],
    same_action: dict[str, Any],
) -> dict[str, Any]:
    """Build NORMAL and CRISIS states; apply same action; return regime_effect_ratio."""
    try:
        from core.regime_detector import detect_regime
    except ImportError:
        return {"regime_effect_ratio": 0.0, "regime_normal": "unknown", "regime_crisis": "unknown", "error": "regime_detector_unavailable"}

    def _state_with_vars(vars_dict: dict[str, float]) -> dict[str, Any]:
        s = copy.deepcopy(base_initial_state)
        s["variables"] = dict(vars_dict)
        s["global_state"] = s["variables"]
        return s

    vars_d = base_initial_state.get("variables") or base_initial_state.get("global_state") or {}
    if not variable_specs:
        return {"regime_effect_ratio": 1.0, "regime_normal": "NORMAL", "regime_crisis": "NORMAL", "note": "no_specs"}

    normal_vars = {}
    crisis_vars = {}
    for var, spec in variable_specs.items():
        if not isinstance(spec, dict):
            continue
        scale = spec.get("scale") or spec
        max_b = (scale.get("max") if isinstance(scale, dict) else None) or spec.get("max") or 100.0
        if not isinstance(max_b, (int, float)):
            max_b = 100.0
        max_b = float(max_b)
        normal_vars[var] = 0.4 * max_b
        crisis_vars[var] = 0.92 * max_b

    if not normal_vars:
        normal_vars = dict(vars_d)
        crisis_vars = {k: v * 0.95 if isinstance(v, (int, float)) else 90 for k, v in vars_d.items()}

    state_normal = _state_with_vars(normal_vars)
    state_crisis = _state_with_vars(crisis_vars)
    reg_normal = detect_regime(normal_vars, variable_specs, 0.1, 0.05)
    reg_crisis = detect_regime(crisis_vars, variable_specs, 0.8, 0.1)
    try:
        final_n = run_engine(state_normal, [same_action], turns=1, noise=False, variable_specs=variable_specs)
        final_c = run_engine(state_crisis, [same_action], turns=1, noise=False, variable_specs=variable_specs)
    except Exception:
        return {"regime_effect_ratio": 0.0, "regime_normal": reg_normal.get("regime"), "regime_crisis": reg_crisis.get("regime"), "error": "run_failed"}
    vn = final_n.get("variables") or final_n.get("global_state") or {}
    vc = final_c.get("variables") or final_c.get("global_state") or {}
    impact_normal = sum(abs((vn.get(k) or 0) - (normal_vars.get(k) or 0)) for k in set(normal_vars) | set(vn))
    impact_crisis = sum(abs((vc.get(k) or 0) - (crisis_vars.get(k) or 0)) for k in set(crisis_vars) | set(vc))
    eps = 1e-9
    ratio = impact_crisis / (impact_normal + eps) if impact_normal >= 0 else 0.0
    return {
        "regime_effect_ratio": round(ratio, 4),
        "regime_normal": reg_normal.get("regime"),
        "regime_crisis": reg_crisis.get("regime"),
        "impact_normal": impact_normal,
        "impact_crisis": impact_crisis,
    }


# ---------------------------------------------------------------------------
# Step 5 — Calibration stress test
# ---------------------------------------------------------------------------


def calibration_stress_test(num_turns: int = 5) -> dict[str, Any]:
    """Inject wrong predictions; measure RMSE and confidence change; report adaptive_confidence."""
    try:
        from core.prediction_calibration import (
            get_calibration_score,
            get_metrics,
            update,
        )
    except ImportError:
        return "not_available"

    agent_id = "_eval_agent"
    predicted = {"x": 10.0}
    actual = {"x": 0.0}
    m_before = get_metrics(agent_id)
    score_before = get_calibration_score(agent_id)
    for _ in range(num_turns):
        update(agent_id, predicted, actual)
    m_after = get_metrics(agent_id)
    score_after = get_calibration_score(agent_id)
    rmse_before = (m_before.get("rolling_mse") or 0) ** 0.5
    rmse_after = (m_after.get("rolling_mse") or 0) ** 0.5
    rmse_delta = rmse_after - rmse_before
    confidence_before = m_before.get("calibration_weight") or 1.0
    confidence_after = m_after.get("calibration_weight") or 1.0
    confidence_delta = confidence_after - confidence_before
    adaptive_confidence = confidence_after < confidence_before or score_after < score_before
    return {
        "rmse_delta": round(rmse_delta, 6),
        "confidence_delta": round(confidence_delta, 6),
        "adaptive_confidence": adaptive_confidence,
    }


# ---------------------------------------------------------------------------
# Step 6 — Generality transfer test
# ---------------------------------------------------------------------------


def generality_test() -> dict[str, Any]:
    """Synthetic domain var_a, var_b, var_c with random propagation; run engine without modifying core."""
    random.seed(123)
    causal_links = [
        {"from": "var_a", "to": "var_b", "weight": 0.3},
        {"from": "var_b", "to": "var_c", "weight": 0.2},
    ]
    initial_state = {
        "variables": {"var_a": 50.0, "var_b": 30.0, "var_c": 20.0},
        "global_state": {"var_a": 50.0, "var_b": 30.0, "var_c": 20.0},
        "causal_links": causal_links,
        "entities": {},
        "relations": [],
        "narrative": [],
        "ontology": {},
        "version": 0,
        "turn": 0,
        "events": [],
    }
    actions = [
        {"numeric_updates": {"var_a": 5.0}, "action_type": "increase_var_a", "primary_variable": "var_a"},
        {"numeric_updates": {"var_b": -2.0}, "action_type": "decrease_var_b", "primary_variable": "var_b"},
    ]
    try:
        final = run_engine(initial_state, actions, turns=2, noise=False)
        v = final.get("variables") or final.get("global_state") or {}
        generically_operable = "var_a" in v and "var_b" in v and "var_c" in v
    except Exception as e:
        generically_operable = False
        return {"generically_operable": False, "error": str(e)}
    return {"generically_operable": generically_operable}


# ---------------------------------------------------------------------------
# Step 7 — Attribution stability test
# ---------------------------------------------------------------------------


def attribution_stability_test(num_runs: int = 5) -> dict[str, Any]:
    """Two actors: small vs large delta; check ranking consistency across runs."""
    from core.delta_attribution import compute_self_effect_per_agent, merge_delta_raw

    delta_raw_per_agent = {
        "actor_small": {"x": 1.0},
        "actor_large": {"x": 20.0},
    }
    delta_after_merge = merge_delta_raw(delta_raw_per_agent, None)
    delta_applied = dict(delta_after_merge)
    rankings = []
    impact_small_list = []
    impact_large_list = []
    for _ in range(num_runs):
        self_effect = compute_self_effect_per_agent(delta_raw_per_agent, delta_after_merge, delta_applied)
        impact_small = sum(abs(v) for v in (self_effect.get("actor_small") or {}).values())
        impact_large = sum(abs(v) for v in (self_effect.get("actor_large") or {}).values())
        impact_small_list.append(impact_small)
        impact_large_list.append(impact_large)
        rankings.append(impact_large > impact_small)
    ranking_consistent = all(rankings)
    impact_gap = (sum(impact_large_list) / num_runs) - (sum(impact_small_list) / num_runs)
    return {"ranking_consistent": ranking_consistent, "impact_gap": round(impact_gap, 6)}


# ---------------------------------------------------------------------------
# Step 8 — Aggregated score and classification
# ---------------------------------------------------------------------------


def score_determinism(result: dict[str, Any]) -> float:
    return 5.0 if result.get("deterministic") else 0.0


def score_nonlinearity(result: dict[str, Any]) -> float:
    return min(5.0, max(0.0, float(result.get("curvature_score", 0))))


def score_regime(result: dict[str, Any]) -> float:
    if result.get("error") or result.get("note") == "no_specs":
        return 2.5
    r = float(result.get("regime_effect_ratio", 0))
    if r >= 1.5:
        return 5.0
    if r >= 1.0:
        return 2.5 + (r - 1.0) * 5.0
    return max(0.0, r * 2.5)


def score_calibration(result: Any) -> float:
    if result == "not_available":
        return 0.0
    if not isinstance(result, dict):
        return 0.0
    if result.get("adaptive_confidence") and (result.get("rmse_delta") or 0) >= 0:
        return 5.0
    if result.get("adaptive_confidence"):
        return 3.0
    return 1.0


def score_generality(result: dict[str, Any]) -> float:
    return 5.0 if result.get("generically_operable") else 0.0


def score_attribution(result: dict[str, Any]) -> float:
    if result.get("ranking_consistent") and (result.get("impact_gap") or 0) > 0:
        return 5.0
    if result.get("ranking_consistent"):
        return 3.0
    return 0.0


def classify(overall_score: float) -> str:
    if overall_score >= 4.5:
        return "Enterprise-grade"
    if overall_score >= 3.5:
        return "Research-grade"
    if overall_score >= 2.5:
        return "Experimental"
    return "Prototype"


# ---------------------------------------------------------------------------
# Step 9 — Run all and output JSON + report
# ---------------------------------------------------------------------------


def _minimal_initial_state_and_actions() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Minimal state and actions for tests that need a scenario."""
    initial_state = {
        "variables": {"x": 50.0, "y": 30.0},
        "global_state": {"x": 50.0, "y": 30.0},
        "causal_links": [{"from": "x", "to": "y", "weight": 0.5}],
        "entities": {},
        "relations": [],
        "narrative": [],
        "ontology": {},
        "version": 0,
        "turn": 0,
        "events": [],
    }
    actions = [
        {"numeric_updates": {"x": 5.0}, "action_type": "increase_x", "primary_variable": "x"},
        {"numeric_updates": {"x": -2.0}, "action_type": "decrease_x", "primary_variable": "x"},
        {"numeric_updates": {"y": 3.0}, "action_type": "increase_y", "primary_variable": "y"},
    ]
    return initial_state, actions


def run_all_evaluations() -> dict[str, Any]:
    """Run all evaluation steps and return aggregated results."""
    initial_state, actions = _minimal_initial_state_and_actions()
    variable_specs = {"x": {"min": 0, "max": 100}, "y": {"min": 0, "max": 100}}

    det = deterministic_test(initial_state, actions, num_runs=5, turns=3, seed=42)
    nonlin = nonlinearity_test(initial_state, variable_specs=variable_specs)
    regime = regime_sensitivity_test(initial_state, variable_specs, same_action=actions[0])
    cal = calibration_stress_test(num_turns=5)
    gen = generality_test()
    attr = attribution_stability_test(num_runs=5)

    scores = {
        "determinism": score_determinism(det),
        "nonlinearity": score_nonlinearity(nonlin),
        "regime_effect": score_regime(regime),
        "calibration": score_calibration(cal),
        "generality": score_generality(gen),
        "attribution_stability": score_attribution(attr),
    }
    overall = sum(scores.values()) / 6.0
    classification = classify(overall)

    return {
        "deterministic": det,
        "nonlinearity": nonlin,
        "regime_effect": regime,
        "calibration": cal,
        "generality": gen,
        "attribution": attr,
        "scores": scores,
        "overall_score": round(overall, 4),
        "classification": classification,
    }


def print_report(results: dict[str, Any]) -> None:
    """Human-readable analysis."""
    print("\n" + "=" * 60)
    print("SIMULATION CORE EVALUATION — HUMAN-READABLE REPORT")
    print("=" * 60)

    nl = results.get("nonlinearity") or {}
    if isinstance(nl, dict):
        ratios = nl.get("ratios") or {}
        if ratios and nl.get("linear"):
            print("\n• Nonlinearity: Impact ratios are near 1 (linear regime). Nonlinear behavior is WEAK.")
        elif ratios:
            print(f"\n• Nonlinearity: Impact ratios {ratios}. Curvature score: {nl.get('curvature_score', 0)}. Some nonlinearity detected.")
        else:
            print("\n• Nonlinearity: Could not compute ratios (e.g. no propagation or zero impact).")

    reg = results.get("regime_effect") or {}
    if isinstance(reg, dict):
        r = reg.get("regime_effect_ratio")
        if r is not None:
            if abs(float(r) - 1.0) < 0.2:
                print("\n• Regime effect: Ratio near 1 — regime effect is SUPERFICIAL (similar impact in NORMAL vs CRISIS).")
            else:
                print(f"\n• Regime effect: Ratio = {r}. Regime differentiation is meaningful.")

    cal = results.get("calibration")
    if cal == "not_available":
        print("\n• Calibration: Module not available; skipped.")
    elif isinstance(cal, dict):
        if cal.get("adaptive_confidence"):
            print("\n• Calibration: ADAPTIVE — confidence/weight decreased after wrong predictions.")
        else:
            print("\n• Calibration: Not adaptive under stress test.")

    gen = results.get("generality") or {}
    if isinstance(gen, dict) and gen.get("generically_operable"):
        print("\n• Generality: Core is DOMAIN-AGNOSTIC (synthetic var_a/var_b/var_c ran successfully).")
    else:
        print("\n• Generality: Core may be tied to domain or synthetic run failed.")

    overall = results.get("overall_score", 0)
    classification = results.get("classification", "Prototype")
    print(f"\n• Overall score: {overall} — {classification}.")
    print("\n• What to improve before platformization:")
    scores = results.get("scores") or {}
    if overall < 4.5:
        if scores.get("determinism", 0) < 5:
            print("  - Raise determinism (ensure ENABLE_UNCERTAINTY=False and fixed seed yield identical finals).")
        if scores.get("regime_effect", 0) < 3:
            print("  - Strengthen regime sensitivity (physics or bounds in CRISIS).")
        if scores.get("calibration", 0) < 3:
            print("  - Ensure calibration is adaptive under prediction errors.")
        if scores.get("generality", 0) < 5:
            print("  - Ensure engine accepts arbitrary variable names and causal graphs.")
        if scores.get("attribution_stability", 0) < 5:
            print("  - Stabilize attribution ranking (consistent ordering of actors by impact).")
    print("=" * 60 + "\n")


def main() -> int:
    results = run_all_evaluations()
    out = {
        "deterministic": results["deterministic"],
        "nonlinearity": results["nonlinearity"],
        "regime_effect": results["regime_effect"],
        "calibration": results["calibration"],
        "generality": results["generality"],
        "attribution": results["attribution"],
        "scores": results["scores"],
        "overall_score": results["overall_score"],
        "classification": results["classification"],
    }
    print("SIMULATION CORE EVALUATION — STRUCTURED JSON")
    print(json.dumps(out, indent=2))
    print_report(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
