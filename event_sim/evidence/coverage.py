"""
Evidence coverage, evidence strength, and the evidence-gap report.

Three things live here, all deterministic and all documented:

1. **Weighted coverage** — plain edge counts let one well-sourced trivial edge make a model
   look grounded. Weighted coverage counts an edge in proportion to how much it actually
   moves the outcome.
2. **Evidence strength** — a low/medium/high label derived by an explicit rule from source
   type, source count and proxy usage. No model assigns it; it is arithmetic on metadata.
3. **The gap report** — high-influence / low-evidence edges, worst first. This is the
   product's answer to "what do we most need to find out?", and it drives the data
   requirements list.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from event_sim.evidence.registry import (
    EvidenceRegistryError,
    calibrations_for_edge,
    mappings_for_variable,
    resolve_source_ids,
)
from event_sim.schemas import CausalEdgeEvidence, WorldSlice

# --------------------------------------------------------------------------------------
# Evidence strength (item 23: derived from evidence properties, never assigned by a model)
# --------------------------------------------------------------------------------------

#: Points contributed by the edge's declared status.
_STATUS_POINTS: dict[str, int] = {
    "observed": 3,
    "empirical": 3,
    "historically_calibrated": 2,
    "literature_backed": 2,
    "expert_assumption": 0,
    "user_assumption": 0,
    "ai_hypothesis": 0,
}

STRENGTH_RULE = (
    "score = status_points (observed/empirical 3, historically_calibrated/literature_backed 2, "
    "assumption/hypothesis 0) + 1 if two or more citable sources + 1 if a calibration record "
    "exists - 1 if any input to this edge relies on a proxy mapping. "
    "score >= 3 -> high, 1-2 -> medium, <= 0 -> low."
)


def evidence_strength(edge: CausalEdgeEvidence) -> dict[str, Any]:
    """
    Deterministic low/medium/high label for one edge, with the components that produced it.

    The components are returned so a reader can see *why* an edge scored what it did rather
    than trusting the label.
    """
    components: dict[str, Any] = {"status": edge.status, "status_points": _STATUS_POINTS.get(edge.status, 0)}
    score = components["status_points"]

    try:
        sources = resolve_source_ids([e.reference for e in edge.evidence if e.reference])
    except EvidenceRegistryError:
        sources = []
    citable = [s for s in sources if s.is_citable()]
    components["citable_sources"] = len(citable)
    if len(citable) >= 2:
        score += 1

    calibrations = calibrations_for_edge(edge.id)
    components["calibration_records"] = len(calibrations)
    if calibrations:
        score += 1

    proxies = [
        m for var in (edge.source, edge.target)
        for m in mappings_for_variable(var)
        if m.mapping_type == "proxy"
    ]
    components["proxy_mappings"] = sorted({m.id for m in proxies})
    if proxies:
        score -= 1

    label = "high" if score >= 3 else ("medium" if score >= 1 else "low")
    return {
        "edge": edge.id,
        "score": score,
        "label": label,
        "components": components,
        "rule": STRENGTH_RULE,
    }


# --------------------------------------------------------------------------------------
# Structural influence (used when no sweep result is available)
# --------------------------------------------------------------------------------------


def structural_influence(slice_: WorldSlice) -> dict[str, float]:
    """
    How much each edge can matter, from graph structure alone.

    weight(e) = |central effect| x (1 + number of variables reachable downstream of e.target)

    Rationale: an edge with a large coefficient that feeds a long downstream chain can move
    more of the model than an equally large edge that terminates. Normalised to [0, 1] over
    the slice so it can be compared with sweep-derived influence.

    This is a *structural upper bound on relevance*, not a measured effect. Where a sweep
    result exists, prefer `pivotal_assumptions` — see `merge_influence`.
    """
    downstream: dict[str, set[str]] = {}
    edges_from: dict[str, list[CausalEdgeEvidence]] = {}
    for edge in slice_.edges:
        edges_from.setdefault(edge.source, []).append(edge)

    def _reach(var: str, seen: frozenset[str]) -> set[str]:
        if var in downstream:
            return downstream[var]
        out: set[str] = set()
        for edge in edges_from.get(var, []):
            if edge.target in seen:
                continue  # feedback loop: count each variable once
            out.add(edge.target)
            out |= _reach(edge.target, seen | {edge.target})
        return out

    raw: dict[str, float] = {}
    for edge in slice_.edges:
        reach = _reach(edge.target, frozenset({edge.source, edge.target}))
        raw[edge.id] = abs(edge.effect.central) * (1.0 + len(reach))

    peak = max(raw.values()) if raw else 0.0
    return {k: (v / peak if peak else 0.0) for k, v in raw.items()}


def merge_influence(
    slice_: WorldSlice,
    pivotal: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Per-edge influence, preferring measured sweep influence over structural influence.

    An edge bound to an assumption axis inherits that axis's measured outcome span (from
    `event_sim.sweep.pivotal_assumptions`). Edges with no axis fall back to structure.
    """
    structural = structural_influence(slice_)
    axis_influence: dict[str, float] = {}
    axis_rank: dict[str, str] = {}
    if pivotal:
        spans = [float(a.get("relative_influence", 0.0)) for a in pivotal.get("axes", [])]
        peak = max(spans) if spans else 0.0
        for axis in pivotal.get("axes", []):
            rel = float(axis.get("relative_influence", 0.0))
            axis_influence[str(axis["axis"])] = (rel / peak) if peak else 0.0
            axis_rank[str(axis["axis"])] = str(axis.get("rank", ""))

    out: dict[str, dict[str, Any]] = {}
    for edge in slice_.edges:
        axis_id = edge.axis
        if axis_id is None:
            for axis in slice_.axes:
                if edge.id in axis.applies_to:
                    axis_id = axis.id
                    break
        if axis_id and axis_id in axis_influence:
            out[edge.id] = {
                "influence": axis_influence[axis_id],
                "basis": "swept_axis",
                "axis": axis_id,
                "rank": axis_rank.get(axis_id, ""),
            }
        else:
            value = structural.get(edge.id, 0.0)
            out[edge.id] = {
                "influence": value,
                "basis": "structural",
                "axis": axis_id,
                "rank": "HIGH" if value >= 0.66 else ("MEDIUM" if value >= 0.33 else "LOW"),
            }
    return out


