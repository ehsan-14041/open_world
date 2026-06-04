"""
Decision Brief: display-only mapping from the rich dashboard payload + per-turn
narrative into a small, human-readable structure for the focused product UI.

This module contains NO engine logic. It reuses `build_dashboard_payload`
(ui.dashboard_payload) and the per-turn `narrative` object produced by
`core.narrative_engine.generate_turn_narrative` (stored on each provenance
entry under the "narrative" key). Every field degrades gracefully when a
source value is missing, so a dry-run / rule-based run still yields a brief.

Guiding principle: we present "structured exploration of options and their
chained consequences", not numeric prediction. No accuracy claims; raw scores
are kept only for the advanced view.
"""

from __future__ import annotations

from typing import Any

from ui.dashboard_payload import build_dashboard_payload


def _dedup_keep_order(items: list[str], limit: int) -> list[str]:
    """Return up to `limit` unique non-empty strings, preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        s = (str(it) if it is not None else "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def _extract_regime(narrative: dict[str, Any]) -> str:
    """Pull the regime label (NORMAL/FRAGILE/CRISIS) from narrative tags."""
    for tag in narrative.get("tags") or []:
        if isinstance(tag, dict) and tag.get("kind") == "regime":
            val = str(tag.get("value") or "").strip().upper()
            if val:
                return val
    return "NORMAL"


def _confidence_level(calibration: dict[str, Any], explanation: dict[str, Any]) -> str:
    """Map calibration health + explanation hint to a coarse level: low|moderate|high."""
    health = str(calibration.get("health") or "").strip().lower()
    if health in ("red",):
        return "low"
    if health in ("green",):
        # Trust explanation's own read when calibration is healthy.
        return str(explanation.get("confidence_level") or "high").strip().lower() or "high"
    if health in ("yellow",):
        return "moderate"
    # No calibration signal: fall back to explanation.
    return str(explanation.get("confidence_level") or "moderate").strip().lower() or "moderate"


def build_decision_brief(
    final_snapshot: dict[str, Any],
    provenance: list[dict[str, Any]] | None,
    scenario: dict[str, Any],
    agents_list: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build a compact Decision Brief from a completed run.

    Args:
        final_snapshot: the final world snapshot (loop result["final"]).
        provenance: the full list of per-turn provenance entries.
        scenario: the (normalized) scenario dict.
        agents_list: optional list of agent dicts (name/role/objectives).

    Returns:
        A dict with human-facing sections:
        situation, what_likely_happens, outcome, key_drivers (list),
        hidden_risks (list), regime (level + commentary), confidence
        (level + note), trajectory (optional), and raw_risk_score
        (de-emphasized, for the advanced view only).
    """
    provenance = provenance or []
    agents_list = agents_list or []
    last_pe = provenance[-1] if provenance else {}

    # Reuse the canonical payload builder for risk / calibration / explanation / assumptions.
    try:
        payload = build_dashboard_payload(
            final_snapshot or {},
            last_pe,
            scenario or {},
            agents_list,
            provenance_history=provenance,
        )
    except Exception:
        payload = {}

    narrative = last_pe.get("narrative") if isinstance(last_pe, dict) else None
    narrative = narrative if isinstance(narrative, dict) else {}
    explanation = payload.get("explanation") if isinstance(payload.get("explanation"), dict) else {}
    risk = payload.get("risk_report") if isinstance(payload.get("risk_report"), dict) else {}
    calibration = payload.get("calibration_metrics") if isinstance(payload.get("calibration_metrics"), dict) else {}
    assumptions = payload.get("assumption_summary") if isinstance(payload.get("assumption_summary"), list) else []

    # --- What likely happens ---
    what = (
        explanation.get("narrative_summary")
        or narrative.get("turn_summary")
        or ""
    )
    outcome = (narrative.get("outcome_assessment") or {}).get("outcome") if isinstance(narrative.get("outcome_assessment"), dict) else ""

    # --- Key drivers ---
    drivers_src = explanation.get("top_drivers") or narrative.get("key_drivers") or []
    if not isinstance(drivers_src, list):
        drivers_src = []
    key_drivers = _dedup_keep_order([str(d) for d in drivers_src], limit=3)

    # --- Hidden risks: narrative hidden costs + assumption "risk if wrong" ---
    risk_items: list[str] = []
    for hc in narrative.get("hidden_costs") or []:
        if isinstance(hc, str):
            risk_items.append(hc)
        elif isinstance(hc, dict):
            risk_items.append(str(hc.get("description") or hc.get("text") or hc.get("cost") or ""))
    for a in assumptions:
        if isinstance(a, dict) and a.get("risk_if_wrong"):
            risk_items.append(str(a.get("risk_if_wrong")))
    hidden_risks = _dedup_keep_order(risk_items, limit=5)

    # --- Regime ---
    regime_level = _extract_regime(narrative)
    regime_commentary = str(narrative.get("regime_commentary") or "").strip()

    # --- Confidence (plain, no raw numbers) ---
    confidence_level = _confidence_level(calibration, explanation)
    confidence_note = str(narrative.get("confidence_adjustment_note") or "").strip()

    # --- Trajectory (optional, multi-turn) ---
    trajectory = ""
    for key in ("longitudinal_story",):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            trajectory = val.strip()
            break

    return {
        "situation": str((scenario or {}).get("description") or "").strip(),
        "what_likely_happens": str(what).strip(),
        "outcome": str(outcome or "").strip(),
        "key_drivers": key_drivers,
        "hidden_risks": hidden_risks,
        "regime": {"level": regime_level, "commentary": regime_commentary},
        "confidence": {"level": confidence_level, "note": confidence_note},
        "trajectory": trajectory,
        # Kept for the advanced view only; the product UI does not emphasize it.
        "raw_risk_score": risk.get("score"),
        "turns": len(provenance),
    }
