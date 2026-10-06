#!/usr/bin/env python3
"""
Chaos test — the real question: does fitted signal survive DIRTY data?

Takes a clean ops-shaped CSV and progressively corrupts it (noise, missing, outliers,
lag, seasonality, regime shift), re-fitting/backtesting at each level. Graceful decay
(0.99 -> ~0.7) = robust enough for messy real ERP exports. Collapse (-> ~0.1) = fragile.

This is more informative than tuning the engine to pass a demo: it estimates how much
value survives the transition from clean synthetic to real-world mess.

    python scripts/chaos_test.py [path.csv]   # default: data/external/user_ops_sample.csv
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.data_fitting import load_csv, backtest, backtest_levels, corrupt_rows  # noqa: E402
from adapters.ops_scenario_builder import _ARCHETYPE_CAUSAL  # noqa: E402

STRUCT = _ARCHETYPE_CAUSAL["distribution"]
DRIVERS = ["weekly_demand", "supplier_risk", "safety_stock"]


def _map(rows):
    ren = {"demand": "weekly_demand", "stockout_units": "stockout_risk"}
    return [{ren.get(k, k): v for k, v in r.items()} for r in rows]


def _score(rows):
    sd = backtest(rows, structure=STRUCT)
    rl = backtest_levels(rows, STRUCT, alpha=1.0)
    return sd.get("overall_r2"), rl.get("overall_r2")


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "data/external/user_ops_sample.csv"
    clean = _map(load_csv(path))
    print(f"clean baseline ({len(clean)} periods):")
    sd, rl = _score(clean)
    print(f"   std-delta R²={sd}   ridge-levels R²={rl}\n")

    print("single-axis degradation (ridge-levels R²):")
    axes = [
        ("noise 10%", dict(noise=0.10)),
        ("noise 25%", dict(noise=0.25)),
        ("missing 15%", dict(missing=0.15)),
        ("outliers 8%", dict(outlier=0.08)),
        ("lag 1wk (drivers)", dict(lag=1, lag_cols=DRIVERS)),
        ("seasonality", dict(seasonality=0.6, seasonality_col="weekly_demand")),
        ("regime shift", dict(regime_shift=0.4, regime_col="supplier_risk")),
    ]
    for name, kw in axes:
        _, rl2 = _score(corrupt_rows(clean, seed=1, **kw))
        print(f"   {name:22s} R²={rl2}")

    print("\nFULL CHAOS (everything at once, 3 seeds):")
    for seed in (1, 2, 3):
        dirty = corrupt_rows(clean, seed=seed, noise=0.10, missing=0.10, outlier=0.05,
                             lag=1, lag_cols=DRIVERS, seasonality=0.4,
                             seasonality_col="weekly_demand", regime_shift=0.3, regime_col="supplier_risk")
        sd2, rl2 = _score(dirty)
        print(f"   seed {seed}:  std-delta R²={sd2}   ridge-levels R²={rl2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
