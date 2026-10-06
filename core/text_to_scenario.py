"""
Text -> Scenario converter, driven by a per-domain Knowledge Base (no LLM).

Design (per the product owner): domains are **data, not code**. The knowledge base
(`config/domain_kb.json`) defines each domain declaratively — keywords, variables,
a causal feedback loop, reacting actors, a constraint, and a non-linear failure rule.
This converter matches the user's free text to a KB domain and assembles a real,
well-formed scenario (L3/L4). Adding a domain = adding a JSON object; no code change.

Contract: if the text matches a defined domain -> return a scenario. If not -> return
None with reason "domain not in knowledge base" (honest "I can't", per spec). Arbitrary
free text outside every defined domain genuinely needs an LLM.
"""

from __future__ import annotations

import copy
import json
import pathlib
import re
from typing import Any

_KB_PATH = pathlib.Path(__file__).resolve().parent.parent / "config" / "domain_kb.json"

_UP = ("raise", "increase", "up", "grow", "expand", "add", "double", "hike", "boost", "scale up")
_DOWN = ("cut", "lower", "decrease", "reduce", "drop", "slash", "shrink", "halve", "scale down", "lay off")


def load_kb() -> list[dict[str, Any]]:
    """Load the domain knowledge base (list of domain definitions)."""
    try:
        data = json.loads(_KB_PATH.read_text(encoding="utf-8"))
        return [d for d in (data.get("domains") or []) if isinstance(d, dict) and d.get("name")]
    except Exception:
        return []


def list_domains() -> list[dict[str, str]]:
    """Return (name, label) for each defined domain — for UI / 'I can't' messaging."""
    return [{"name": d["name"], "label": d.get("label", d["name"])} for d in load_kb()]


def _extract_magnitude(text: str) -> float:
    t = text.lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
    if m:
        return max(0.01, min(3.0, float(m.group(1)) / 100.0))
    if "double" in t or re.search(r"\b2\s*x\b", t):
        return 1.0
    if "triple" in t or re.search(r"\b3\s*x\b", t):
        return 2.0
    if "halve" in t or "half" in t:
        return 0.5
    return 0.25


def _direction(text: str) -> int:
    t = text.lower()
    if any(w in t for w in _DOWN):
        return -1
    if any(w in t for w in _UP):
        return 1
    return 1


def detect_domain(text: str, kb: list[dict[str, Any]] | None = None) -> str | None:
    """Best-matching domain name by keyword score, or None if nothing matches."""
    t = (text or "").lower()
    kb = kb if kb is not None else load_kb()
    best, best_score = None, 0
    for d in kb:
        score = sum(1 for kw in (d.get("keywords") or []) if kw in t)
        if score > best_score:
            best, best_score = d["name"], score
    return best


def _clamp(v: float, lo: Any, hi: Any) -> float:
    if isinstance(lo, (int, float)):
        v = max(float(lo), v)
    if isinstance(hi, (int, float)):
        v = min(float(hi), v)
    return v


def _apply_parameterize(scenario: dict[str, Any], rules_spec: list[dict[str, Any]], mag: float) -> None:
    """Map the move magnitude onto causal link strengths / rule thresholds (in place)."""
    for p in rules_spec or []:
        try:
            value = float(p.get("base", 0.0)) + float(p.get("per_mag", 0.0)) * mag
            value = _clamp(value, p.get("min"), p.get("max"))
            value = round(value, 3)
        except Exception:
            continue
        if p.get("target") == "link":
            for link in scenario.get("causal_links") or []:
                if link.get("from") == p.get("from") and link.get("to") == p.get("to"):
                    link[p.get("field", "strength")] = value
        elif p.get("target") == "rule":
            for rule in scenario.get("rules") or []:
                if rule.get("id") == p.get("id"):
                    rule.setdefault("params", {})[p.get("param", "threshold")] = value


def _build_from_domain(domain: dict[str, Any], text: str, mag: float, sign: int) -> dict[str, Any]:
    """Assemble a scenario dict from a KB domain definition."""
    variables = domain.get("variables") or {}
    initial_state: dict[str, float] = {}
    variable_specs: dict[str, dict[str, Any]] = {}
    for var, spec in variables.items():
        if not isinstance(spec, dict):
            continue
        if isinstance(spec.get("initial"), (int, float)):
            initial_state[var] = float(spec["initial"])
        vs = {k: spec[k] for k in ("min", "max", "behavior_type", "inertia", "decay", "rate_limit") if k in spec}
        if vs:
            variable_specs[var] = vs

    scenario: dict[str, Any] = {
        "description": f"{domain.get('label', domain['name'])} decision: {text.strip()}",
        "decision_input": {
            "move": text.strip(),
            "actors": list(domain.get("actors_hint") or []),
            "horizon_months": int(domain.get("horizon_months", 6)),
        },
        "initial_state": initial_state,
        "variable_specs": variable_specs,
        "initial_agents": copy.deepcopy(domain.get("actors") or []),
        "causal_links": copy.deepcopy(domain.get("causal_links") or []),
        "allowed_actions": list(domain.get("allowed_actions") or []),
        "rules": copy.deepcopy(domain.get("rules") or []),
    }
    _apply_parameterize(scenario, domain.get("parameterize") or [], mag)
    return scenario


def text_to_scenario(text: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """
    Convert free text to a scenario using the domain KB (no LLM).

    Returns (scenario, meta). scenario is None when no domain matches; meta carries
    {matched, domain, magnitude, direction, reason, available_domains}.
    """
    text = (text or "").strip()
    kb = load_kb()
    available = [d["name"] for d in kb]
    meta: dict[str, Any] = {"matched": False, "domain": None, "magnitude": None,
                            "direction": None, "reason": None, "available_domains": available}
    if not text:
        meta["reason"] = "empty text"
        return None, meta

    name = detect_domain(text, kb)
    if name is None:
        meta["reason"] = "domain not in knowledge base"
        return None, meta

    domain = next(d for d in kb if d["name"] == name)
    mag = _extract_magnitude(text)
    sign = _direction(text)
    scenario = _build_from_domain(domain, text, mag, sign)
    meta.update({"matched": True, "domain": name, "magnitude": mag, "direction": sign})
    return scenario, meta
