"""
Evidence layer: validation and coverage accounting.

Two jobs, both epistemic rather than numeric:

1. `validate_module` — refuse to load a world module that claims evidence it does not
   carry. A status in EVIDENCE_BACKED_STATUSES (observed / empirical / literature_backed /
   historically_calibrated) requires at least one Evidence record. This is what stops an
   AI-proposed coefficient from quietly becoming a "literature-backed" one.

2. `evidence_coverage` — count edges and variables by status group so a run can display
   how much of its own mechanism is actually evidenced. Coverage is reported as shares of
   the model's causal edges, explicitly NOT as a probability that the model is right.
"""

from __future__ import annotations

from typing import Any, Iterable

from event_sim.schemas import (
    EVIDENCE_BACKED_STATUSES,
    EVIDENCE_STATUS_GROUP,
    EVIDENCE_STATUS_ORDER,
    OBSERVABILITY_ORDER,
    CausalEdgeEvidence,
    VariableDefinition,
    WorldModule,
)


class EvidenceValidationError(ValueError):
    """Raised when a module claims a status stronger than its evidence supports."""


#: Human-readable label per coverage group, for UI/API.
COVERAGE_GROUP_LABELS: dict[str, str] = {
    "observed_empirical": "Observed / empirical",
    "literature_backed": "Literature-backed / historically calibrated",
    "assumption": "Expert or user assumption",
    "ai_hypothesis": "AI hypothesis",
}

#: Coverage below which a run is flagged as weakly evidenced (share of edges that are
#: assumption or AI hypothesis). Not a probability — a disclosure threshold.
WEAK_EVIDENCE_THRESHOLD = 0.5


def validate_edge(edge: CausalEdgeEvidence) -> list[str]:
    """Return a list of validation errors for one edge (empty = valid)."""
    errors: list[str] = []
    if edge.status not in EVIDENCE_STATUS_ORDER:
        errors.append(f"{edge.id}: unknown evidence status {edge.status!r}")
    if edge.status in EVIDENCE_BACKED_STATUSES and not edge.evidence:
        errors.append(
            f"{edge.id}: status '{edge.status}' requires at least one evidence record; "
            f"downgrade to 'expert_assumption' or attach a source"
        )
    if edge.polarity not in ("positive", "negative"):
        errors.append(f"{edge.id}: polarity must be 'positive' or 'negative'")
    if edge.effect.low > edge.effect.high:
        errors.append(f"{edge.id}: effect.low ({edge.effect.low}) exceeds effect.high ({edge.effect.high})")
    if not (edge.effect.low <= edge.effect.central <= edge.effect.high):
        errors.append(f"{edge.id}: effect.central must lie within [low, high]")
    if edge.lag.min < 0 or edge.lag.max < edge.lag.min:
        errors.append(f"{edge.id}: invalid lag window {edge.lag.to_dict()}")
    return errors


