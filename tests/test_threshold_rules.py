"""
Path B — generic non-linear threshold primitives for the rule engine.

Proves, deterministically and in isolation from agent dynamics, that a scenario can
declare a tipping point in pure JSON: when a variable crosses a threshold, a
catastrophic (non-linear) shock is applied — the cascade that linear propagation
cannot produce (see the Path A finding).
"""

from __future__ import annotations

from core.threshold_rules import (
    cond_var_above, cond_var_below, effect_scale_var, effect_add_to_var,
    register_threshold_primitives,
)
from core.rule_engine import run_rules


# ---- primitives in isolation ----

def test_cond_var_above() -> None:
    snap = {"variables": {"churn_rate": 0.5}}
    assert cond_var_above(snap, {"var": "churn_rate", "threshold": 0.45}) is True
    assert cond_var_above(snap, {"var": "churn_rate", "threshold": 0.55}) is False


def test_cond_var_below() -> None:
    snap = {"variables": {"runway": 3.0}}
    assert cond_var_below(snap, {"var": "runway", "threshold": 6.0}) is True
    assert cond_var_below(snap, {"var": "runway", "threshold": 2.0}) is False


def test_cond_missing_var_is_false() -> None:
    assert cond_var_above({"variables": {}}, {"var": "x", "threshold": 1.0}) is False


def test_effect_scale_var_returns_multiplicative_delta(make_world) -> None:
    w = make_world({"mrr": 100.0})
    delta = effect_scale_var(w, {"target": "mrr", "factor": 0.6})
    # additive delta of -40 so that apply (current + delta) == current*0.6
    assert delta["numeric_updates"]["mrr"] == -40.0


def test_effect_add_to_var(make_world) -> None:
    w = make_world({"mrr": 100.0})
    delta = effect_add_to_var(w, {"target": "mrr", "amount": -25.0})
    assert delta["numeric_updates"]["mrr"] == -25.0


# ---- end-to-end through run_rules + WorldModel ----

def test_rule_fires_and_applies_cascade_above_threshold(make_world) -> None:
    register_threshold_primitives()
    w = make_world({"churn_rate": 0.5, "mrr": 100.0})
    rules = [{
        "id": "churn_cliff", "condition_key": "var_above", "effect_key": "scale_var",
        "params": {"var": "churn_rate", "threshold": 0.45, "target": "mrr", "factor": 0.6},
    }]
    activated = run_rules(w.snapshot(), w, rules)
    assert len(activated) == 1 and activated[0]["id"] == "churn_cliff"
    # The rule returns the correct multiplicative delta (asserted exactly in
    # test_effect_scale_var); after the world's apply_delta physics (damping/clamp/
    # noise) mrr still drops substantially below its starting value.
    assert w.variables["mrr"] < 90.0, f"cascade did not drop mrr (got {w.variables['mrr']})"


def test_rule_does_not_fire_below_threshold(make_world) -> None:
    register_threshold_primitives()
    w = make_world({"churn_rate": 0.40, "mrr": 100.0})
    rules = [{
        "id": "churn_cliff", "condition_key": "var_above", "effect_key": "scale_var",
        "params": {"var": "churn_rate", "threshold": 0.45, "target": "mrr", "factor": 0.6},
    }]
    activated = run_rules(w.snapshot(), w, rules)
    assert activated == []
    assert abs(w.variables["mrr"] - 100.0) < 1e-6  # untouched
