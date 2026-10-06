"""
Model Health: a single honest verdict panel for a world model.

Motivation. Reporting "0% empirical / 100% assumption" told the user how much evidence the
model carries, but nothing about whether the model *works*, or about whether the world can
even be seen. After two historical replays the useful summary has three axes, not one:

    can we see the world?      →  observability (observable / proxy / latent mix)
    do we have evidence?       →  evidence coverage, influence-weighted
    does the model hold up?    →  historical validation, split by direction / timing / magnitude

The purpose is not to score the model well. It is to tell a user exactly which parts of an
answer to distrust — which is the capability an LLM cannot offer, because an LLM does not
know where its own answer is weak.

Every rating here is computed by a stated deterministic rule. Nothing is assigned by a model.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from event_sim.evidence.coverage import merge_influence
from event_sim.evidence.validation import evidence_coverage
from event_sim.schemas import OBSERVABILITY_LABELS, VariableDefinition, WorldSlice

RATINGS = ("GOOD", "MEDIUM", "POOR", "FAILED", "UNTESTED")

RULES: dict[str, str] = {
    "evidence_coverage": (
        "share of causal edges (influence-weighted) that are assumption or AI hypothesis: "
        "<25% GOOD, <50% MEDIUM, <75% POOR, otherwise FAILED"
    ),
    "observability": (
        "share of variables that are latent: <25% GOOD, <40% MEDIUM, <60% POOR, otherwise FAILED"
    ),
    "proxy_dependence": (
        "share of variables that are proxy_observable: <25% LOW, <50% MEDIUM, otherwise HIGH "
        "(reported as a level, not a grade)"
    ),
    "directional_validity": (
        "share of evaluated variables whose simulated direction matched the observed "
        "direction: =1 GOOD, >=0.5 MEDIUM, >0 POOR, 0 FAILED, no data UNTESTED"
    ),
    "timing_validity": (
        "median absolute timing error across scored peaks and milestones, in turns: "
        "<=1 GOOD, <=3 MEDIUM, <=6 POOR, otherwise FAILED, no data UNTESTED"
    ),
    "magnitude_validity": (
        "envelope coverage rate across scored level observations: >=0.8 GOOD, >=0.5 MEDIUM, "
        ">0 POOR, 0 FAILED, no data UNTESTED"
    ),
    "historical_validation": (
        "worst of directional, timing and magnitude validity, ignoring UNTESTED axes; "
        "UNTESTED if no replay has been run"
    ),
}


def observability_profile(variables: Iterable[VariableDefinition]) -> dict[str, Any]:
    """
    How much of this world can be seen at all — the axis the Yantian replay showed was
    binding, and which evidence coverage alone does not express.
    """
    var_list = list(variables)
    counts: dict[str, int] = {"observable": 0, "proxy_observable": 0, "latent": 0}
    for var in var_list:
        counts[var.observability_class] = counts.get(var.observability_class, 0) + 1
    total = len(var_list) or 1
    shares = {k: v / total for k, v in counts.items()}
    latent = shares["latent"]
    proxy = shares["proxy_observable"]
    return {
        "counts": counts,
        "shares": shares,
        "labels": dict(OBSERVABILITY_LABELS),
        "variable_count": len(var_list),
        "latent_share": latent,
        "proxy_share": proxy,
        "rating": (
            "FAILED" if latent >= 0.6 else
            "POOR" if latent >= 0.4 else
            "MEDIUM" if latent >= 0.25 else "GOOD"
        ),
        "proxy_dependence": "HIGH" if proxy >= 0.5 else ("MEDIUM" if proxy >= 0.25 else "LOW"),
        "latent_variables": [v.id for v in var_list if v.observability_class == "latent"],
        "proxy_variables": [v.id for v in var_list if v.observability_class == "proxy_observable"],
        "observable_variables": [v.id for v in var_list if v.observability_class == "observable"],
        "rule": RULES["observability"],
    }


def _validation_axes(replays: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Direction / timing / magnitude, aggregated across every replay supplied."""
    directions: list[bool] = []
    timing_errors: list[int] = []
    coverage_rates: list[float] = []

    for entry in replays:
        evaluation = entry.get("evaluation") or {}
        for row in evaluation.get("variables") or []:
            traj = row.get("trajectory") or {}
            if "direction_match" in traj:
                directions.append(bool(traj["direction_match"]))
            if traj.get("peak_timing_error_turns") is not None:
                timing_errors.append(abs(int(traj["peak_timing_error_turns"])))
            if row.get("coverage_rate") is not None:
                coverage_rates.append(float(row["coverage_rate"]))
        milestones = entry.get("milestones") or {}
        for row in milestones.get("milestones") or []:
            if row.get("scored") and row.get("timing_error_turns") is not None:
                timing_errors.append(abs(int(row["timing_error_turns"])))

    direction_score = (sum(directions) / len(directions)) if directions else None
    timing = (sorted(timing_errors)[len(timing_errors) // 2] if timing_errors else None)
    magnitude = (sum(coverage_rates) / len(coverage_rates)) if coverage_rates else None

    directional_rating = (
        "UNTESTED" if direction_score is None else
        "GOOD" if direction_score >= 1.0 else
        "MEDIUM" if direction_score >= 0.5 else
        "POOR" if direction_score > 0 else "FAILED"
    )
    timing_rating = (
        "UNTESTED" if timing is None else
        "GOOD" if timing <= 1 else
        "MEDIUM" if timing <= 3 else
        "POOR" if timing <= 6 else "FAILED"
    )
    magnitude_rating = (
        "UNTESTED" if magnitude is None else
        "GOOD" if magnitude >= 0.8 else
        "MEDIUM" if magnitude >= 0.5 else
        "POOR" if magnitude > 0 else "FAILED"
    )
    return {
        "directional_validity": directional_rating,
        "timing_validity": timing_rating,
        "magnitude_validity": magnitude_rating,
        "direction_match_rate": direction_score,
        "median_absolute_timing_error_turns": timing,
        "mean_envelope_coverage": magnitude,
        "events_tested": [e.get("episode") for e in replays],
    }


#: A defect's lifecycle. A defect is NEVER deleted once measured — it advances through
#: these stages so the model keeps its scientific history. A reader must always be able to
#: see that the model once had this problem and how it was resolved.
DEFECT_LIFECYCLE = (
    "known",                   # measured on >= 2 independent events, unfixed
    "mitigated",               # a change reduced it, but not yet on a held-out event
    "historically_validated",  # reduced on a HELD-OUT event
    "superseded",              # the measurement or the model changed so the defect no longer applies
)


def advance_defect(defect: dict[str, Any], stage: str, *, evidence: str) -> dict[str, Any]:
    """
    Move a defect along its lifecycle without erasing where it started.

    `first_recorded` and the original statement are preserved, and each transition appends
    to `history`. Deleting a defect because a later change improved it would destroy exactly
    the record that makes the model's development auditable.
    """
    if stage not in DEFECT_LIFECYCLE:
        raise ValueError(f"unknown defect stage {stage!r}; expected one of {DEFECT_LIFECYCLE}")
    if not evidence:
        raise ValueError("advancing a defect requires evidence for the transition")
    current = str(defect.get("lifecycle", "known"))
    if DEFECT_LIFECYCLE.index(stage) < DEFECT_LIFECYCLE.index(current):
        raise ValueError(
            f"cannot move defect {defect.get('id')!r} backwards from {current!r} to {stage!r}"
        )
    updated = dict(defect)
    updated["lifecycle"] = stage
    updated.setdefault("first_recorded", current)
    updated["history"] = list(defect.get("history") or []) + [
        {"from": current, "to": stage, "evidence": evidence}
    ]
    return updated


def known_defects(replays: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Measured defects the model is currently known to have and has NOT had fixed.

    Stating these on the product surface looks strange from a marketing point of view and is
    exactly what builds trust in serious decision support: the alternative is a user
    discovering the defect themselves, at which point nothing else in the output is credible.

    A defect is only listed when it has been *measured on more than one independent event*,
    so this cannot fill up with one-off noise.
    """
    from event_sim.cross_event import bias_metrics, timing_findings

    if len(replays) < 2:
        return []

    # `timing_findings` reads `milestone_evaluation`; callers of model_health pass the same
    # payload under the shorter key `milestones`. Normalise rather than requiring both.
    by_episode = {
        r.get("episode", f"event_{i}"): {
            "evaluation": r.get("evaluation") or {},
            "milestone_evaluation": r.get("milestone_evaluation") or r.get("milestones") or {},
        }
        for i, r in enumerate(replays)
    }
    bias = bias_metrics(timing_findings(by_episode))
    out: list[dict[str, Any]] = []

    combined = bias["combined_timing_bias"]
    if combined.get("systematic") and combined["median"] < 0:
        out.append({
            "id": "recovery_dynamics_too_fast",
            "severity": "high",
            "lifecycle": "known",
            "lifecycle_stages": list(DEFECT_LIFECYCLE),
            "history": [],
            "statement": (
                "Recovery dynamics currently trend too fast: across "
                f"{len(combined['episodes'])} independent historical disruptions the model "
                f"reaches peaks and recoveries a median of {abs(combined['median'])} turns "
                "earlier than observed, and never later."
            ),
            "measured_on": combined["episodes"],
            "metric": "combined_timing_bias",
            "value": combined["median"],
            "status": "known, measured, NOT fixed",
            "leading_explanation": (
                "H1 (queue as a stock) is supported by an independent mechanism test on real "
                "port-queue data (docs/replays/H1_QUEUE_MECHANISM.md) and has now been "
                "IMPLEMENTED EXPERIMENTALLY and replayed "
                "(docs/replays/H1_EXPERIMENT_RESULTS.md). On the one event whose metric can "
                "move it cut the peak timing error from -9 to -5 weeks and improved every "
                "secondary metric, but it did not meet the pre-registered acceptance rule, so "
                "this defect stays 'known' rather than 'mitigated'. The default production "
                "model is unchanged."
            ),
            "experimental_mechanism": {
                "hypothesis": "H1",
                "module": "port_disruption_h1_queue_experimental",
                "result": "experimental_no_effect (pre-registered rule); substantive improvement on Yantian",
                "historical_validation": "NOT YET — held-out event required",
            },
            "why_not_fixed": (
                "Competing structural explanations (queue-as-stock, backlog persistence, "
                "understated lags, asymmetric recovery) cannot be told apart without a "
                "held-out third event. Tuning a coefficient to close the gap now would fit "
                "the benchmarks rather than find the mechanism."
            ),
            "affects": "any conclusion about WHEN an effect peaks or clears",
            "safe_to_use_for": "direction of effect, and relative comparison between interventions",
        })
    return out


def model_health(
    slice_: WorldSlice,
    *,
    pivotal: dict[str, Any] | None = None,
    replays: Sequence[dict[str, Any]] | None = None,
    gap_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Assemble the Model Health panel.

    `replays` is a list of {episode, evaluation, milestones} dicts — one per historical
    event tested. Passing more than one is what turns "this model failed here" into
    "this model fails the same way everywhere", which is a much stronger claim.
    """
    influence = merge_influence(slice_, pivotal)
    coverage = evidence_coverage(slice_.edges)
    total_weight = sum(float(influence.get(e.id, {}).get("influence", 0.0)) for e in slice_.edges)
    assumption_weight = sum(
        float(influence.get(e.id, {}).get("influence", 0.0))
        for e in slice_.edges
        if e.status in ("expert_assumption", "user_assumption", "ai_hypothesis")
    )
    assumption_share = (assumption_weight / total_weight) if total_weight else 1.0
    evidence_rating = (
        "GOOD" if assumption_share < 0.25 else
        "MEDIUM" if assumption_share < 0.5 else
        "POOR" if assumption_share < 0.75 else "FAILED"
    )

    observability = observability_profile(slice_.variables)
    axes = _validation_axes(list(replays or []))

    tested = [axes[k] for k in ("directional_validity", "timing_validity", "magnitude_validity")
              if axes[k] != "UNTESTED"]
    order = {"GOOD": 0, "MEDIUM": 1, "POOR": 2, "FAILED": 3}
    historical = max(tested, key=lambda r: order[r]) if tested else "UNTESTED"

    defects = known_defects(list(replays or []))

    critical = (gap_report or {}).get("high_influence_low_evidence") or []
    recommended = []
    for row in critical[:3]:
        var = slice_.variable(str(row.get("target", "")))
        recommended.append({
            "for_edge": row.get("edge"),
            "variable": row.get("target"),
            "unit": var.unit if var else "",
            "observability_class": var.observability_class if var else "",
            "why": "highest-influence edge with the weakest evidence",
        })

    return {
        "evidence_coverage": {
            "rating": evidence_rating,
            "weighted_assumption_share": assumption_share,
            "unweighted_assumption_share": coverage["assumption_share"],
            "rule": RULES["evidence_coverage"],
        },
        "observability": observability,
        "proxy_dependence": {
            "level": observability["proxy_dependence"],
            "proxy_variables": observability["proxy_variables"],
            "rule": RULES["proxy_dependence"],
        },
        "historical_validation": {
            "rating": historical,
            "rule": RULES["historical_validation"],
            **axes,
        },
        "known_defects": defects,
        "critical_uncertainty": [row.get("edge") for row in critical],
        "recommended_data": recommended,
        "framing": (
            "Model Health says where NOT to trust this model. Every rating is computed by "
            "the stated rule from evidence and replay results; none is assigned by a model."
        ),
    }


def render_model_health(health: dict[str, Any]) -> str:
    """Fixed-width rendering for the CLI and reports."""
    lines = ["MODEL HEALTH", ""]
    rows = [
        ("Evidence coverage", health["evidence_coverage"]["rating"]),
        ("Observability", health["observability"]["rating"]),
        ("Proxy dependence", health["proxy_dependence"]["level"]),
        ("Historical validation", health["historical_validation"]["rating"]),
        ("Directional validity", health["historical_validation"]["directional_validity"]),
        ("Timing validity", health["historical_validation"]["timing_validity"]),
        ("Magnitude validity", health["historical_validation"]["magnitude_validity"]),
    ]
    for label, rating in rows:
        lines.append(f"  {label:<24} {rating}")
    lines.append("")
    for defect in health.get("known_defects", []):
        lines.append("  KNOWN MODEL DEFECT")
        lines.append(f"    {defect['statement']}")
        lines.append(f"    lifecycle: {defect.get('lifecycle', 'known')} "
                     f"(stages: {' -> '.join(defect.get('lifecycle_stages', []))})")
        lines.append(f"    status: {defect['status']}")
        lines.append(f"    affects: {defect['affects']}")
        lines.append(f"    still safe for: {defect['safe_to_use_for']}")
        lines.append("")
    if health["critical_uncertainty"]:
        lines.append("  Critical uncertainty")
        for edge in health["critical_uncertainty"]:
            lines.append(f"    {edge}")
    if health["recommended_data"]:
        lines.append("  Recommended data")
        for item in health["recommended_data"]:
            lines.append(
                f"    {item['variable']} ({item['unit']}) — {item['observability_class']}"
            )
    latent = health["observability"]["latent_variables"]
    if latent:
        lines.append("")
        lines.append(f"  Latent (unobservable) variables: {', '.join(latent)}")
    return "\n".join(lines)
