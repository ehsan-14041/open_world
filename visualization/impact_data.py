"""
Impact data for causal graph visualization.
Computes deltas (initial vs final), top drivers, and activated edges from
snapshot + trace. Does not modify world_model or core simulation.
"""

from __future__ import annotations

from typing import Any


def _get_variables(snapshot: dict[str, Any]) -> dict[str, float]:
    """Extract variables dict from snapshot (variables or global_state) or flat var dict."""
    if snapshot is None or not isinstance(snapshot, dict):
        return {}
    raw = snapshot.get("variables") or snapshot.get("global_state")
    if raw is None:
        # Plain initial_state dict from scenario
        raw = snapshot
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        if isinstance(v, (int, float)):
            out[k] = float(v)
    return out


def compute_activated_edges(
    provenance: list[dict[str, Any]],
    causal_links: list[dict[str, Any]],
) -> set[tuple[str, str]]:
    """
    Infer which causal edges were activated during the simulation.
    An edge (from_var, to_var) is considered activated if in some step
    to_var received a propagation and from_var changed in that same step.
    """
    activated: set[tuple[str, str]] = set()
    link_map: dict[str, list[str]] = {}  # to_var -> [from_var, ...]
    for link in causal_links or []:
        if not isinstance(link, dict):
            continue
        from_v = link.get("from")
        to_v = link.get("to")
        if isinstance(from_v, str) and isinstance(to_v, str):
            link_map.setdefault(to_v, []).append(from_v)

    for step in provenance or []:
        variable_changes = step.get("variable_changes") or []
        changed_vars = {c.get("var") for c in variable_changes if c.get("var")}
        for c in variable_changes:
            if c.get("source") != "propagation":
                continue
            to_var = c.get("var")
            if not to_var:
                continue
            for from_var in link_map.get(to_var, []):
                if from_var in changed_vars:
                    activated.add((from_var, to_var))

    return activated


def prepare_impact_data(
    initial_state: dict[str, Any],
    final_snapshot: dict[str, Any],
    provenance: list[dict[str, Any]] | None = None,
    causal_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
    Compute impact metrics from initial state, final snapshot, and optional trace.

    Uses snapshot + trace only; does not touch world_model.

    Returns:
        Dict with:
          - initial_state: dict[str, float]
          - final_state: dict[str, float]
          - deltas: dict[str, float]  (final - initial per variable)
          - top_drivers: list[{"var": str, "delta": float, "abs_delta": float}]  (top 3 by |delta|)
          - activated_edges: list[{"from": str, "to": str}]
        or None if impact cannot be computed (e.g. missing initial/final).
    """
    init_vars = _get_variables(initial_state) if isinstance(initial_state, dict) else {}
    fin_vars = _get_variables(final_snapshot) if isinstance(final_snapshot, dict) else {}

    # All variables that appear in either state
    all_vars = set(init_vars) | set(fin_vars)
    if not all_vars:
        return None

    deltas: dict[str, float] = {}
    for var in all_vars:
        init_val = init_vars.get(var, 0.0)
        fin_val = fin_vars.get(var, 0.0)
        deltas[var] = fin_val - init_val

    # Top 3 by absolute delta
    sorted_vars = sorted(
        deltas.keys(),
        key=lambda v: abs(deltas[v]),
        reverse=True,
    )
    top_drivers = [
        {"var": v, "delta": deltas[v], "abs_delta": abs(deltas[v])}
        for v in sorted_vars[:3]
    ]

    # Activated edges from provenance
    links = causal_links if causal_links is not None else (final_snapshot.get("causal_links") or [])
    activated = compute_activated_edges(provenance or [], links)
    activated_list = [{"from": a, "to": b} for a, b in activated]

    return {
        "initial_state": init_vars,
        "final_state": fin_vars,
        "deltas": deltas,
        "top_drivers": top_drivers,
        "activated_edges": activated_list,
    }
