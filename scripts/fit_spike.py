#!/usr/bin/env python3
"""
Coefficient-fitting spike — the de-risking artifact for the "ops + real data" pivot.

Two modes:
  python scripts/fit_spike.py                       # synthetic self-test (no data needed)
  python scripts/fit_spike.py <data.csv> <vertical> # fit + backtest a real CSV

The CSV must have one row per period (e.g. weekly) and columns named like the ops
variables (weekly_demand, inventory_on_hand, fill_rate, lead_time_days, unit_cost,
supplier_risk, capacity_utilization, holding_cost_weekly, ...). vertical is one of:
distribution, manufacturing, retail, multi_echelon, contract_manufacturing, general_ops.

Verdict to look for on REAL data: backtest overall_r2 >= ~0.5 -> the model reproduces
their history -> the product is real. Below ~0.3 -> fitting can't model their data from
this graph -> no UI will save it; rethink the structure or the vertical.
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.data_fitting import (  # noqa: E402
    load_csv, fit_weights, backtest, synthesize_ops_history,
)


def _report(rows, vertical, true_weights=None):
    print(f"  periods: {len(rows)}  | vertical: {vertical}")
    fit = fit_weights(rows, vertical)
    print(f"  fit mean R² (in-sample): {fit['mean_r2']}  | targets: {fit['per_target_r2']}")
    if fit["warnings"]:
        print("  warnings:", "; ".join(fit["warnings"][:4]))

    # recovery check (only meaningful with known ground truth)
    if true_weights:
        sign_ok = total = 0
        for link in fit["fitted_links"]:
            if link.get("_source") != "fitted":
                continue
            tw = true_weights.get((link["from"], link["to"]))
            if tw is None or abs(tw) < 1e-6:
                continue
            total += 1
            if (tw > 0) == (link["weight"] > 0):
                sign_ok += 1
        print(f"  sign recovery: {sign_ok}/{total} edges correct")

    bt = backtest(rows, vertical)
    if bt.get("ok"):
        print(f"  BACKTEST overall R²: {bt['overall_r2']}  ({bt['verdict']})"
              f"  | train {bt['train_periods']} / holdout {bt['holdout_periods']}")
        for y, m in bt["per_target"].items():
            print(f"     {y}: R²={m['r2']}  MAPE={m['mape_pct']}%")
    else:
        print("  BACKTEST:", bt.get("reason"))
    return fit, bt


def main() -> int:
    if len(sys.argv) >= 2:
        path = sys.argv[1]
        vertical = sys.argv[2] if len(sys.argv) >= 3 else "distribution"
        print(f"=== Fitting real CSV: {path} ===")
        rows = load_csv(path)
        if not rows:
            print("No numeric rows parsed from CSV.")
            return 1
        _report(rows, vertical)
        return 0

    print("=== SYNTHETIC SELF-TEST (no data) — proves the fitter recovers known weights ===")
    for vertical in ("distribution", "manufacturing", "retail"):
        print(f"\n[{vertical}]")
        rows, tw = synthesize_ops_history(vertical, weeks=80, seed=11, noise=0.2)
        _report(rows, vertical, true_weights=tw)

    print("\n=== Honesty check: fit RANDOM noise (should backtest WEAK) ===")
    import numpy as np
    rng = np.random.default_rng(3)
    cols = ["weekly_demand", "inventory_on_hand", "fill_rate", "lead_time_days",
            "supplier_risk", "unit_cost", "capacity_utilization", "holding_cost_weekly", "stockout_risk", "backlog_weeks"]
    noise_rows = [{c: float(rng.normal(50, 5)) for c in cols} for _ in range(80)]
    _report(noise_rows, "distribution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
