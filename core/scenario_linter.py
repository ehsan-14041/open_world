"""
Scenario Intelligence Layer — the linter.

Static, simulation-free validation of a scenario, implementing
docs/SCENARIO_GRAMMAR.md §7 (errors + warnings) and §7.5 (completeness levels L1–L4).

It answers three questions without running the engine:
  1. Will it run?            -> errors (block execution)
  2. Is it likely garbage?   -> warnings (the "scenario smells")
  3. How complete is it?     -> level L1..L4 + why it isn't higher

Pure function over the scenario dict + the variable graph. No state mutation.
"""

from __future__ import annotations

from typing import Any

import core.threshold_rules  # noqa: F401 — ensure threshold primitives are registered
import core.market_dynamics  # noqa: F401 — ensure market shock primitives are registered
from core.rule_engine import has_condition, has_effect
from core.legacy_semantics import legacy_goal_to_var_direction

# Heuristic keyword sets for the semantic smells.
_SECOND_MOVER_KW = ("competitor", "rival", "regulator", "supplier", "adversary", "opponent")
_LIQUIDITY_KW = ("cash", "runway", "capital", "liquidity")
_CONSTRAINT_KW = _LIQUIDITY_KW + ("capacity", "inventory", "budget", "reserve", "headroom")


# ---------- helpers ----------

def _state_vars(scenario: dict[str, Any]) -> set[str]:
    st = scenario.get("initial_state")
    return set(st.keys()) if isinstance(st, dict) else set()


def _objective_var(key: str) -> str | None:
    mapped = legacy_goal_to_var_direction(key)
    return mapped[0] if mapped else None


def _has_cycle(edges: list[tuple[str, str]]) -> bool:
    """Directed-cycle detection (DFS with recursion stack) over (from, to) edges."""
    adj: dict[str, list[str]] = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def visit(n: str) -> bool:
        color[n] = GREY
        for m in adj.get(n, []):
            c = color.get(m, WHITE)
            if c == GREY:
                return True
            if c == WHITE and visit(m):
                return True
        color[n] = BLACK
        return False

    return any(color.get(n, WHITE) == WHITE and visit(n) for n in list(adj.keys()))


