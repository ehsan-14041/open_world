# What data the engine needs, and what it does with it

This is the reference for the "ops + real data" path: what to ask a customer for, the
exact format, how much, and — crucially — **why** the system needs it and **what it does**
with it. Template file: `data/templates/ops_history_template.csv`.

---

## 1. Why data at all (the whole point)

Today the engine's causal weights (e.g. "higher lead time → lower fill rate, strength
−0.5") are **domain guesses**, baked into `adapters/ops_scenario_builder._ARCHETYPE_CAUSAL`.
A simulator built on guessed coefficients is a toy: the numbers look precise but aren't
grounded in *this* customer's reality.

Real historical data lets us **fit those weights from the customer's own operation** —
we keep the *structure* (which variables affect which, domain knowledge) but learn the
*magnitudes* from their data. Then we **backtest**: did the fitted model reproduce their
last N weeks? If yes, the sensitivity/robustness analysis on top is trustworthy. That is
the difference between "interesting demo" and "I'd pay for this."

---

## 2. What the system actually does with it (the pipeline)

```
customer CSV (weekly history)
      │
      ▼
[1] FIT      core.data_fitting.fit_weights
            For each outcome (e.g. fill_rate), regress its week-over-week change on the
            week-over-week change of its declared drivers (inventory, lead_time, …).
            The standardized coefficients become the causal weights.  -> per-target R²
      │
      ▼
[2] BACKTEST core.data_fitting.backtest
            Fit on the early weeks only; predict the held-out recent weeks one step
            ahead; compare to what actually happened.  -> overall R² / MAPE / verdict
            (This is the honesty gate. Noise backtests as "weak"; real structure as "strong".)
      │
      ▼
[3] BUILD    build_scenario(profile, fitted_links=...)
            The fitted weights replace the guessed ones in the scenario.
      │
      ▼
[4] ROBUSTNESS / WAR-ROOM   (unchanged engine)
            Now the sensitivity sweep is around the customer's *real* coefficients, so
            "this decision is fragile to lead-time variance" is grounded, not invented.
```

The key point: **only step [1]–[3] are new. Steps [4] (the whole robustness/RDM engine)
are reused unchanged.** Data plugs in at one seam.

---

## 3. The data: format

- **One CSV file.**
- **One row per time period**, in **chronological order** (oldest first). Weekly is ideal;
  monthly works.
- The header row names the columns; each value is a number.
- The engine compares **week-over-week change**, so consecutive, evenly-spaced rows matter
  more than calendar dates. (A `date`/`week` column is fine — it's ignored if non-numeric.)

### How many rows?
- **Absolute minimum to backtest: 8 periods** (it needs to hold some out).
- **Usable: ~20–30 periods.**
- **Good/trustworthy: 52+ periods** (a year of weekly data). More rows → more stable fit,
  tighter backtest. With <15 rows the fit is fragile and the report will warn you.

---

## 4. The columns (what each means, where it comes from)

Provide **whatever of these you have** — the fitter uses the present columns and keeps the
archetype guess (with a warning) for any missing one. The more real columns, the more of
the model is data-grounded. Names should match these (or be renamed to them).

| Column | Meaning | Typical source | Unit |
|---|---|---|---|
| `weekly_demand` | units demanded that week | ERP / sales orders | units |
| `inventory_on_hand` | stock on hand at week end | WMS / ERP | units |
| `safety_stock` | safety-stock policy level | planning system | units |
| `lead_time_days` | actual replenishment lead time | procurement / supplier | days |
| `fill_rate` | orders filled on time (service level) | OMS / WMS | 0–1 |
| `unit_cost` | landed cost per unit | ERP / finance | $ |
| `supplier_risk` | supplier reliability risk index | scorecard (or proxy) | 0–1 |
| `capacity_utilization` | how full capacity ran | MES / ops | 0–1 |
| `holding_cost_weekly` | weekly carrying cost | finance | $ |
| `stockout_risk` | stockout incidence/risk | WMS | 0–1 |
| `backlog_weeks` | weeks of backlog | OMS | weeks |

### Drivers vs. outcomes (why the columns are split this way)
- **Drivers (what you control / observe):** `weekly_demand`, `safety_stock`, `supplier_risk`,
  `unit_cost`. These are the *inputs* the model treats as given each week.
- **Outcomes (what the model learns to reproduce):** `fill_rate`, `inventory_on_hand`,
  `lead_time_days`, `stockout_risk`, `holding_cost_weekly`, `capacity_utilization`,
  `backlog_weeks`. These are what the fit + backtest are scored against.

The exact wiring (which driver affects which outcome) is the per-vertical structure in
`_ARCHETYPE_CAUSAL`. For **distribution**, e.g.:
`weekly_demand → inventory_on_hand → fill_rate`, `lead_time_days → fill_rate`,
`supplier_risk → lead_time_days`, `fill_rate → stockout_risk`. Data fits the *strength* of
each of those arrows.

---

## 5. How to run it (when you have a file)

```
python scripts/fit_spike.py  <their_file>.csv  <vertical>
```
`vertical` ∈ `distribution | manufacturing | retail | multi_echelon |
contract_manufacturing | general_ops`.

Read **`BACKTEST overall R²`**:
- **≥ ~0.5** → the model reproduces their history → the product is real → build the upload UI.
- **0.3–0.5** → partial; some outcomes model well, others don't (check per-target R²).
- **< ~0.3 ("weak")** → this structure can't model their data. No UI fixes that — change the
  causal structure for that vertical, or pick a different vertical/customer.

---

## 6. Honest caveats (so you're not surprised)

- **Real exports are messy.** ERP/WMS dumps rarely have these exact columns. Expect to
  rename columns and possibly derive a couple (e.g. `holding_cost_weekly` from
  `inventory_on_hand × unit_cost × holding_rate`). Budget time for this mapping.
- **Short/noisy series fit poorly** — that's correct behavior, not a bug. The backtest
  protects you: if it says "weak", believe it.
- **Proxies are fine to start.** No `supplier_risk` index? Use late-delivery rate. The fit
  will tell you if the proxy carries signal.
- **One clean dataset that backtests well beats ten messy ones.** For the first validation,
  you only need a single real customer history where the backtest passes.
