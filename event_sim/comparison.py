"""
World comparison: two branches from one checkpoint, diffed under identical conditions.

This is the capability an LLM answer cannot supply. Both worlds start from a *provably*
identical state (the same CheckpointStore entry), share the same slice, the same
assumption settings and the same injected event; the only difference is the intervention.
Any divergence is therefore attributable to the intervention and to nothing else.
"""

from __future__ import annotations

from typing import Any, Sequence

from event_sim.engine import EventSimulation

#: A variable is reported as materially different when the branches differ by more than
#: this share of the variable's own scale. Presentation threshold only.
MATERIAL_DIFFERENCE = 0.01


def _series(sim: EventSimulation, variable: str) -> dict[int, float]:
    return {int(rec["turn"]): float(rec["state"].get(variable, 0.0)) for rec in sim.trajectory}


def compare(
    world_a: EventSimulation,
    world_b: EventSimulation,
    *,
    variables: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Compare two worlds turn by turn. Returns per-variable series, the final difference,
    the largest difference and the turn it occurred, plus the shared fork state so a
    reader can verify the branches really did start from the same world.
    """
    if world_a.slice.id != world_b.slice.id:
        raise ValueError("Cannot compare worlds built from different slices")

    var_ids = list(variables) if variables else [v.id for v in world_a.slice.variables]
    turns = sorted(set(_series(world_a, var_ids[0])) & set(_series(world_b, var_ids[0])))

    rows: list[dict[str, Any]] = []
    for vid in var_ids:
        var_def = world_a.slice.variable(vid)
        sa, sb = _series(world_a, vid), _series(world_b, vid)
        diffs = {t: sb.get(t, 0.0) - sa.get(t, 0.0) for t in turns}
        peak_turn = max(turns, key=lambda t: abs(diffs[t])) if turns else 0
        final_turn = turns[-1] if turns else 0
        scale = abs(var_def.scale) if var_def and var_def.scale else 1.0
        rows.append({
            "variable": vid,
            "label": var_def.label if var_def else vid,
            "unit": var_def.unit if var_def else "",
            "a": [sa.get(t) for t in turns],
            "b": [sb.get(t) for t in turns],
            "difference": [diffs[t] for t in turns],
            "final_a": sa.get(final_turn),
            "final_b": sb.get(final_turn),
            "final_difference": diffs.get(final_turn, 0.0),
            "peak_difference": diffs.get(peak_turn, 0.0),
            "peak_turn": peak_turn,
            "material": abs(diffs.get(peak_turn, 0.0)) / scale > MATERIAL_DIFFERENCE,
        })

    # Rank by how far the branches diverge relative to each variable's own scale, so a
    # freight index in points does not automatically outrank a fill rate in [0, 1].
    def _relative_divergence(row: dict[str, Any]) -> float:
        var_def = world_a.slice.variable(str(row["variable"]))
        scale = abs(var_def.scale) if var_def and var_def.scale else 1.0
        return abs(float(row["peak_difference"])) / scale

    rows.sort(key=lambda r: -_relative_divergence(r))

    fork_turn = world_b.fork_turn
    fork_state_a = next((r["state"] for r in world_a.trajectory if r["turn"] == fork_turn), None)
    fork_state_b = next((r["state"] for r in world_b.trajectory if r["turn"] == fork_turn), None)

    return {
        "turns": turns,
        "time_unit": world_a.slice.time_unit,
        "world_a": {
            "branch_id": world_a.branch_id,
            "label": world_a.config.label,
            "interventions": [i.to_dict() for i in world_a.interventions],
        },
        "world_b": {
            "branch_id": world_b.branch_id,
            "label": world_b.config.label,
            "interventions": [i.to_dict() for i in world_b.interventions],
        },
        "fork_turn": fork_turn,
        "identical_at_fork": fork_state_a == fork_state_b,
        "fork_state": fork_state_a,
        "same_assumptions": world_a.config.axis_settings == world_b.config.axis_settings,
        "variables": rows,
        "material_differences": [r["variable"] for r in rows if r["material"]],
        "framing": (
            "Both worlds start from the same checkpoint with the same assumption settings; "
            "the only difference is the intervention. Differences below are attributable to "
            "the intervention within this model — they are not a forecast of its real effect."
        ),
    }


def summarize(comparison: dict[str, Any], *, top: int = 5) -> list[str]:
    """Deterministic one-line summaries of the biggest differences (no LLM)."""
    out: list[str] = []
    unit = comparison.get("time_unit", "turns")
    for row in comparison["variables"][:top]:
        if not row["material"]:
            continue
        direction = "higher" if row["final_difference"] > 0 else "lower"
        out.append(
            f"{row['label']}: {abs(row['final_difference']):.3g} {row['unit'] or 'units'} "
            f"{direction} in {comparison['world_b']['label']} by {unit[:-1] if unit.endswith('s') else unit} "
            f"{comparison['turns'][-1]} (peak difference {row['peak_difference']:+.3g} at "
            f"{unit[:-1] if unit.endswith('s') else unit} {row['peak_turn']})"
        )
    if not out:
        out.append("No material difference between the two worlds under these assumptions.")
    return out
