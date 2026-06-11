# Fitting findings — what real data taught us (de-risk log)

Honest record of the "fit coefficients from data" de-risk, so the lesson survives.

## TL;DR
- **Synthetic validation was misleading.** The fitter scored backtest R²=1.0 on synthetic
  data — but the synthetic data was generated *in the same standardized-delta space the
  fitter assumes*. That is circular: "works on synthetic" proved almost nothing.
- **On real data (UCI Daily Demand Forecasting Orders, 60 days), the original method
  failed.** Even a near-additive trivial relationship backtested at only R²=0.10; a
  non-trivial structure overfit (in-sample 0.84 → backtest **−0.42**).
- **A better method (ridge regression in levels) roughly doubled it:** trivial 0.53,
  non-trivial 0.32–0.38 (moderate). So the *method* was the main weakness, not the idea —
  and the fix direction is clear.
- **But UCI only tested the pipeline, not the product thesis.** It is order-flow data with
  no inventory / lead-time / fill-rate / stockout structure, so no method could validate
  "raise safety stock 15% → fill-rate fragility to lead-time shocks."

## Numbers (real UCI data, one-step-ahead holdout)
| structure | std-delta (engine-facing) | ridge-levels |
|---|---|---|
| trivial (Non-urgent+Urgent → Target) | 0.10 (weak) | 0.53 (moderate) |
| non-trivial (sector/banking → Target) | −0.42 (overfit) | 0.32–0.38 (moderate) |

## Root causes of the std-delta weakness
1. **`[-1, 1]` weight clamp** (needed for the engine's coupling semantics) breaks
   reconstruction when a true coefficient exceeds 1 — it caps the signal.
2. **Standardized-delta round-trip** is lossy with correlated/multicollinear parents.
3. **No regularization** → overfit on short series (the −0.42).
4. **Same-period linear assumption** `ΔY = Σ wᵢ ΔXᵢ`. Real ops dynamics have **lags,
   seasonality, regime changes, non-linearity** (e.g. `lead_time(t) → inventory(t+2) →
   fill_rate(t+3)`), which a contemporaneous linear fit cannot capture. This is likely why
   ridge-in-levels did better.

## The distinction that must not be blurred
- ✅ **Pipeline tested:** ingestion → fit → backtest runs on real, messy data.
- ❌ **Product thesis NOT tested:** needs a dataset with `inventory, demand, replenishment,
  lead_time, stockout, service_level` over time. Forecasting datasets (date/sales/price/
  promo) do **not** qualify.

## Open question that gates everything
Does a public dataset that carries the ops causal structure (inventory + service level +
lead time) even exist? If not, the fitter's value *is* the customer's own data, and the
right MVP is **consultant-assisted onboarding** (customer sends ERP export → we map → fit →
robustness), not a self-serve generic fitter.

## Reproduce
```
curl -L -o data/external/uci_daily_demand.csv \
  https://archive.ics.uci.edu/ml/machine-learning-databases/00409/Daily_Demand_Forecasting_Orders.csv
python - <<'PY'
from core.data_fitting import load_csv, backtest, backtest_levels
rows = load_csv("data/external/uci_daily_demand.csv")
T = "Target (Total orders)"
s = [{"from":"Non-urgent order","to":T},{"from":"Urgent order","to":T}]
print("std-delta:", backtest(rows, structure=s)["overall_r2"])
print("ridge-levels:", backtest_levels(rows, s)["overall_r2"])
PY
```

## Code state
- `core/data_fitting.py`: `fit_weights`/`backtest` now accept an arbitrary `structure`
  (not just the vertical archetype); `backtest_levels` added (ridge regression in levels)
  as the honest predictive yardstick, decoupled from the engine's clamped weights.
- Not yet done (deliberately deferred until an ops-shaped dataset is confirmed to exist):
  rewriting the engine-facing fitter to use lagged / regularized dynamics.
