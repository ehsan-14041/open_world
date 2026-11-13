# InventoryBench replication, second step: a split-half test

Written on 2026-11-13, before the split was drawn and before any new policy was run. It follows
[PROTOCOL.md](PROTOCOL.md), whose files and numbers are left untouched. No language model is called.

## Why

The first step had no held-out data: the baselines were designed after reading the benchmark's code, and all
1,320 instances were used to report them. One gap also remained: the best published arm (Gemini 3 Flash,
OR->LLM) scored 0.385 on the stochastic-lead instances against 0.350 for Cusum+Supply.

Two questions:

- Q1. Does the first step's result hold on instances that played no part in designing a rule?
- Q2. Can a better supply rule, designed on one half of the benchmark, close the remaining gap on the other half?

## The split

Unit: the demand trajectory (`cluster` in `ib.py`; 80 synthetic, 200 real). All instances of a trajectory, under
every lead-time setting and cost ratio, go to the same half. Within each data type the clusters are sorted,
shuffled with `random.Random(20261117)`, and the first half becomes **design**, the rest **test**.
`split.py` writes `split.json`; nothing else may assign instances.

## Design half

Free exploration of the supply side only (how the pipeline, the lead time, the loss rate, the order inflation and
the cap are computed from what the environment shows). The demand side stays the pre-declared CUSUM rule.
Selection criterion: mean normalised reward (the benchmark's metric) on the design half's stochastic-lead
instances. Every candidate tried is logged in `design_log.json`. One policy, **Cusum+Supply2**, is then frozen in
`policies2.py` and its definition and the design-half numbers are appended below **before** the test half is run.

`design.py` loads design-half instances only. The published LLM order sequences of the test half are not read
during design.

## Test half: run once

`test_half.py` runs OR, Cusum+Supply (the first step's primary, unchanged) and Cusum+Supply2 on the test half and
scores the published arms on the same instances. It is run once. If it has to be re-run because of a bug, the
bug and both outputs are reported.

Metrics as in PROTOCOL.md: the benchmark's normalised reward (primary), plus unclipped and
feasible-clairvoyant-normalised as sensitivity. Intervals: 95% cluster bootstrap over test-half trajectories,
10,000 resamples, seed 20261117.

## Decision rules

- Q1 holds if, on the test half, the interval for (Cusum+Supply - Gemini 3 Flash LLM) lies above 0, and the
  interval for (Cusum+Supply - OR) lies above 0.
- Q2, on the test half's stochastic-lead instances, Cusum+Supply2 minus Gemini 3 Flash OR->LLM:
  - **gap closed** if the interval lies above -0.01;
  - **the hybrid keeps an advantage** if the interval lies entirely below 0;
  - otherwise **undecided**.
  The same difference is reported for all instances of the test half and under the two sensitivity metrics; the
  verdict is stated for the primary metric and any disagreement of the sensitivity metrics is reported beside it.
- All nine published LLM arms are reported, not only the one named above.

## Known weaknesses, stated in advance

- The first step already reported aggregate results on all instances, so the designer has seen pooled numbers
  that include the test half. No per-instance result of the test half is consulted from here on.
- Synthetic trajectories in the two halves can come from the same generating pattern (different realisation),
  so the halves are not independent draws from different worlds.
- A rule designed on this benchmark encodes this benchmark's lead-time process (1, 2, 3 or lost). Nothing here
  speaks to other supply processes or to real systems.
- Each published LLM arm is one run per instance.

## Frozen policy and design-half numbers

Frozen on 2026-11-13, before `test_half.py` existed. 123 candidates were tried on the design half (two grids;
all in `design_log.json`). The member with the highest mean normalised reward on the design half's 220
stochastic-lead instances was taken, as the criterion says:

**Cusum+Supply2** = CUSUM demand statistics (unchanged) with this supply side:

- an order is treated as lost once it has been outstanding longer than max(promised, rounded-up mean of the
  lead times seen); it then leaves the inventory position;
- lead time for the base stock = rounded-up mean of the lead times seen (promised until one is seen);
- **no** inflation of the order by the loss rate (the first step's rule inflated, and that turned out to hurt);
- base stock reduced by 0.5 x loss rate x (1 + L) x mean demand;
- cap = 0.8 x (one period's mean + 1.645 sd).

Design-half numbers (benchmark metric / unclipped):

| | stochastic-lead (220) | fixed-lead (440) | all design (660) |
|---|---|---|---|
| Cusum+Supply (first step) | 0.340 / 0.254 | 0.631 / 0.528 | 0.534 / 0.437 |
| Cusum+Supply2 | 0.420 / 0.410 | 0.633 / 0.542 | 0.562 / 0.498 |

Two of the chosen constants (cap 0.8, reduction 0.5) sit at the edge of the second grid; the search was not
extended further. The gain from those two over the plainer member (cap 1.0, no reduction: 0.398) is small next
to the gain from dropping the inflation (0.340 to 0.398), so most of the improvement is one structural change.

## Test-half record

`test_half.py` was run once, on 2026-11-13. No bug was found and it was not re-run. Output: `test_half.json`,
`test_half.md`.

- Q1 holds: on the test half Cusum+Supply minus OR is +0.091 [+0.077, +0.105] and minus Gemini 3 Flash LLM is
  +0.046 [+0.036, +0.055].
- Q2: **gap closed**, and more. On the test half's 220 stochastic-lead instances Cusum+Supply2 minus Gemini 3
  Flash OR->LLM is +0.032 [+0.020, +0.044]; unclipped +0.048 [+0.025, +0.071]; clairvoyant-normalised +0.062
  [+0.038, +0.086]. On all 660 test instances: +0.022 [+0.013, +0.030]. The sensitivity metrics agree in sign.
- Against all nine published arms, on all test instances, the difference is positive with an interval above 0.
  On the fixed-lead instances alone it is indistinguishable from the two LLM->OR arms of Gemini and Grok
  (-0.001 and -0.002, intervals include 0).
