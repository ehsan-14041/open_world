"""
Structural causal graph only. No action/turn logs in causal_links.
Entries: from, to, edge_model: { type, params, delay?, decay? }.
Backward compatible: legacy weight/polarity/strength normalized to edge_model.linear.
"""

from __future__ import annotations

from typing import Any, Literal

EdgeModelType = Literal["linear", "logistic", "ordinal_shift", "categorical_influence", "custom"]

# Structural keys only; presence of any of these in a link means it is action provenance, not structure.
ACTION_LOG_KEYS = frozenset({"from_action", "agent", "variable", "delta", "turn", "repaired"})


def is_structural_link(link: dict[str, Any]) -> bool:
    """True if link is structural only (no action/turn log fields)."""
    if not isinstance(link, dict):
        return False
    return not ACTION_LOG_KEYS.intersection(link.keys())


def structural_causal_links(causal_links: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """
    Filter to structural links only: must have 'from' and 'to'.
    Exclude any link that contains action provenance keys.
    """
    out: list[dict[str, Any]] = []
    for link in causal_links or []:
        if not isinstance(link, dict):
            continue
        if not is_structural_link(link):
            continue
        from_var = link.get("from")
        to_var = link.get("to")
        if not from_var or not to_var:
            continue
        out.append(normalize_link(link))
    return out


def normalize_link(link: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a causal link to v2 structural form: from, to, edge_model.
    Legacy weight/polarity/strength -> edge_model { type: "linear", params: { weight } }.
    """
    out: dict[str, Any] = {
        "from": link.get("from"),
        "to": link.get("to"),
    }
    em = link.get("edge_model")
    if isinstance(em, dict) and em.get("type"):
        out["edge_model"] = dict(em)
        return out
    # Legacy
    weight = link.get("weight")
    if weight is None:
        pol = (link.get("polarity") or "positive").strip().lower()
        strength = float(link.get("strength", 0.5))
        weight = -strength if pol == "negative" else strength
    try:
        w = float(weight)
    except (TypeError, ValueError):
        w = 0.5
    out["edge_model"] = {
        "type": "linear",
        "params": {"weight": w},
        "delay": link.get("delay") if isinstance(link.get("delay"), int) else None,
        "decay": link.get("decay") if isinstance(link.get("decay"), (int, float)) else None,
    }
    return out


def get_weight_for_propagation(link: dict[str, Any]) -> float:
    """Extract propagation weight from structural link (linear weight or equivalent)."""
    em = link.get("edge_model")
    if isinstance(em, dict):
        params = em.get("params") or {}
        if "weight" in params:
            try:
                return float(params["weight"])
            except (TypeError, ValueError):
                pass
        # logistic/ordinal_shift may have strength
        if "strength" in params:
            try:
                return float(params["strength"])
            except (TypeError, ValueError):
                pass
    # Legacy
    w = link.get("weight")
    if w is not None:
        try:
            return float(w)
        except (TypeError, ValueError):
            pass
    pol = (link.get("polarity") or "positive").lower()
    strength = float(link.get("strength", 0.5))
    return -strength if pol == "negative" else strength


def get_delay(link: dict[str, Any]) -> int:
    """Delay in turns (0 = immediate)."""
    em = link.get("edge_model")
    if isinstance(em, dict) and isinstance(em.get("delay"), int):
        return max(0, em["delay"])
    return max(0, int(link.get("delay", 0)))


def get_decay(link: dict[str, Any]) -> float | None:
    """Decay factor per turn, if any."""
    em = link.get("edge_model")
    if isinstance(em, dict) and em.get("decay") is not None:
        try:
            return float(em["decay"])
        except (TypeError, ValueError):
            pass
    if link.get("decay") is not None:
        try:
            return float(link["decay"])
        except (TypeError, ValueError):
            pass
    return None
