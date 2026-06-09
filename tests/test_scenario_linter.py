"""
Tests for the Scenario Intelligence Layer (core/scenario_linter.py).

Implements docs/SCENARIO_GRAMMAR.md §7 (errors/warnings) and §7.5 (levels L1–L4).
"""

from __future__ import annotations

from core.scenario_linter import lint_scenario


# ---------- errors ----------

def test_clean_scenario_has_no_errors_and_is_runnable(l4_scenario) -> None:
    rep = lint_scenario(l4_scenario())
    assert rep["errors"] == []
    assert rep["runnable"] is True


def test_undeclared_causal_variable_is_error(l4_scenario) -> None:
    sc = l4_scenario()
    sc["causal_links"].append({"from": "price", "to": "ghost_var", "strength": 0.5})
    rep = lint_scenario(sc)
    assert any(e["code"] == "E_LINK_UNDECLARED" for e in rep["errors"])
    assert rep["runnable"] is False
    assert rep["level"] == 0


def test_no_objectives_is_error(l4_scenario) -> None:
    sc = l4_scenario()
    for a in sc["initial_agents"]:
        a["objectives"] = {}
    rep = lint_scenario(sc)
    assert any(e["code"] == "E_NO_OBJECTIVES" for e in rep["errors"])


def test_objective_over_derived_variable_is_warning_not_error(l4_scenario) -> None:
    # an objective over a non-initial_state var (e.g. a derived metric) must NOT block
    sc = l4_scenario()
    sc["initial_agents"][0]["objectives"] = {"service_level": 1.0}  # not in initial_state
    rep = lint_scenario(sc)
    assert not any(e["code"].startswith("E_") and "OBJECTIVE" in e["code"] for e in rep["errors"])
    assert any(w["code"] == "W_OBJECTIVE_UNMATCHED" for w in rep["warnings"])


def test_unregistered_rule_key_is_error(l4_scenario) -> None:
    sc = l4_scenario()
    sc["rules"][0]["condition_key"] = "no_such_condition"
    rep = lint_scenario(sc)
    assert any(e["code"] == "E_RULE_UNREGISTERED" for e in rep["errors"])


# ---------- warnings (smells) ----------

def test_missing_second_mover_warns(l4_scenario) -> None:
    sc = l4_scenario()
    sc["initial_agents"] = [{"name": "founder", "role": "Founder", "objectives": {"mrr": 1.0}}]
    rep = lint_scenario(sc)
    assert any(w["code"] == "W_NO_SECOND_MOVER" for w in rep["warnings"])


def test_no_feedback_loop_warns(l4_scenario) -> None:
    sc = l4_scenario()
    sc["causal_links"] = [l for l in sc["causal_links"] if not (l["from"] == "cash" and l["to"] == "price")]
    rep = lint_scenario(sc)
    assert any(w["code"] == "W_NO_FEEDBACK_LOOP" for w in rep["warnings"])


def test_missing_constraint_warns(l4_scenario) -> None:
    sc = l4_scenario()
    # drop cash (the only constraint variable) and its links/objectives
    sc["initial_state"].pop("cash")
    sc["variable_specs"].pop("cash")
    sc["causal_links"] = [l for l in sc["causal_links"] if "cash" not in (l["from"], l["to"])]
    sc["initial_agents"][0]["objectives"] = {"mrr": 1.0}
    rep = lint_scenario(sc)
    assert any(w["code"] == "W_NO_CONSTRAINT" for w in rep["warnings"])


def test_large_unspecified_variable_warns(l4_scenario) -> None:
    sc = l4_scenario()
    sc["variable_specs"].pop("mrr")  # mrr=50000 now unspecced
    rep = lint_scenario(sc)
    assert any(w["code"] == "W_SCALE_NO_SPEC" for w in rep["warnings"])


def test_no_rule_warns_missing_failure_mode(l4_scenario) -> None:
    sc = l4_scenario()
    sc["rules"] = []
    rep = lint_scenario(sc)
    assert any(w["code"] == "W_NO_FAILURE_MODE" for w in rep["warnings"])


# ---------- completeness levels ----------

def test_full_scenario_reaches_l4(l4_scenario) -> None:
    rep = lint_scenario(l4_scenario())
    assert rep["level"] == 4, rep["level_reasons"]
    assert rep["level_name"] == "Robustness-Ready"


def test_missing_failure_mode_caps_at_l2(l4_scenario) -> None:
    sc = l4_scenario()
    sc["rules"] = []  # removes the non-linear failure mode -> can't reach L3
    rep = lint_scenario(sc)
    assert rep["level"] == 2
    assert "L3" in rep["level_reasons"]


def test_no_loop_caps_at_l1(l4_scenario) -> None:
    sc = l4_scenario()
    sc["causal_links"] = [l for l in sc["causal_links"] if not (l["from"] == "cash" and l["to"] == "price")]
    rep = lint_scenario(sc)
    assert rep["level"] == 1
    assert "L2" in rep["level_reasons"]


def test_errors_force_level_zero(l4_scenario) -> None:
    sc = l4_scenario()
    sc["causal_links"].append({"from": "x", "to": "y", "strength": 0.5})
    rep = lint_scenario(sc)
    assert rep["level"] == 0
