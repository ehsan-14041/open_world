# InventoryBench replication: protocol

Written on 2026-11-11, after reading the benchmark's source and reproducing its OR baseline on one instance,
and **before any of the new baselines was run on any instance**. Later changes are listed at the end, dated.

Source: https://github.com/TianyiPeng/InventoryBench at commit `62b1f1162f19a41d428d47c6cd4ca431f098f6f3`
(paper: Baek, Fu, Ma, Peng, "AI Agents for Inventory Control: Human-LLM-OR Complementarity", arXiv 2602.12631).
The clone lives in `vendor/` and is not modified. No language model is called anywhere in this work; the LLM
arms are the order sequences the authors published in `results/`.

## Question

The paper reports that an LLM beats its OR baseline overall (0.494 against 0.445, Gemini 3 Flash). Reading the
code shows three things the OR baseline does not do and the LLM prompt is told about or can do:

1. it estimates demand from all history with equal weight;
2. it uses the promised lead time and never looks at the lead times it has seen;
3. it counts lost orders as "in transit" for ever, because the environment reports them that way
   (`env.py` line 252), while the LLM prompt says "Lost orders ... remain in 'In-transit' indefinitely.
   Prolonged absence ... signals a lost shipment" (`run_llm.py` lines 560-561).

**Can simple statistical rules that use the same observations close the gap to the published LLM results?**

## Phase 0 and 1: checks that must pass before the baselines run

- P0-a The copies of `train.csv` / `test.csv` stored beside each model's logs (`empirical_results/`) are
  byte-identical (after line-ending normalisation) to `benchmark/`.
- P0-b Scoring every published order sequence in `results/` with (i) the repository's own
  `eval/evaluate_results.simulate_and_score` and (ii) `ib.score` gives the same reward, and the batch means
  equal the published `scores.json`.
- P0-c For the LLM arms, those rewards equal the per-instance rewards logged in
  `empirical_results/*/benchmark_results.json`.
- P1-a The repository's `scripts/run_or.py`, run unmodified on a stratified sample of 60 instances (10 per
  data type x lead-time setting, drawn with seed 20261116, forced to include stationary and non-stationary
  synthetic patterns), gives the logged OR reward.
- P1-b `policies.OR` run through `ib.simulate` reproduces the published OR order sequence on all 1,320
  instances.

Any mismatch is investigated and explained before going on. A mismatch that cannot be explained stops the work.

## Baselines

All are the benchmark's capped base-stock rule with one piece replaced, so each difference from OR has one cause.
Constants are textbook defaults, fixed here, not tuned.

| Name | Demand statistics | Supply side |
|---|---|---|
| OR | all history | promised lead time; in-transit as reported |
| Rolling | last W = 10 observations (training samples included) | as OR |
| Cusum | observations since the last alarm of a two-sided CUSUM on standardised demand, k = 0.5, h = 4; after an alarm the window restarts with the newest 3 observations; needs 3 observations and a non-zero sd to run | as OR |
| SupplyAware | all history | an order outstanding longer than max(promised, longest lead time seen) is treated as lost and leaves the inventory position; lead time = ceil(mean of lead times seen), promised until one is seen; loss rate = lost / (lost + arrived), at most 0.5; order and cap divided by (1 - loss rate) |
| Rolling+Supply | as Rolling | as SupplyAware |
| Cusum+Supply | as Cusum | as SupplyAware |

Information: only what `ib.Obs` carries (on-hand, in-transit as the environment reports it, past demands, own
past orders, past arrivals with their order period), the training samples, the promised lead time, p and h.
The actual lead-time column of `test.csv` is read by the simulator only. Product text and dates are not used.

**Primary baseline: Cusum+Supply.** It is named now so that the headline comparison is not chosen after
seeing results. The other five are reported in full.

## Metrics

Per instance: raw reward; normalised reward as the benchmark defines it, max(0, reward / (p x total demand));
service level (sold / demand); holding cost. Aggregates: mean over all 1,320; by data type; by lead-time
setting; by synthetic demand pattern.

The normaliser p x total demand is an upper bound that no policy can reach when lead times are positive or
orders are lost. It is called "the benchmark's normaliser" here, never an oracle. As a sensitivity check the
same tables are repeated with the perfect-foresight feasible optimum (`ib.clairvoyant`: an agent that knows all
future demands and lead times), which is itself an upper bound on any real policy, not an achievable target.

## Comparisons and uncertainty

Paired differences, baseline minus comparator, on the same instance. Comparators: OR, and the nine published
LLM arms (3 models x LLM, OR->LLM, LLM->OR). Each published arm is a single run per instance.

Instances are not independent: the same demand trajectory appears under three lead-time settings (and, for
synthetic data, three cost ratios). Intervals are 95% percentile intervals from a cluster bootstrap that
resamples trajectories (10,000 resamples, seed 20261116): cluster = pattern/variant/realisation for synthetic,
article for real.

## Decision rules

- "Matches the LLM": the interval for (Cusum+Supply - LLM arm) on all instances lies above -0.01.
- "Exceeds": it lies above 0.
- "Robust": the sign of the difference is the same in all six data type x lead-time cells, and in at least 8
  of the 10 synthetic patterns.
- Share of the OR-to-LLM gap closed by one change = (variant - OR) / (LLM - OR), reported per lead-time
  setting. This describes what one change to the baseline buys. It is not a statement about why the LLM
  scores what it scores; no ablation of the LLM is run here.

## What is not claimed

Nothing about real inventory systems: the lead-time process and most demand series are synthetic. Nothing
about LLMs in general: three models, one run each, one prompt. No tuning on these 1,320 instances: there is no
held-out set in the benchmark, so any constant changed after seeing results is reported as a sensitivity run
and never replaces the pre-declared number.

## Sensitivity runs (declared in advance, reported separately)

W in {5, 20}; CUSUM h in {3, 5}; uncapped orders; the feasible-clairvoyant normaliser.

## Changes after this point

- 2026-11-11, after Phase 0 and 1 passed and before any new baseline was run: Phase 0 showed that the
  benchmark's max(0, .) clips between 113 and 323 of 1,320 instances per published arm (those with a negative
  reward). An **unclipped** normalised reward (reward / (p x total demand)) is therefore added as a further
  sensitivity table. The pre-declared primary metric is unchanged.