def validate_module(module: WorldModule, *, raise_on_error: bool = True) -> list[str]:
    """
    Validate a world module structurally and epistemically.
    Returns the list of errors; raises EvidenceValidationError when raise_on_error.
    """
    errors: list[str] = []
    var_ids = set(module.variable_ids())
    if len(var_ids) != len(module.variables):
        errors.append(f"{module.id}: duplicate variable ids")

    for var in module.variables:
        if var.scale == 0:
            errors.append(f"{module.id}.{var.id}: scale must be non-zero (it normalises deviations)")
        if not (0.0 < var.response <= 1.0):
            errors.append(f"{module.id}.{var.id}: dynamics.response must be in (0, 1]")
        if var.minimum is not None and var.maximum is not None and var.minimum > var.maximum:
            errors.append(f"{module.id}.{var.id}: range.min exceeds range.max")
        if var.status not in EVIDENCE_STATUS_ORDER:
            errors.append(f"{module.id}.{var.id}: unknown evidence status {var.status!r}")
        # Observability is part of the World Model contract, not optional metadata: a user
        # must always be able to ask of any result "was this variable measured, estimated
        # through a stand-in, or is it purely internal model state?"
        if var.observability_class not in OBSERVABILITY_ORDER:
            errors.append(
                f"{module.id}.{var.id}: observability_class must be one of "
                f"{OBSERVABILITY_ORDER}, got {var.observability_class!r}"
            )
        if not var.observability_note:
            errors.append(
                f"{module.id}.{var.id}: observability_class {var.observability_class!r} needs a "
                f"justification in observability_note — state what series exists, or that none does"
            )

    axis_ids = {a.id for a in module.axes}
    seen_edges: set[str] = set()
    for edge in module.edges:
        errors.extend(f"{module.id}: {e}" for e in validate_edge(edge))
        if edge.source not in var_ids:
            errors.append(f"{module.id}: edge {edge.id} has unknown source variable")
        if edge.target not in var_ids:
            errors.append(f"{module.id}: edge {edge.id} has unknown target variable")
        if edge.source == edge.target:
            errors.append(f"{module.id}: edge {edge.id} is a self-loop")
        if edge.id in seen_edges:
            errors.append(f"{module.id}: duplicate edge {edge.id}")
        seen_edges.add(edge.id)
        if edge.axis and edge.axis not in axis_ids:
            errors.append(f"{module.id}: edge {edge.id} references unknown axis {edge.axis!r}")

    for var in module.variables:
        if var.axis and var.axis not in axis_ids:
            errors.append(f"{module.id}.{var.id}: references unknown axis {var.axis!r}")

    if raise_on_error and errors:
        raise EvidenceValidationError("; ".join(errors))
    return errors


def evidence_coverage(
    edges: Iterable[CausalEdgeEvidence],
    variables: Iterable[VariableDefinition] | None = None,
) -> dict[str, Any]:
    """
    Count causal edges by evidence status group.

    Returns shares of the model's mechanisms — deliberately not a confidence score.
    `weakly_evidenced` is True when assumptions + AI hypotheses are at least
    WEAK_EVIDENCE_THRESHOLD of edges, and drives the UI disclosure banner.
    """
    edge_list = list(edges)
    by_status: dict[str, int] = {s: 0 for s in EVIDENCE_STATUS_ORDER}
    by_group: dict[str, int] = {g: 0 for g in COVERAGE_GROUP_LABELS}
    for edge in edge_list:
        by_status[edge.status] = by_status.get(edge.status, 0) + 1
        group = EVIDENCE_STATUS_GROUP.get(edge.status, "ai_hypothesis")
        by_group[group] = by_group.get(group, 0) + 1

    total = len(edge_list)
    shares = {g: (c / total if total else 0.0) for g, c in by_group.items()}
    assumption_share = shares.get("assumption", 0.0) + shares.get("ai_hypothesis", 0.0)

    out: dict[str, Any] = {
        "edge_count": total,
        "by_status": {k: v for k, v in by_status.items() if v},
        "by_group": by_group,
        "shares": shares,
        "group_labels": dict(COVERAGE_GROUP_LABELS),
        "assumption_share": assumption_share,
        "weakly_evidenced": total > 0 and assumption_share >= WEAK_EVIDENCE_THRESHOLD,
        "sourced_edges": sum(1 for e in edge_list if e.evidence),
        "disclaimer": (
            "Coverage counts how many causal mechanisms carry evidence. It is not a "
            "probability that the simulated trajectories are correct."
        ),
    }
    if variables is not None:
        var_list = list(variables)
        var_status: dict[str, int] = {}
        for v in var_list:
            var_status[v.status] = var_status.get(v.status, 0) + 1
        out["variable_count"] = len(var_list)
        out["variables_by_status"] = var_status
    return out


def missing_evidence(edges: Iterable[CausalEdgeEvidence]) -> list[dict[str, Any]]:
    """
    Edges whose magnitude rests on judgement rather than data, worst first. This is the
    'what would need research' list surfaced next to every run.
    """
    out: list[dict[str, Any]] = []
    for edge in edges:
        if edge.evidence:
            continue
        out.append({
            "edge": edge.id,
            "source": edge.source,
            "target": edge.target,
            "status": edge.status,
            "confidence": edge.confidence,
            "effect_span": edge.effect.span(),
            "mechanism": edge.mechanism,
            "needs": "empirical estimate of effect size and lag",
        })
    out.sort(key=lambda d: (-float(d["effect_span"]), str(d["edge"])))
    return out
