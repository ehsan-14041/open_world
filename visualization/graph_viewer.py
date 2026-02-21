"""
Graph viewer: prepare causal variable graph data for visualization.
Converts world_state (variables + causal_links) to nodes and edges format.
"""

from __future__ import annotations

from typing import Any


def prepare_graph_data(world_state: dict[str, Any]) -> dict[str, Any]:
    """
    Convert world_state snapshot to graph data structure for visualization.
    
    Args:
        world_state: Snapshot dict with 'variables' (dict[str, float]) and 
                     'causal_links' (list[dict]) keys.
    
    Returns:
        Dict with 'nodes' and 'edges' lists, plus optional 'turn' field.
        Nodes: [{"id": str, "value": float, "magnitude": float}, ...]
        Edges: [{"source": str, "target": str, "weight": float}, ...]
    """
    if world_state is None or not isinstance(world_state, dict):
        return {"nodes": [], "edges": [], "turn": 0}
    variables = world_state.get("variables") or world_state.get("global_state") or {}
    causal_links = world_state.get("causal_links") or []
    turn = world_state.get("turn", 0)
    
    # Build nodes from variables
    nodes = []
    for var_name, var_value in variables.items():
        if not isinstance(var_name, str):
            continue
        try:
            value = float(var_value) if isinstance(var_value, (int, float)) else 0.0
            nodes.append({
                "id": var_name,
                "value": value,
                "magnitude": abs(value),
            })
        except (TypeError, ValueError):
            continue
    
    # Build edges from causal_links
    edges = []
    for link in causal_links:
        if not isinstance(link, dict):
            continue
        from_var = link.get("from")
        to_var = link.get("to")
        weight = link.get("weight", 0.0)
        
        if not isinstance(from_var, str) or not isinstance(to_var, str):
            continue
        
        try:
            weight_val = float(weight)
            edges.append({
                "source": from_var,
                "target": to_var,
                "weight": weight_val,
            })
        except (TypeError, ValueError):
            continue
    
    result = {
        "nodes": nodes,
        "edges": edges,
        "turn": turn,
    }
    
    return result
