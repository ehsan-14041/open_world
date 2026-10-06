"""
Causal trace: read the explanation out of execution, never reconstruct it afterwards.

Every turn the engine records, per variable, the exact contribution of each incoming edge
(`coefficient x source deviation at the lagged turn`). This module walks those records
backwards, so the chain

    service_level ↓  because  inventory_availability ↓
                   because  shipping_delay ↑
                   because  port_capacity ↓ (injected event)

is a report of arithmetic that actually happened, with the responsible edge's evidence
status attached at every link. An LLM may render this into prose; it cannot author it.
"""

from __future__ import annotations

from typing import Any

from event_sim.engine import EventSimulation

#: Contributions smaller than this share of the total pressure on a variable are omitted
#: from the trace to keep the chain readable.
MIN_SHARE = 0.05


def _provenance_for_turn(sim: EventSimulation, turn: int) -> dict[str, Any] | None:
    for record in sim.provenance:
        if record.get("turn") == turn:
            return record
    return None


def _direction(value: float) -> str:
    if value > 1e-9:
        return "up"
    if value < -1e-9:
        return "down"
    return "flat"


def explain(
    sim: EventSimulation,
    variable: str,
    turn: int,
    *,
    max_depth: int = 4,
    min_share: float = MIN_SHARE,
) -> dict[str, Any]:
    """
    Backward causal chain for one variable at one turn.

    Each node reports the variable's value and deviation, and its drivers ranked by the
    absolute size of their contribution. Recursion follows each driver to the turn its
    contribution was actually read from (turn − lag), which is what makes the chain
    honest about time.
    """
    return _explain_node(sim, variable, turn, depth=0, max_depth=max_depth,
                         min_share=min_share, seen=set())


def _explain_node(
    sim: EventSimulation,
    variable: str,
    turn: int,
    *,
    depth: int,
    max_depth: int,
    min_share: float,
    seen: set[tuple[str, int]],
) -> dict[str, Any]:
    var_def = sim.slice.variable(variable)
    turn = max(0, min(turn, sim.world.turn))
    record = sim.trajectory[turn] if turn < len(sim.trajectory) else sim.trajectory[-1]
    var_record = next((v for v in record["variables"] if v["variable"] == variable), None)

    node: dict[str, Any] = {
        "variable": variable,
        "label": var_def.label if var_def else variable,
        "unit": var_def.unit if var_def else "",
        "turn": turn,
        "value": (var_record or {}).get("value"),
        "baseline": var_def.baseline if var_def else None,
        "deviation": (var_record or {}).get("deviation", 0.0),
        "direction": _direction((var_record or {}).get("deviation", 0.0)),
        "held_by_event": bool((var_record or {}).get("held_by_event")),
        "intervention_offset": (var_record or {}).get("intervention_offset", 0.0),
        "drivers": [],
    }

    key = (variable, turn)
    if key in seen or depth >= max_depth or turn == 0:
        if node["held_by_event"]:
            node["terminal_reason"] = "injected event"
        elif turn == 0:
            node["terminal_reason"] = "baseline state"
        elif key in seen:
            node["terminal_reason"] = "already explained (feedback loop)"
        else:
            node["terminal_reason"] = "trace depth limit"
        return node
    seen = seen | {key}

    if node["held_by_event"]:
        # The event is the explanation. Incoming pressure is recorded but overridden, so
        # presenting it as the cause would be false attribution.
        node["terminal_reason"] = "injected event holds this variable"
        events = record.get("events_active") or []
        node["drivers"] = [{
            "kind": "event",
            "id": e,
            "description": f"Event {e} holds {variable} at its injected level",
        } for e in events]
        return node

    prov = _provenance_for_turn(sim, turn)
    contributions = ((prov or {}).get("contributions") or {}).get(variable) or []
    total = sum(abs(float(c["contribution"])) for c in contributions)
    if total <= 0:
        if abs(float(node["intervention_offset"] or 0.0)) > 1e-12:
            node["terminal_reason"] = "intervention offset"
            node["drivers"] = [{
                "kind": "intervention",
                "id": iv,
                "description": f"Intervention {iv} offsets {variable} directly",
            } for iv in (record.get("interventions_active") or [])]
        else:
            node["terminal_reason"] = "no incoming causal pressure this turn"
        return node

    ranked = sorted(contributions, key=lambda c: -abs(float(c["contribution"])))
    for contrib in ranked:
        share = abs(float(contrib["contribution"])) / total
        if share < min_share:
            continue
        driver = {
            "kind": "causal_edge",
            "edge": contrib["edge"],
            "source": contrib["source"],
            "contribution": contrib["contribution"],
            "share_of_pressure": share,
            "coefficient": contrib["coefficient"],
            "effect_setting": contrib["effect_setting"],
            "lag": contrib["lag"],
            "evidence_status": contrib["evidence_status"],
            "confidence": contrib["confidence"],
            "direction": _direction(float(contrib["contribution"])),
            "because": _explain_node(
                sim,
                str(contrib["source"]),
                int(contrib["source_turn"]),
                depth=depth + 1,
                max_depth=max_depth,
                min_share=min_share,
                seen=seen,
            ),
        }
        node["drivers"].append(driver)
    return node


