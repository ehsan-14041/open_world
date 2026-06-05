"""
Decision Brief: display-only mapping from the rich dashboard payload + per-turn
narrative into a structured decision intelligence output.

This module contains NO engine logic. It reuses `build_dashboard_payload`
(ui.dashboard_payload) and the per-turn `narrative` object produced by
`core.narrative_engine.generate_turn_narrative` (stored on each provenance
entry under the "narrative" key). Every field degrades gracefully when a
source value is missing, so a dry-run / rule-based run still yields a brief.

Guiding principle: we present "structured exploration of options and their
chained consequences", not numeric prediction. No accuracy claims; raw scores
are kept only for the advanced view.

Output sections (new):
  decision        — echoes the structured input (move, actors, constraints, horizon)
  what_likely_happens — narrative summary
  outcome         — outcome label
  top_drivers     — [{name, direction, why_it_matters}] × 3
  second_order_effects — [{effect, trigger, hops, magnitude_label}] × 3
  hidden_assumptions — [{assumption, risk_if_wrong, evidence_strength}] × 5
  kill_criteria   — [{watch_variable, threshold, signal, why}] × 3
  regime, confidence, trajectory, raw_risk_score

Backward-compat aliases: key_drivers → top_drivers items, hidden_risks → hidden_assumptions items.
"""

from __future__ import annotations

from typing import Any

from ui.dashboard_payload import build_dashboard_payload
from core.narrative_engine import outcome_label_display, _humanize_var
from core.kill_criteria import derive_kill_criteria
from core.trace_compression import compress_trace_to_causal_chain

try:
    from core.world_summarizer import detect_language
except Exception:
    def detect_language(_text: str) -> str:
        return "en"


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
        return str(explanation.get("confidence_level") or "high").strip().lower() or "high"
    if health in ("yellow",):
        return "moderate"
    return str(explanation.get("confidence_level") or "moderate").strip().lower() or "moderate"


def _move_keywords(decision_input: dict[str, Any] | None) -> set[str]:
    """Extract searchable keywords from the decision move and actors."""
    if not decision_input:
        return set()
    kws: set[str] = set()
    move_text = (decision_input.get("move") or "").lower()
    kws.update(w for w in move_text.split() if len(w) > 3)
    for actor in decision_input.get("actors") or []:
        kws.update(w for w in str(actor).lower().split() if len(w) > 3)
    return kws


def _causal_proximity_scores(
    provenance: list[dict[str, Any]],
    decision_input: dict[str, Any] | None,
) -> dict[str, float]:
    """
    Score variables by causal proximity to the move.
    Uses propagation_trace hop distance and compress_trace_to_causal_chain output.
    """
    scores: dict[str, float] = {}
    move_kws = _move_keywords(decision_input)

    for pe in provenance:
        tr = pe.get("turn_record") or {}
        for step in tr.get("propagation_trace") or []:
            if not isinstance(step, dict):
                continue
            hop = step.get("hop", 1)
            if not isinstance(hop, int) or hop < 1:
                hop = 1
            weight = 1.0 / hop
            for key in ("from", "to"):
                v = step.get(key)
                if not v:
                    continue
                vstr = str(v)
                scores[vstr] = scores.get(vstr, 0.0) + weight
                if move_kws and any(kw in vstr.lower() for kw in move_kws):
                    scores[vstr] += 1.5

    try:
        chain = compress_trace_to_causal_chain(provenance, slm_callback=None, max_events=50)
        for evt in chain:
            if not isinstance(evt, dict):
                continue
            for key in ("cause_var", "effect_var"):
                v = evt.get(key)
                if v:
                    vstr = str(v)
                    scores[vstr] = scores.get(vstr, 0.0) + 0.5
    except Exception:
        pass

    return scores


