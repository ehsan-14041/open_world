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

## RESOLVED — public ops-shaped datasets are insufficient for full thesis validation

We tested the fitting/backtest pipeline on: a synthetic dataset, the UCI Daily Demand
Forecasting Orders dataset, and public dataset candidates that partially cover supply-chain
signals.

Findings:
1. **Synthetic validation is not sufficient** — a method that performs well on synthetic
   data may still fail on real data.
2. The earlier **delta-standardized fitting overfit / underperformed** on real data.
3. **Ridge-on-levels is materially better** than the previous approach, but still does not
   validate the full product thesis.
4. **No public dataset jointly contains the full causal structure** the thesis needs —
   inventory + demand + lead time + fill rate + replenishment dynamics over time. The two
   closest each cover only a fragment:
   - *FreshRetailNet-50K* (arXiv 2505.16319, HuggingFace Dingdong-Inc): real hourly demand +
     stockout status — but no inventory level, no lead time, no replenishment.
   - *DataCo Smart Supply Chain* (Kaggle): shipping lead time + late-delivery + demand —
     but order-level (not a time series), and no inventory or fill rate.

Conclusion:
- Public datasets can **de-risk the pipeline** (it runs on real, messy data).
- They **do not validate the product thesis** ("raise safety stock 15% → fill-rate
  fragility to lead-time shocks").
- **Real customer operational exports are required for thesis validation.**
- The recommended MVP path is **consultant-assisted onboarding**, not fully self-serve
  fitting: customer sends an ERP/WMS export → we map columns → fit weights → backtest →
  robustness. Build a self-serve fitter only after one real export backtests well.

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

## Update 2 — ops-shaped data + chaos test (Data Risk, not Product Risk)

A hand-built **ops-shaped** dataset (demand + inventory + lead_time + fill_rate + stockout
+ supplier_risk, 20 weeks) was fit: the fitter recovered every causal **sign** correctly
and backtested R²=0.99. Important honesty correction: **this is still synthetic** — the
author defined the structure, directions, and shocks. It is more *realistic* than the
earlier synthetic set, but the same family. It does not validate real customer data.

Validation gates:
| gate | status |
|---|---|
| simple synthetic | ✅ closed |
| ops-shaped synthetic | ✅ closed |
| public dataset | 🟡 partial (pipeline only) |
| **real customer dataset** | ❌ still open |

**Chaos test** (degrade the clean ops-shaped data, re-fit; `scripts/chaos_test.py`):
| corruption | ridge-levels R² |
|---|---|
| baseline | 0.99 |
| noise 10% / 25% | 0.98 / 0.90 ✅ |
| missing 15% | 0.99 ✅ (forward-fill) |
| **outliers 8%** | **0.37 🔴** |
| lag 1wk / seasonality / regime shift | 0.97 / 0.98 / 0.99 ✅ |
| full chaos (3 seeds) | 0.91 / 0.84 / **0.24** |

Conclusion: the fitter is **robust to noise, missing data, lag, seasonality, regime
shift**, but **fragile to outliers** — and stacked full-chaos is seed-dependent (can
collapse). The risk has shifted from *Product Risk* ("can it find relationships?" — yes)
to **Data Risk** ("does useful signal survive dirty ERP data?"). The concrete next fix —
when a real customer dataset justifies it — is **outlier-robust regression**
(Huber / winsorization), NOT a feedback loop added to pass a demo (premature demo-tuning).

## Update 3 — outlier-robust fitting (the one measured weakness, fixed)

The chaos test's only real failure was outlier sensitivity. Added `robust=True`
(per-column winsorization to the train [2.5, 97.5] band) to `backtest_levels` and measured
it against the same chaos benchmark:

| case | non-robust | robust (winsorize) |
|---|---|---|
| clean | 0.99 | 0.99 (no harm) |
| outliers 8% | 0.37 | **0.97** |
| full chaos seed 1/2/3 | 0.91 / 0.84 / **0.24** | 0.93 / 0.88 / **0.94** |

Winsorization neutralizes the outlier collapse without hurting clean data. This was the
right (and only) new code at this stage: a targeted fix on a *measured* weakness, validated
immediately — not a feature or demo-tuning. The likely first-real-dataset killer (ERP
outliers: misposted inventory, one-off orders, migration errors) is now mitigated by
default-available robust fitting.

## Code state
- `core/data_fitting.py`: `fit_weights`/`backtest` now accept an arbitrary `structure`
  (not just the vertical archetype); `backtest_levels` added (ridge regression in levels)
  as the honest predictive yardstick, decoupled from the engine's clamped weights.
- Not yet done (deliberately deferred until an ops-shaped dataset is confirmed to exist):
  rewriting the engine-facing fitter to use lagged / regularized dynamics.
