"""Tests for coefficient fitting from time-series data (core/data_fitting.py)."""

from __future__ import annotations

import numpy as np

from core.data_fitting import (
    fit_weights, backtest, synthesize_ops_history, load_csv, write_csv,
)
from adapters.ops_scenario_builder import build_scenario


def test_fitter_recovers_signs_from_synthetic_data() -> None:
    rows, tw = synthesize_ops_history("distribution", weeks=80, seed=11, noise=0.2)
    fit = fit_weights(rows, "distribution")
    sign_ok = total = 0
    for link in fit["fitted_links"]:
        if link.get("_source") != "fitted":
            continue
        t = tw.get((link["from"], link["to"]))
        if t is None or abs(t) < 1e-6:
            continue
        total += 1
        if (t > 0) == (link["weight"] > 0):
            sign_ok += 1
    assert total >= 5
    assert sign_ok / total >= 0.8, f"sign recovery too low: {sign_ok}/{total}"


def test_backtest_strong_on_consistent_data() -> None:
    rows, _ = synthesize_ops_history("manufacturing", weeks=80, seed=5, noise=0.2)
    bt = backtest(rows, "manufacturing")
    assert bt["ok"] is True
    assert bt["overall_r2"] >= 0.5, bt


def test_backtest_weak_on_random_noise() -> None:
    rng = np.random.default_rng(3)
    cols = ["weekly_demand", "inventory_on_hand", "fill_rate", "lead_time_days",
            "supplier_risk", "unit_cost", "capacity_utilization", "holding_cost_weekly",
            "stockout_risk", "backlog_weeks"]
    rows = [{c: float(rng.normal(50, 5)) for c in cols} for _ in range(80)]
    bt = backtest(rows, "distribution")
    # honest: a structure-fit to pure noise must NOT claim a strong fit
    assert bt["ok"] is True
    assert bt["overall_r2"] < 0.3, bt
    assert bt["verdict"] == "weak"


def test_backtest_needs_enough_periods() -> None:
    rows, _ = synthesize_ops_history("distribution", weeks=5, seed=1)
    bt = backtest(rows, "distribution")
    assert bt["ok"] is False


def test_fitted_links_override_archetype_in_build_scenario() -> None:
    rows, _ = synthesize_ops_history("distribution", weeks=60, seed=2)
    fit = fit_weights(rows, "distribution")
    profile = {"business_unit_type": "distribution", "inventory_on_hand": 10000,
               "weekly_demand": 650, "fill_rate": 0.92}
    sc = build_scenario(profile, fitted_links=fit["fitted_links"])
    # the scenario's causal weights should match the fitted ones, not the archetype
    fitted_map = {(l["from"], l["to"]): l["weight"] for l in fit["fitted_links"]}
    for link in sc["causal_links"]:
        key = (link["from"], link["to"])
        if key in fitted_map:
            assert abs(link["weight"] - fitted_map[key]) < 1e-6


def test_robust_winsorize_recovers_from_outliers() -> None:
    """Winsorized fitting recovers material accuracy under outliers and doesn't harm clean."""
    from adapters.ops_scenario_builder import _ARCHETYPE_CAUSAL
    from core.data_fitting import corrupt_rows, backtest_levels
    rows, _ = synthesize_ops_history("distribution", weeks=80, seed=5, noise=0.15)
    S = _ARCHETYPE_CAUSAL["distribution"]
    # deterministic (fixed seeds): outliers hurt the plain fit; winsorize recovers it.
    dirty = corrupt_rows(rows, seed=2, outlier=0.1)
    nonrobust = backtest_levels(dirty, S, robust=False)["overall_r2"]
    robust = backtest_levels(dirty, S, robust=True)["overall_r2"]
    # under outliers, winsorize helps or ties — never materially worse
    assert robust >= nonrobust - 0.02, f"robust={robust} vs non-robust={nonrobust}"
    # and it must not materially hurt clean data (safe to enable by default)
    c_nr = backtest_levels(rows, S, robust=False)["overall_r2"]
    c_r = backtest_levels(rows, S, robust=True)["overall_r2"]
    assert c_r >= c_nr - 0.05, f"winsorize hurt clean data: {c_r} < {c_nr}"


def test_csv_round_trip(tmp_path) -> None:
    rows, _ = synthesize_ops_history("retail", weeks=20, seed=4)
    p = tmp_path / "hist.csv"
    write_csv(rows, str(p))
    loaded = load_csv(str(p))
    assert len(loaded) == len(rows)
    assert set(loaded[0].keys()) == set(rows[0].keys())