def _build_top_drivers(
    narrative: dict[str, Any],
    explanation: dict[str, Any],
    provenance: list[dict[str, Any]],
    lang: str,
    decision_input: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Build top_drivers as [{name, direction, why_it_matters}].

    Sources (in priority order):
    1. narrative.key_drivers (already produced by the engine)
    2. explanation.top_drivers (dashboard payload)
    Rank by causal proximity to the move using propagation_trace hops
    and compress_trace_to_causal_chain output.
    """
    causal_scores = _causal_proximity_scores(provenance, decision_input)
    move_kws = _move_keywords(decision_input)

    if lang == "fa":
        raw_drivers = narrative.get("key_drivers") or explanation.get("top_drivers") or []
    else:
        raw_drivers = explanation.get("top_drivers") or narrative.get("key_drivers") or []
    if not isinstance(raw_drivers, list):
        raw_drivers = []

    seen: set[str] = set()
    drivers: list[dict[str, Any]] = []
    for d in raw_drivers:
        if isinstance(d, dict):
            name = str(d.get("name") or d.get("variable") or "").strip()
            direction = str(d.get("direction") or d.get("trend") or "").strip()
            why = str(d.get("why") or d.get("why_it_matters") or d.get("description") or "").strip()
        else:
            name = str(d).strip()
            direction = ""
            why = ""
        if not name or name in seen:
            continue
        seen.add(name)
        causal = causal_scores.get(name, 0.0)
        if move_kws and any(kw in name.lower() for kw in move_kws):
            causal += 2.0
        drivers.append({"name": name, "direction": direction, "why_it_matters": why, "_score": causal})
        if len(drivers) >= 6:
            break

    drivers.sort(key=lambda x: x.pop("_score", 0), reverse=True)
    return drivers[:3]


def _causal_chain_phrases(narrative: dict[str, Any]) -> dict[tuple[str, str], str]:
    """Map (trigger_var, effect_var) pairs to human phrases from narrative causal_chain."""
    phrases: dict[tuple[str, str], str] = {}
    for chain_entry in narrative.get("causal_chain") or []:
        if not isinstance(chain_entry, dict):
            continue
        chain = chain_entry.get("chain") or []
        if not isinstance(chain, list) or len(chain) < 2:
            continue
        for i in range(len(chain) - 1):
            trigger_item = chain[i]
            effect_item = chain[i + 1]
            if not isinstance(trigger_item, (list, tuple)) or not isinstance(effect_item, (list, tuple)):
                continue
            if len(trigger_item) < 1 or len(effect_item) < 1:
                continue
            trigger_var = str(trigger_item[0])
            effect_var = str(effect_item[0])
            trigger_h = _humanize_var(trigger_var)
            effect_h = _humanize_var(effect_var)
            phrases[(trigger_var, effect_var)] = f"{trigger_h} → {effect_h}"
    return phrases


def _build_second_order_effects(
    provenance: list[dict[str, Any]],
    narrative: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Build second_order_effects as [{effect, trigger, hops, magnitude_label}].

    Uses propagation_trace entries with hop >= 2 across all turns.
    Ranks by absolute delta_contrib, deduplicates by (from, to) pair.
    Cross-references narrative.causal_chain for human phrasing.
    """
    chain_phrases = _causal_chain_phrases(narrative)
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for pe in provenance:
        tr = pe.get("turn_record") or {}
        for step in tr.get("propagation_trace") or []:
            if not isinstance(step, dict):
                continue
            hop = step.get("hop", 1)
            if not isinstance(hop, int) or hop < 2:
                continue
            from_var = str(step.get("from") or "").strip()
            to_var = str(step.get("to") or "").strip()
            if not from_var or not to_var:
                continue
            contrib = step.get("delta_contrib")
            if not isinstance(contrib, (int, float)):
                continue
            key = (from_var, to_var)
            existing = candidates.get(key)
            if existing is None or abs(float(contrib)) > abs(float(existing["_mag"])):
                candidates[key] = {
                    "effect": to_var,
                    "trigger": from_var,
                    "hops": hop,
                    "_mag": float(contrib),
                }

    # Map magnitude to label
    def _mag_label(v: float) -> str:
        abs_v = abs(v)
        if abs_v >= 0.6:
            return "high"
        if abs_v >= 0.25:
            return "medium"
        return "low"

    sorted_effects = sorted(candidates.values(), key=lambda x: abs(x["_mag"]), reverse=True)
    results: list[dict[str, Any]] = []
    for e in sorted_effects[:3]:
        trigger = e["trigger"]
        effect = e["effect"]
        phrase = chain_phrases.get((trigger, effect))
        display_effect = phrase or f"{_humanize_var(trigger)} → {_humanize_var(effect)}"
        results.append({
            "effect": display_effect,
            "trigger": _humanize_var(trigger),
            "hops": e["hops"],
            "magnitude_label": _mag_label(e["_mag"]),
        })
    return results


def _build_hidden_assumptions(
    narrative: dict[str, Any],
    assumptions: list[Any],
) -> list[dict[str, Any]]:
    """
    Build hidden_assumptions as [{assumption, risk_if_wrong, evidence_strength}].

    Sources: payload.assumption_summary + narrative.hidden_costs.
    """
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    # From structured assumption_summary
    for a in assumptions:
        if not isinstance(a, dict):
            continue
        text = str(a.get("assumption") or a.get("text") or a.get("statement") or "").strip()
        risk = str(a.get("risk_if_wrong") or a.get("risk") or "").strip()
        strength = str(a.get("evidence_strength") or a.get("confidence") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append({"assumption": text, "risk_if_wrong": risk, "evidence_strength": strength})
        if len(items) >= 5:
            break

    # From narrative hidden costs (fill remaining slots)
    for hc in narrative.get("hidden_costs") or []:
        if len(items) >= 5:
            break
        if isinstance(hc, str):
            text = hc.strip()
            risk = ""
        elif isinstance(hc, dict):
            text = str(hc.get("description") or hc.get("text") or hc.get("cost") or "").strip()
            risk = str(hc.get("risk_if_wrong") or "").strip()
        else:
            continue
        if not text or text in seen:
            continue
        seen.add(text)
        items.append({"assumption": text, "risk_if_wrong": risk, "evidence_strength": ""})

    return items


def build_decision_brief(
    final_snapshot: dict[str, Any],
    provenance: list[dict[str, Any]] | None,
    scenario: dict[str, Any],
    agents_list: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build a Decision Brief from a completed run.

    Args:
        final_snapshot: the final world snapshot (loop result["final"]).
        provenance: the full list of per-turn provenance entries.
        scenario: the (normalized) scenario dict.  May contain 'decision_input'.
        agents_list: optional list of agent dicts (name/role/objectives).

    Returns a dict with sections:
        decision, what_likely_happens, outcome,
        top_drivers, second_order_effects, hidden_assumptions, kill_criteria,
        regime, confidence, trajectory, raw_risk_score, turns.

    Backward-compat aliases: key_drivers, hidden_risks.
    """
    provenance = provenance or []
    agents_list = agents_list or []
    last_pe = provenance[-1] if provenance else {}
    lang = "fa" if detect_language(str((scenario or {}).get("description") or "")) == "fa" else "en"

    decision_input: dict[str, Any] = {}
    if isinstance((scenario or {}).get("decision_input"), dict):
        decision_input = scenario["decision_input"]

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

    # What likely happens
    what = (
        explanation.get("narrative_summary")
        or narrative.get("turn_summary")
        or ""
    )

    # Outcome label
    outcome_raw = (narrative.get("outcome_assessment") or {}).get("outcome") if isinstance(narrative.get("outcome_assessment"), dict) else ""
    outcome = outcome_label_display(outcome_raw, lang) if outcome_raw else ""

    # Top drivers (structured)
    top_drivers = _build_top_drivers(narrative, explanation, provenance, lang, decision_input or None)

    # Second-order effects
    second_order_effects = _build_second_order_effects(provenance, narrative)

    # Hidden assumptions
    hidden_assumptions = _build_hidden_assumptions(narrative, assumptions)

    # Kill criteria
    try:
        kill_criteria = derive_kill_criteria(
            final_snapshot or {},
            provenance,
            scenario or {},
            decision_input=decision_input or None,
        )
    except Exception:
        kill_criteria = []

    # Regime
    regime_level = _extract_regime(narrative)
    regime_commentary = str(narrative.get("regime_commentary") or "").strip()

    # Confidence
    confidence_level = _confidence_level(calibration, explanation)
    confidence_note = str(narrative.get("confidence_adjustment_note") or "").strip()

    # Trajectory (multi-turn longitudinal)
    trajectory = ""
    for key in ("longitudinal_story",):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            trajectory = val.strip()
            break

    # Backward-compat aliases
    key_drivers_compat = _dedup_keep_order([d.get("name", "") for d in top_drivers], limit=3)
    hidden_risks_compat = _dedup_keep_order(
        [a.get("assumption", "") or a.get("risk_if_wrong", "") for a in hidden_assumptions],
        limit=5,
    )

    return {
        # Structured decision context (empty dict when legacy free-text path)
        "decision": {
            "move": decision_input.get("move") or "",
            "actors": decision_input.get("actors") or [],
            "constraints": decision_input.get("constraints") or {},
            "horizon_months": decision_input.get("horizon_months"),
        },
        "situation": str((scenario or {}).get("description") or "").strip(),
        "what_likely_happens": str(what).strip(),
        "outcome": str(outcome or "").strip(),
        # Four core decision intelligence sections
        "top_drivers": top_drivers,
        "second_order_effects": second_order_effects,
        "hidden_assumptions": hidden_assumptions,
        "kill_criteria": kill_criteria,
        # Context panels
        "regime": {"level": regime_level, "commentary": regime_commentary},
        "confidence": {"level": confidence_level, "note": confidence_note},
        "trajectory": trajectory,
        # Advanced view only
        "raw_risk_score": risk.get("score"),
        "turns": len(provenance),
        # Backward-compat aliases
        "key_drivers": key_drivers_compat,
        "hidden_risks": hidden_risks_compat,
    }