def flatten(node: dict[str, Any], _depth: int = 0) -> list[dict[str, Any]]:
    """Flatten a trace to an ordered list of links, for tabular display."""
    rows: list[dict[str, Any]] = [{
        "depth": _depth,
        "variable": node["variable"],
        "turn": node["turn"],
        "value": node.get("value"),
        "direction": node.get("direction"),
        "terminal_reason": node.get("terminal_reason"),
    }]
    for driver in node.get("drivers", []):
        rows.append({
            "depth": _depth,
            "edge": driver.get("edge"),
            "source": driver.get("source"),
            "contribution": driver.get("contribution"),
            "share_of_pressure": driver.get("share_of_pressure"),
            "lag": driver.get("lag"),
            "evidence_status": driver.get("evidence_status"),
        })
        if driver.get("because"):
            rows.extend(flatten(driver["because"], _depth + 1))
    return rows


def render_text(node: dict[str, Any], indent: int = 0) -> str:
    """
    Plain-text rendering of the chain, produced from simulation provenance only.
    Deliberately deterministic: no model is invoked to write this.
    """
    pad = "    " * indent
    arrow = {"up": "^", "down": "v", "flat": "-"}.get(str(node.get("direction")), "-")
    value = node.get("value")
    value_str = f"{value:.3g}" if isinstance(value, (int, float)) else "?"
    lines = [f"{pad}{node['variable']} {arrow} (t{node['turn']} = {value_str})"]
    if node.get("terminal_reason") and not node.get("drivers"):
        lines.append(f"{pad}    <- {node['terminal_reason']}")
    for driver in node.get("drivers", []):
        if driver.get("kind") != "causal_edge":
            lines.append(f"{pad}    <- {driver.get('description', driver.get('id'))}")
            continue
        lines.append(
            f"{pad}    <- {driver['share_of_pressure']:.0%} via {driver['edge']} "
            f"(lag {driver['lag']}, {driver['evidence_status']})"
        )
        if driver.get("because"):
            lines.append(render_text(driver["because"], indent + 2))
    return "\n".join(lines)


def dominant_path(sim: EventSimulation, variable: str, turn: int, *, max_depth: int = 5) -> list[dict[str, Any]]:
    """
    The single strongest causal path into `variable` at `turn` — the chain to show first
    in a UI. Follows the largest contribution at each step.
    """
    path: list[dict[str, Any]] = []
    node = explain(sim, variable, turn, max_depth=max_depth, min_share=0.0)
    while True:
        path.append({
            "variable": node["variable"],
            "turn": node["turn"],
            "value": node.get("value"),
            "direction": node.get("direction"),
            "terminal_reason": node.get("terminal_reason"),
        })
        drivers = [d for d in node.get("drivers", []) if d.get("kind") == "causal_edge"]
        if not drivers:
            break
        best = drivers[0]
        path[-1]["via"] = {
            "edge": best["edge"],
            "lag": best["lag"],
            "evidence_status": best["evidence_status"],
            "share_of_pressure": best["share_of_pressure"],
        }
        node = best["because"]
        if not node:
            break
    return path