# --------------------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------------------

WEIGHTING_METHOD = (
    "Each edge is weighted by its influence: measured outcome span for edges bound to a "
    "swept assumption axis, otherwise |central effect| x (1 + downstream reach), normalised "
    "to the slice. Weighted coverage is the influence-weighted share of edges in each "
    "evidence group, so a well-sourced but inconsequential edge cannot make the model look "
    "grounded."
)


def weighted_coverage(
    edges: Sequence[CausalEdgeEvidence],
    influence: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Influence-weighted evidence coverage, alongside the unweighted counts."""
    from event_sim.evidence.validation import evidence_coverage
    from event_sim.schemas import EVIDENCE_STATUS_GROUP

    base = evidence_coverage(edges)
    total_weight = sum(float(influence.get(e.id, {}).get("influence", 0.0)) for e in edges)
    by_group: dict[str, float] = {g: 0.0 for g in base["by_group"]}
    for edge in edges:
        group = EVIDENCE_STATUS_GROUP.get(edge.status, "ai_hypothesis")
        by_group[group] = by_group.get(group, 0.0) + float(
            influence.get(edge.id, {}).get("influence", 0.0)
        )
    shares = {g: (w / total_weight if total_weight else 0.0) for g, w in by_group.items()}
    assumption_share = shares.get("assumption", 0.0) + shares.get("ai_hypothesis", 0.0)

    base["weighted"] = {
        "by_group": by_group,
        "shares": shares,
        "assumption_share": assumption_share,
        "total_weight": total_weight,
        "weighting_method": WEIGHTING_METHOD,
        "weakly_evidenced": total_weight > 0 and assumption_share >= 0.5,
    }
    return base


# --------------------------------------------------------------------------------------
# Gap report (items 25, 26, 27)
# --------------------------------------------------------------------------------------

#: What kind of data would resolve each treatment class, per the evidence audit.
_TREATMENT_HINTS: dict[str, str] = {
    "customer_data": "a customer operational export (weekly series) covering both endpoints",
    "public_data": "a public time series for both endpoints at a compatible frequency",
    "literature": "a published effect-size estimate for this mechanism",
    "replay": "a historical disruption with observed series for the target variable",
}


def evidence_gap_report(
    slice_: WorldSlice,
    *,
    pivotal: dict[str, Any] | None = None,
    top: int | None = None,
) -> dict[str, Any]:
    """
    High-influence / low-evidence edges, worst first — the model's research priorities.

    Priority = influence x (1 - normalised evidence strength). An edge that barely moves the
    outcome is not a priority however weakly evidenced it is, and a well-evidenced edge is
    not a priority however influential.
    """
    influence = merge_influence(slice_, pivotal)
    rows: list[dict[str, Any]] = []
    for edge in slice_.edges:
        strength = evidence_strength(edge)
        infl = float(influence.get(edge.id, {}).get("influence", 0.0))
        strength_norm = {"low": 0.0, "medium": 0.5, "high": 1.0}[strength["label"]]
        rows.append({
            "edge": edge.id,
            "source": edge.source,
            "target": edge.target,
            "influence": infl,
            "influence_rank": influence.get(edge.id, {}).get("rank", ""),
            "influence_basis": influence.get(edge.id, {}).get("basis", ""),
            "evidence": strength["label"].upper(),
            "evidence_score": strength["score"],
            "status": edge.status,
            "priority": infl * (1.0 - strength_norm),
            "mechanism": edge.mechanism,
            "effect_span": edge.effect.span(),
        })
    rows.sort(key=lambda r: (-float(r["priority"]), str(r["edge"])))
    if top:
        rows = rows[:top]

    critical = [r for r in rows if r["influence_rank"] == "HIGH" and r["evidence"] == "LOW"]
    return {
        "gaps": rows,
        "high_influence_low_evidence": critical,
        "priority_formula": "priority = influence x (1 - evidence_strength), evidence_strength in {low:0, medium:0.5, high:1}",
        "strength_rule": STRENGTH_RULE,
        "framing": (
            "These are the assumptions that most change the answer and are least supported. "
            "They are research priorities, not errors."
        ),
    }


def data_requirements(gap_report: dict[str, Any], slice_: WorldSlice, *, top: int = 5) -> list[dict[str, Any]]:
    """
    What to collect, tied to a specific unresolved edge.

    Every requested variable names the edge it would resolve; there are no generic
    "collect more data" recommendations.
    """
    out: list[dict[str, Any]] = []
    for row in gap_report["gaps"][:top]:
        if row["evidence"] == "HIGH":
            continue
        source_var = slice_.variable(str(row["source"]))
        target_var = slice_.variable(str(row["target"]))
        out.append({
            "edge": row["edge"],
            "why": (
                f"{row['edge']} has {row['influence_rank'] or 'unranked'} influence on the "
                f"outcome and {row['evidence']} evidence ({row['status']})"
            ),
            "collect": [
                {
                    "variable": v.id,
                    "unit": v.unit,
                    "frequency": slice_.time_unit,
                    "observability": v.observability,
                }
                for v in (source_var, target_var) if v is not None
            ],
            "would_enable": (
                "empirical fit of this edge's effect size and lag"
                if row["status"] in ("expert_assumption", "user_assumption", "ai_hypothesis")
                else "tighter effect range"
            ),
            "likely_holder": (
                "the operating company (internal metric)"
                if any(v is not None and v.observability != "measured" for v in (source_var, target_var))
                else "public or commercial data provider"
            ),
        })
    return out