def _causal_edges(scenario: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for link in scenario.get("causal_links") or []:
        if isinstance(link, dict) and link.get("from") and link.get("to"):
            out.append((str(link["from"]), str(link["to"])))
    return out


def _lever_moves_a_variable(scenario: dict[str, Any], state_vars: set[str]) -> bool:
    if isinstance(scenario.get("decision_input"), dict) and scenario["decision_input"].get("move"):
        return True
    tradeoffs = scenario.get("action_tradeoffs")
    if isinstance(tradeoffs, dict):
        for eff in tradeoffs.values():
            if isinstance(eff, dict) and any(v in state_vars for v in eff):
                return True
    for action in scenario.get("allowed_actions") or []:
        a = str(action)
        for pref in ("increase_", "decrease_"):
            if a.startswith(pref) and a[len(pref):] in state_vars:
                return True
    return False


# ---------- core checks ----------

def _errors(scenario: dict[str, Any], state_vars: set[str]) -> list[dict[str, str]]:
    errs: list[dict[str, str]] = []

    # E1: causal link references an undeclared variable
    for a, b in _causal_edges(scenario):
        for v in (a, b):
            if v not in state_vars:
                errs.append({"code": "E_LINK_UNDECLARED",
                             "message": f"causal_links references undeclared variable '{v}'",
                             "element": f"{a}->{b}"})

    # Objectives: only a TOTAL absence of objectives is fatal (goal_score would be 0).
    # An objective over a variable not in initial_state may be a *derived* metric
    # (e.g. service_level, margin) that the engine still tracks, so it is a warning
    # (W_OBJECTIVE_UNMATCHED), not a blocking error.
    agents = scenario.get("initial_agents") or []
    any_objective = any(isinstance(ag, dict) and (ag.get("objectives") or {}) for ag in agents)
    if not any_objective:
        errs.append({"code": "E_NO_OBJECTIVES",
                     "message": "no actor declares any objective; goal_score would be 0",
                     "element": "initial_agents"})

    # E4: unregistered rule keys
    for rule in scenario.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        ck, ek = rule.get("condition_key"), rule.get("effect_key")
        if ck and not has_condition(str(ck)):
            errs.append({"code": "E_RULE_UNREGISTERED",
                         "message": f"rule '{rule.get('id','?')}' uses unregistered condition_key '{ck}' (silently skipped)",
                         "element": str(rule.get("id", "?"))})
        if ek and not has_effect(str(ek)):
            errs.append({"code": "E_RULE_UNREGISTERED",
                         "message": f"rule '{rule.get('id','?')}' uses unregistered effect_key '{ek}' (silently skipped)",
                         "element": str(rule.get("id", "?"))})

    # E5: the decision moves no declared variable
    if state_vars and not _lever_moves_a_variable(scenario, state_vars):
        errs.append({"code": "E_NO_LEVER",
                     "message": "the decision moves no declared variable (no decision_input, action_tradeoffs, or increase_/decrease_ action)",
                     "element": "allowed_actions"})

    return errs


def _warnings(scenario: dict[str, Any], state_vars: set[str]) -> list[dict[str, str]]:
    warns: list[dict[str, str]] = []
    agents = scenario.get("initial_agents") or []
    edges = _causal_edges(scenario)
    specs = scenario.get("variable_specs") if isinstance(scenario.get("variable_specs"), dict) else {}

    # W1: no second mover / reacting actor
    actor_text = " ".join(f"{a.get('name','')} {a.get('role','')}".lower() for a in agents if isinstance(a, dict))
    if not any(kw in actor_text for kw in _SECOND_MOVER_KW):
        warns.append({"code": "W_NO_SECOND_MOVER",
                      "message": "no competitor/regulator/supplier actor — the world has no second mover that reacts",
                      "hint": "Single-Cause Thinking: every option looks robust when nothing pushes back."})

    # W2: no feedback loop
    if edges and not _has_cycle(edges):
        warns.append({"code": "W_NO_FEEDBACK_LOOP",
                      "message": "the causal graph is a pure DAG (no feedback loop)",
                      "hint": "Real systems have loops (e.g. churn→revenue→runway→hiring→…)."})

    # W3: missing liquidity / constraint
    if not any(any(kw in v.lower() for kw in _CONSTRAINT_KW) for v in state_vars):
        warns.append({"code": "W_NO_CONSTRAINT",
                      "message": "no constraint variable (cash/runway/capacity/inventory) — nothing can run out",
                      "hint": "Infinite Growth: without a binding constraint, decisions look free."})

    # W4: large-magnitude variable without explicit spec
    st = scenario.get("initial_state") or {}
    for v, val in st.items():
        if isinstance(val, (int, float)) and not isinstance(val, bool) and abs(val) > 100 and v not in specs:
            warns.append({"code": "W_SCALE_NO_SPEC",
                          "message": f"large-magnitude variable '{v}'={val} has no variable_specs entry",
                          "hint": "Declare its scale & behavior_type; don't rely on scale-aware defaults."})

    # W4b: objective over a variable not in initial_state (may be derived; otherwise inert)
    seen_unmatched: set[str] = set()
    for ag in agents:
        if not isinstance(ag, dict):
            continue
        for key in (ag.get("objectives") or {}):
            var = _objective_var(str(key))
            if var and var not in state_vars and var not in seen_unmatched:
                seen_unmatched.add(var)
                warns.append({"code": "W_OBJECTIVE_UNMATCHED",
                              "message": f"objective '{key}' targets '{var}', not in initial_state",
                              "hint": "If it isn't a derived metric, it won't contribute to goal_score."})

    # W5: missing failure mode (no non-linear rule)
    if not (scenario.get("rules")):
        warns.append({"code": "W_NO_FAILURE_MODE",
                      "message": "no non-linear rule — a purely linear world drifts but cannot break",
                      "hint": "Add a threshold rule (var_above→scale_var); robustness can't tell fragile from robust without one."})

    # W6: inert shock — rule effect target not a declared variable / no downstream
    to_vars = {b for _, b in edges}
    from_vars = {a for a, _ in edges}
    for rule in scenario.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        params = rule.get("params") or {}
        target = params.get("target") or params.get("var")
        if target and target not in state_vars:
            warns.append({"code": "W_SHOCK_INERT",
                          "message": f"rule '{rule.get('id','?')}' targets '{target}', which is not a declared variable",
                          "hint": "The shock will have no effect."})

    # W7: dangling causal link (to-var with no downstream and not an objective)
    obj_vars = {_objective_var(str(k)) for a in agents if isinstance(a, dict) for k in (a.get("objectives") or {})}
    for v in to_vars:
        if v not in from_vars and v not in obj_vars:
            warns.append({"code": "W_DANGLING_LINK",
                          "message": f"variable '{v}' is affected but has no downstream effect and no actor cares about it",
                          "hint": "Either give it a downstream link or an objective, or drop the link."})

    return warns


def _completeness_level(
    scenario: dict[str, Any],
    state_vars: set[str],
    errors: list[dict[str, str]],
) -> tuple[int, dict[str, str]]:
    """Return (level 0..4, reasons-why-not-higher)."""
    reasons: dict[str, str] = {}
    if errors:
        return 0, {"L1": "has blocking errors — does not run"}

    edges = _causal_edges(scenario)
    specs = scenario.get("variable_specs") if isinstance(scenario.get("variable_specs"), dict) else {}
    agents = [a for a in (scenario.get("initial_agents") or []) if isinstance(a, dict)]
    st = scenario.get("initial_state") or {}

    # L2
    has_loop = bool(edges) and _has_cycle(edges)
    no_unspecced_large = not any(
        isinstance(val, (int, float)) and not isinstance(val, bool) and abs(val) > 100 and v not in specs
        for v, val in st.items()
    )
    enough_actors = len(agents) >= 2
    l2 = has_loop and no_unspecced_large and enough_actors
    if not l2:
        if not has_loop:
            reasons["L2"] = "no feedback loop in the causal graph"
        elif not no_unspecced_large:
            reasons["L2"] = "a large-magnitude variable lacks an explicit spec"
        else:
            reasons["L2"] = "fewer than 2 actors (only the decider is modeled)"
        return 1, reasons

    # L3
    actor_text = " ".join(f"{a.get('name','')} {a.get('role','')}".lower() for a in agents)
    has_second_mover = any(kw in actor_text for kw in _SECOND_MOVER_KW)
    has_constraint = any(any(kw in v.lower() for kw in _CONSTRAINT_KW) for v in state_vars)
    has_rule = bool(scenario.get("rules"))
    l3 = has_second_mover and has_constraint and has_rule
    if not l3:
        missing = []
        if not has_second_mover:
            missing.append("a reacting second mover (competitor/regulator/supplier)")
        if not has_constraint:
            missing.append("a constraint variable that can run out")
        if not has_rule:
            missing.append("a non-linear failure-mode rule")
        reasons["L3"] = "missing " + "; ".join(missing)
        return 2, reasons

    # L4
    rules = scenario.get("rules") or []
    thresholds_explicit = all(
        isinstance((r.get("params") or {}).get("threshold"), (int, float))
        for r in rules if isinstance(r, dict)
    )
    links_sweepable = all(
        isinstance(l.get("strength"), (int, float)) or isinstance(l.get("weight"), (int, float))
        for l in (scenario.get("causal_links") or []) if isinstance(l, dict)
    )
    l4 = thresholds_explicit and links_sweepable
    if not l4:
        if not thresholds_explicit:
            reasons["L4"] = "a rule has no explicit numeric threshold"
        else:
            reasons["L4"] = "a causal link has no sweepable strength/weight"
        return 3, reasons

    return 4, reasons


_LEVEL_NAMES = {
    0: "Invalid", 1: "Structurally Valid", 2: "Causally Coherent",
    3: "Strategically Complete", 4: "Robustness-Ready",
}


def lint_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """
    Lint a (normalized) scenario. Returns:
      {errors, warnings, level, level_name, level_reasons, runnable}
    """
    scenario = scenario or {}
    state_vars = _state_vars(scenario)
    errors = _errors(scenario, state_vars)
    warnings = _warnings(scenario, state_vars)
    level, reasons = _completeness_level(scenario, state_vars, errors)
    return {
        "errors": errors,
        "warnings": warnings,
        "level": level,
        "level_name": _LEVEL_NAMES.get(level, "Unknown"),
        "level_reasons": reasons,
        "runnable": not errors,
    }
