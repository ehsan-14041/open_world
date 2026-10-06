"""
Robustness & Failure-Mode aggregation.

Turns an ensemble of perturbed runs into an honest, ordinal report:
  - outcome distribution ("N of M runs")
  - robustness band (robust / mixed / fragile) with the literal count
  - per-variable spread (which variables are uncertain)
  - failure modes (the recurring way the decision breaks)
  - divergence point (where trajectories fan out)
  - pivotal assumption (the load-bearing coefficient)

HARD RULE: never emit an absolute probability. Outputs are counts, spreads, and
named patterns. Every report carries `disclaimer`.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from simulation.ensemble import RunResult, aggregate_goal_vars

DISCLAIMER = (
    "These are robustness counts under swept assumptions — not real-world "
    "probabilities. The engine sweeps uncertain coefficients to show where the "
    "decision is robust and how it breaks. You are the validator of each finding."
)


# ---------- small stats helpers (no numpy) ----------

def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _variance(vals: list[float]) -> float:
    n = len(vals)
    if n < 2:
        return 0.0
    mean = sum(vals) / n
    return sum((x - mean) ** 2 for x in vals) / n


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def _rank(vals: list[float]) -> list[float]:
    """Fractional ranks (ties averaged) for Spearman correlation."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 1-based average rank for the tie group
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation — robust to monotonic non-linearity and outliers."""
    if len(xs) < 2:
        return 0.0
    return _pearson(_rank(xs), _rank(ys))


def _final_regime(m: RunResult) -> str:
    return m.regime_sequence[-1] if m.regime_sequence else "NORMAL"


def _is_failure(m: RunResult) -> bool:
    return _final_regime(m).upper() == "CRISIS" or m.goal_score < 0


def _band(ratio: float) -> str:
    if ratio >= 0.7:
        return "robust"
    if ratio >= 0.4:
        return "mixed"
    return "fragile"


# ---------- aggregations ----------

def _variable_bands(members: list[RunResult], top: int = 6) -> list[dict[str, Any]]:
    by_var: dict[str, list[float]] = {}
    for m in members:
        for var, val in (m.final_state or {}).items():
            if isinstance(val, (int, float)):
                by_var.setdefault(var, []).append(float(val))
    bands: list[dict[str, Any]] = []
    for var, vals in by_var.items():
        if len(vals) < 2:
            continue
        s = sorted(vals)
        p25 = _percentile(s, 0.25)
        p75 = _percentile(s, 0.75)
        median = _percentile(s, 0.5)
        spread = p75 - p25
        scale = abs(median) if abs(median) > 1e-9 else (s[-1] - s[0] or 1.0)
        bands.append({
            "variable": var,
            "min": round(s[0], 3),
            "p25": round(p25, 3),
            "median": round(median, 3),
            "p75": round(p75, 3),
            "max": round(s[-1], 3),
            "spread": round(spread, 3),
            "normalized_spread": round(spread / scale, 3),
        })
    bands.sort(key=lambda b: b["normalized_spread"], reverse=True)
    return bands[:top]


def _failure_modes(members: list[RunResult], top: int = 3) -> list[dict[str, Any]]:
    # Prefer an absolute fail/success split; if one side is empty (e.g. a smooth
    # gradient where every run is technically negative), fall back to contrasting
    # the worst tercile against the best tercile so we always surface what
    # distinguishes bad runs from good ones when there is variance.
    failing = [m for m in members if _is_failure(m)]
    succeeding = [m for m in members if not _is_failure(m)]
    if not failing or not succeeding:
        ordered = sorted(members, key=lambda m: m.goal_score)
        k = max(1, len(ordered) // 3)
        failing = ordered[:k]
        succeeding = ordered[-k:]
    if not failing or not succeeding or failing is succeeding:
        return []

    def _mean_by_var(group: list[RunResult]) -> dict[str, float]:
        acc: dict[str, list[float]] = {}
        for m in group:
            for var, val in (m.final_state or {}).items():
                if isinstance(val, (int, float)):
                    acc.setdefault(var, []).append(float(val))
        return {v: (sum(xs) / len(xs)) for v, xs in acc.items() if xs}

    fail_mean = _mean_by_var(failing)
    succ_mean = _mean_by_var(succeeding) if succeeding else {}

    drivers: list[dict[str, Any]] = []
    for var, fmean in fail_mean.items():
        smean = succ_mean.get(var)
        if smean is None:
            continue
        diff = fmean - smean
        scale = max(abs(fmean), abs(smean), 1e-9)
        drivers.append({
            "variable": var,
            "direction": "higher" if diff > 0 else "lower",
            "fail_mean": round(fmean, 3),
            "success_mean": round(smean, 3),
            "_score": abs(diff) / scale,
        })
    drivers.sort(key=lambda d: d.pop("_score"), reverse=True)
    return drivers[:top]


def _divergence_point(members: list[RunResult], scenario: dict[str, Any]) -> dict[str, Any]:
    goal_vars = aggregate_goal_vars(scenario)
    if not goal_vars or not members:
        return {}
    max_turns = max((len(m.trajectory) for m in members), default=0)
    if max_turns == 0:
        return {}

    def _turn_goal_score(m: RunResult, t: int) -> float | None:
        if t >= len(m.trajectory):
            return None
        state = m.trajectory[t] or {}
        init = m.perturbed_initial_state or {}
        score = 0.0
        any_var = False
        for var, direction in goal_vars:
            cur = state.get(var)
            base = init.get(var)
            if isinstance(cur, (int, float)) and isinstance(base, (int, float)):
                denom = abs(float(base)) if abs(float(base)) > 1e-9 else 1.0
                score += ((float(cur) - float(base)) / denom) * direction
                any_var = True
        return score if any_var else None

    per_turn_var: list[float] = []
    for t in range(max_turns):
        scores = [s for m in members if (s := _turn_goal_score(m, t)) is not None]
        per_turn_var.append(_variance(scores) if scores else 0.0)

    if not any(per_turn_var):
        return {}
    # turn with the largest jump in variance vs the previous turn
    best_t, best_jump = 0, -1.0
    prev = 0.0
    for t, v in enumerate(per_turn_var):
        jump = v - prev
        if jump > best_jump:
            best_jump, best_t = jump, t
        prev = v
    return {
        "turn": best_t + 1,  # 1-based for humans
        "variance_by_turn": [round(v, 3) for v in per_turn_var],
    }


def _pivotal_assumption(members: list[RunResult], top: int = 3) -> list[dict[str, Any]]:
    if len(members) < 3:
        return []
    # dimensions present in every member
    common = set(members[0].perturbation.keys())
    for m in members[1:]:
        common &= set(m.perturbation.keys())
    if not common:
        return []
    goal_scores = [m.goal_score for m in members]
    ranked: list[dict[str, Any]] = []
    for dim in common:
        mults = [m.perturbation.get(dim, 1.0) for m in members]
        corr = _spearman(mults, goal_scores)  # rank correlation: robust to non-linearity
        ranked.append({"assumption": dim, "correlation": round(corr, 3), "_abs": abs(corr)})
    ranked.sort(key=lambda d: d.pop("_abs"), reverse=True)
    return [r for r in ranked[:top] if abs(r["correlation"]) > 0.1]


def aggregate_robustness(members: list[RunResult], scenario: dict[str, Any]) -> dict[str, Any]:
    """Build the full robustness report from ensemble members."""
    n = len(members)
    if n == 0:
        return {"n_runs": 0, "low_signal": True, "disclaimer": DISCLAIMER}

    regime_dist = Counter(_final_regime(m) for m in members)
    outcome_dist = Counter(m.outcome_label or "Unclassified" for m in members)
    robust_count = sum(1 for m in members if _final_regime(m).upper() == "NORMAL" and m.goal_score > 0)
    ratio = robust_count / n

    has_causal = bool((scenario or {}).get("causal_links"))
    # Quantitative signal: do goal scores actually move across runs?
    goal_scores = [m.goal_score for m in members]
    gs_var = _variance(goal_scores)
    gs_mean = sum(goal_scores) / n if n else 0.0
    gs_rel_spread = (math.sqrt(gs_var) / abs(gs_mean)) if abs(gs_mean) > 1e-9 else (math.sqrt(gs_var))
    categorical_degenerate = len(regime_dist) <= 1 and len(outcome_dist) <= 1
    quantitative_flat = gs_rel_spread < 0.02  # < 2% relative spread => essentially no movement
    low_signal = (not has_causal) or (categorical_degenerate and quantitative_flat)

    report = {
        "n_runs": n,
        "robustness": {
            "robust_count": robust_count,
            "of": n,
            "label": f"{robust_count} / {n}",
            "band": _band(ratio),
        },
        "outcome_distribution": {
            "by_regime": dict(regime_dist),
            "by_outcome": dict(outcome_dist),
        },
        "variable_bands": _variable_bands(members),
        "failure_modes": _failure_modes(members),
        "divergence_point": _divergence_point(members, scenario),
        "pivotal_assumption": _pivotal_assumption(members),
        "low_signal": low_signal,
        "disclaimer": DISCLAIMER,
    }
    if low_signal:
        report["low_signal_reason"] = (
            "Scenario has no causal graph (causal_links empty), so cross-run variance "
            "reflects only noise — robustness signal is weak. Build a causal model first."
            if not has_causal else
            "All runs produced essentially the same result — perturbation did not move the outcome."
        )
    # Surface quantitative spread even when the categorical label is uniform.
    report["quantitative_spread"] = {
        "goal_score_relative_spread": round(gs_rel_spread, 3),
        "goal_score_min": round(min(goal_scores), 3),
        "goal_score_max": round(max(goal_scores), 3),
    }
    return report


def _median(vals: list[float]) -> float:
    return _percentile(sorted(vals), 0.5) if vals else 0.0


def compare_scenarios(members_by_option: dict[str, list[RunResult]]) -> dict[str, Any]:
    """
    Robust Decision Making (RDM) comparison of option -> ensemble members.

    Presents THREE honest decision criteria side by side — never a single "best":
      - maximin       : the option whose worst-case outcome is least bad (pessimist)
      - expected_value: the option with the best median outcome (typical case)
      - minimax_regret: the option you'd least regret if the world defies your
                        assumptions (Regret = best-across-options-in-this-state − this option)

    Regret requires per-state alignment: member i of every option must have faced the
    same perturbation (guaranteed when ensembles share base_seed). If member counts
    differ, regret is skipped with a note rather than computed incorrectly.

    Each option also reports its bounding constraint (the pivotal assumption its
    outcome hinges on). Never emits a probability.
    """
    labels = [lbl for lbl, ms in members_by_option.items() if ms]
    if not labels:
        return {"options": [], "disclaimer": DISCLAIMER}

    counts = {lbl: len(members_by_option[lbl]) for lbl in labels}
    aligned = len(set(counts.values())) == 1 and len(labels) >= 2
    n = next(iter(counts.values())) if aligned else 0

    # --- Regret matrix (only when aligned) ---
    max_regret: dict[str, float] = {}
    if aligned:
        for lbl in labels:
            max_regret[lbl] = 0.0
        for i in range(n):
            best_i = max(members_by_option[lbl][i].goal_score for lbl in labels)
            for lbl in labels:
                regret_i = best_i - members_by_option[lbl][i].goal_score
                if regret_i > max_regret[lbl]:
                    max_regret[lbl] = regret_i

    # --- Per-option criteria ---
    options: list[dict[str, Any]] = []
    for lbl in labels:
        ms = members_by_option[lbl]
        scores = [m.goal_score for m in ms]
        worst = min(scores)
        robust_count = sum(1 for m in ms if _final_regime(m).upper() == "NORMAL" and m.goal_score > 0)
        worst_regime = "NORMAL"
        for r in ("CRISIS", "FRAGILE", "NORMAL"):
            if any(_final_regime(m).upper() == r for m in ms):
                worst_regime = r
                break
        fmodes = _failure_modes(ms)
        pivotal = _pivotal_assumption(ms)
        opt = {
            "option": lbl,
            "worst_case_score": round(worst, 3),       # maximin basis
            "median_score": round(_median(scores), 3), # expected-value basis
            "robust_count": f"{robust_count} / {len(ms)}",
            "worst_regime": worst_regime,
            "top_failure_driver": (fmodes[0]["variable"] if fmodes else ""),
            "hinges_on": (pivotal[0]["assumption"] if pivotal else None),
        }
        if aligned:
            opt["max_regret"] = round(max_regret[lbl], 3)
        options.append(opt)

    # --- Criterion winners (each criterion can favor a different option) ---
    criteria: dict[str, Any] = {
        "maximin": max(labels, key=lambda l: min(m.goal_score for m in members_by_option[l])),
        "expected_value": max(labels, key=lambda l: _median([m.goal_score for m in members_by_option[l]])),
    }
    if aligned:
        criteria["minimax_regret"] = min(labels, key=lambda l: max_regret[l])

    # --- Honest synthesis: do the criteria agree? ---
    by_label = {o["option"]: o for o in options}
    distinct = set(criteria.values())
    if len(distinct) == 1:
        winner = next(iter(distinct))
        wr = str((by_label.get(winner) or {}).get("worst_regime", "NORMAL")).upper()
        if wr == "NORMAL":
            synthesis = (
                f"All criteria favor '{winner}': best worst-case and best typical case, and "
                f"it never leaves NORMAL — a genuinely robust choice."
            )
        else:
            # Numeric criteria agree, but the option still breaks in its worst case.
            # Do NOT call this "robust" — it is the least-bad option, not a safe one.
            synthesis = (
                f"All numeric criteria favor '{winner}', but its worst case still reaches "
                f"{wr} — it is the least-bad option here, not a safe one. Every option can "
                f"break under these assumptions; treat the verdict as directional."
            )
    else:
        synthesis = (
            "No single option dominates. "
            + "; ".join(f"{k} favors '{v}'" for k, v in criteria.items())
            + ". Choose by your risk appetite, not by an average."
        )

    return {
        "options": options,
        "criteria": criteria,
        "regret_aligned": aligned,
        "synthesis": synthesis,
        "disclaimer": DISCLAIMER,
        **({} if aligned else {"regret_note": "Options had different ensemble sizes; minimax-regret omitted (needs per-state alignment)."}),
    }
