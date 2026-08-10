"""
World Builder: select the relevant slice of the world for a question.

A simulation must load only the part of the world it can defend. Just as important, it
must state what it left out — `WorldSlice.excluded_systems` is populated from the library
so a user can see that "labour market" or "insurance" was not modelled at all, rather than
discovering it from a surprising result.

No LLM is involved here. Slice selection is: named modules (explicit) or a keyword match
against module ids, titles and domains (deterministic). An LLM may later *propose* which
modules to include; it would then hand a module id list to this function, and the slice
would still be assembled and validated here.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Sequence

from event_sim.evidence import evidence_coverage, missing_evidence
from event_sim.registry import available_modules, get_module
from event_sim.schemas import (
    AssumptionAxis,
    CausalEdgeEvidence,
    VariableDefinition,
    WorldModule,
    WorldSlice,
)


def _assumption_records(
    variables: Sequence[VariableDefinition],
    edges: Sequence[CausalEdgeEvidence],
    axes: Sequence[AssumptionAxis],
) -> list[dict[str, Any]]:
    """
    Every judgement call the slice rests on, weakest evidence first. This is the
    "Assumptions" panel: it must be readable without reading the module file.
    """
    records: list[dict[str, Any]] = []
    for edge in edges:
        records.append({
            "kind": "causal_edge",
            "id": edge.id,
            "statement": (
                f"{edge.source} affects {edge.target} "
                f"({edge.polarity}, effect {edge.effect.low}-{edge.effect.high}, "
                f"lag {edge.lag.min}-{edge.lag.max} {edge.lag.unit})"
            ),
            "status": edge.status,
            "confidence": edge.confidence,
            "sourced": bool(edge.evidence),
            "mechanism": edge.mechanism,
            "effect_span": edge.effect.span(),
        })
    for var in variables:
        records.append({
            "kind": "variable_dynamics",
            "id": var.id,
            "statement": (
                f"{var.id} baseline {var.baseline} {var.unit}, "
                f"closes {var.response:.0%} of the gap to causal pressure per turn"
            ),
            "status": var.status,
            "confidence": "low",
            "sourced": False,
            "mechanism": var.description,
            "effect_span": 0.0,
        })
    for axis in axes:
        records.append({
            "kind": "assumption_axis",
            "id": axis.id,
            "statement": f"{axis.label}: swept over {', '.join(axis.settings)}",
            "status": axis.status,
            "confidence": "low",
            "sourced": False,
            "mechanism": axis.description,
            "effect_span": 0.0,
        })
    order = {"observed": 0, "empirical": 1, "literature_backed": 2, "historically_calibrated": 3,
             "expert_assumption": 4, "user_assumption": 5, "ai_hypothesis": 6}
    records.sort(key=lambda r: (-order.get(str(r["status"]), 9), -float(r["effect_span"]), str(r["id"])))
    return records


def build_slice(
    module_ids: Iterable[str],
    *,
    question: str = "",
    slice_id: str | None = None,
    include_variables: Sequence[str] | None = None,
    extra_edges: Sequence[CausalEdgeEvidence] | None = None,
) -> WorldSlice:
    """
    Assemble a WorldSlice from named modules.

    `include_variables` narrows the slice further (edges whose endpoints fall outside the
    kept set are dropped and recorded as excluded). `extra_edges` allows a caller to add
    user- or AI-proposed edges; they keep whatever status they declare and are counted in
    coverage like any other edge.
    """
    # Deep-copy out of the module registry. Modules are cached process-wide, so handing a
    # slice the registry's own VariableDefinition / CausalEdgeEvidence objects would let any
    # caller that tunes a slice (calibration trials, replay baseline overrides, a user
    # editing an assumption) silently mutate the shipped module for every later run.
    modules: list[WorldModule] = [copy.deepcopy(get_module(mid)) for mid in module_ids]
    if not modules:
        raise ValueError("build_slice requires at least one module id")

    variables: list[VariableDefinition] = []
    edges: list[CausalEdgeEvidence] = []
    axes: list[AssumptionAxis] = []
    interventions: list[dict[str, Any]] = []
    seen_vars: set[str] = set()
    seen_axes: set[str] = set()

    for module in modules:
        for var in module.variables:
            if var.id in seen_vars:
                continue
            seen_vars.add(var.id)
            variables.append(var)
        edges.extend(module.edges)
        for axis in module.axes:
            if axis.id in seen_axes:
                continue
            seen_axes.add(axis.id)
            axes.append(axis)
        for iv in module.interventions:
            interventions.append({**iv, "module": module.id})

    excluded_systems: list[str] = []
    if include_variables is not None:
        keep = set(include_variables)
        dropped = [v.id for v in variables if v.id not in keep]
        variables = [v for v in variables if v.id in keep]
        edges = [e for e in edges if e.source in keep and e.target in keep]
        excluded_systems.extend(f"variable:{v}" for v in sorted(dropped))

    edges.extend(extra_edges or [])

    included_ids = {m.id for m in modules}
    for summary in available_modules():
        if summary["id"] not in included_ids:
            excluded_systems.append(f"{summary['domain']}/{summary['id']}")

    time_units = {m.time_unit for m in modules}
    if len(time_units) > 1:
        raise ValueError(
            f"Cannot compose modules with different time units: {sorted(time_units)}"
        )

    slice_ = WorldSlice(
        id=slice_id or "+".join(sorted(included_ids)),
        question=question,
        time_unit=modules[0].time_unit,
        included_systems=[f"{m.domain}/{m.id}" for m in modules],
        excluded_systems=excluded_systems,
        variables=variables,
        edges=edges,
        axes=axes,
        interventions=interventions,
        assumptions=_assumption_records(variables, edges, axes),
        missing_evidence=missing_evidence(edges),
        coverage=evidence_coverage(edges, variables),
    )
    return slice_


def describe_slice(slice_: WorldSlice) -> dict[str, Any]:
    """
    Inspectable summary: what is in, what is out, what it assumes, what evidence is
    missing. Used by GET /api/event_sim/slice and by the CLI demo.
    """
    return {
        "id": slice_.id,
        "question": slice_.question,
        "time_unit": slice_.time_unit,
        "included_systems": list(slice_.included_systems),
        "excluded_systems": list(slice_.excluded_systems),
        "variables": [
            {
                "id": v.id,
                "label": v.label,
                "unit": v.unit,
                "baseline": v.baseline,
                "range": {"min": v.minimum, "max": v.maximum},
                "response": v.response,
                "observability": v.observability,
                "status": v.status,
            }
            for v in slice_.variables
        ],
        "edges": [
            {
                "id": e.id,
                "source": e.source,
                "target": e.target,
                "polarity": e.polarity,
                "effect": e.effect.to_dict(),
                "lag": e.lag.to_dict(),
                "status": e.status,
                "confidence": e.confidence,
                "sourced": bool(e.evidence),
                "axis": e.axis,
                "mechanism": e.mechanism,
            }
            for e in slice_.edges
        ],
        "axes": [a.to_dict() for a in slice_.axes],
        "interventions": [dict(i) for i in slice_.interventions],
        "assumptions": list(slice_.assumptions),
        "missing_evidence": list(slice_.missing_evidence),
        "coverage": dict(slice_.coverage),
    }
