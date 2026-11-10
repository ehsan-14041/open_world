# Event backtest protocol: does a fitted engine predict held-out historical shocks?

Written on 2026-11-10 **before any outcome was computed**. Only the file structure and coverage of
the two data files had been inspected. Any later change is recorded at the bottom.

## Question

If the engine's coefficients are fitted on historical events instead of guessed, does it predict
events it has not seen better than simple baselines? If not, "turn history into a dataset and train
the engine" is not worth building on.

## Why this shock

Large currency depreciations, and what they do to consumer prices over the next year.

- Both the shock and the response are public, monthly, for many countries
  (Bank for International Settlements: `WS_XRU` US dollar exchange rates, `WS_LONG_CPI` consumer prices).
- Events are defined **from the data by a rule**, so no event list is curated by hand.
- It is an edge the engine already uses with a guessed coefficient
  (`fx_rate -> price_level` in `research/iran_game_studio/iran_mobile_studio_v0.json`: 0.3 / 0.5 / 0.7).

## Event rule

Monthly average exchange rate, local currency per US dollar. Month `t` is an event when:

1. `FX(t) / FX(t-1) - 1 >= 0.15`;
2. no month in `t-24 .. t-1` had a one-month depreciation of 15% or more;
3. exchange rate and CPI are both present for every month `t-13 .. t+12`;
4. CPI inflation over the twelve months before, `CPI(t-1)/CPI(t-13) - 1`, is at most 100%
   (the engine is linear; hyperinflations are out of scope);
5. the country is not the United States.

## Variables (deviation from the pre-shock trend)

- `g` = average monthly CPI growth over `t-13 .. t-1`; `d` = the same for the exchange rate.
- For `k = 0 .. 12`: `devCPI_k = CPI(t+k) / (CPI(t-1) * (1+g)^(k+1)) - 1`, and `devFX_k` likewise.

## The engine under test

The repository's own engine (`event_sim.engine`), monthly turns, two variables. The observed
`devFX` path is held by events (a conditional forecast: given what the currency did, what did
prices do). One edge `fx -> cpi` with coefficient `c` and lag `L`; `cpi` relaxes at rate `r`.

Fit on training events by grid search minimising the sum of squared errors of `devCPI_k`,
`k = 0..12`: `c` in 0..1.5 step 0.05, `r` in 0.05..1.0 step 0.05, `L` in {0, 1, 2, 3}.

## Baselines

- **B0** no effect: `devCPI = 0`.
- **B1** average of previous events: the mean training `devCPI_k` path, whatever the shock size.
- **B2** plain regression: `devCPI_k = b_k * devFX_k`, one slope per horizon fitted on training.
- **E-prior** the engine with the guess already in the repository: `c = 0.5`, lag 1 month,
  `r = 1 - 0.97^30.4 = 0.60` per month (0.03 per day in the game model).

## Split

- **Primary:** events sorted by date; the earliest 80% train, the latest 20% test.
- **Robustness:** 5-fold cross-validation grouped by country.

## Metrics

- Primary: RMSE of `devCPI_12` on test events, in percentage points.
- Secondary: RMSE over the whole path `k = 0..12`; median absolute error at `k = 12`.

## What counts as passing

The fitted engine has lower primary RMSE than **B0 and B1** on the temporal test set **and** in the
grouped cross-validation. Beating B2 is reported separately: it says whether the engine's dynamics
add anything over a regression. Failing either part is reported as failing.

## Changes after results were seen

The protocol was run once, unchanged, and **failed** (see `reports/event_backtest/RESULTS.md`).

Afterwards, three exploratory checks were run to understand the failure. They are post-hoc, were
chosen after seeing the result, and do not change the verdict:

- A: the same split with an absolute-error (robust) loss instead of squared error;
- B: training only on events from 1990 onward;
- C: scoring the test set without the October-November 2008 cluster.
