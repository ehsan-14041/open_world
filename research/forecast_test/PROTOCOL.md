# Political forecasting test: does the engine add anything to a language model?

Written on 2026-11-10 **before any forecast was made or scored**. Only the API field names and one
price history were inspected. Changes after results are recorded at the bottom.

## Question

On resolved political questions, does "language model + engine" forecast better than the language
model alone? If not, taking the engine into political forecasting is not worth building.

## Questions

Source: Polymarket (public API), events tagged `politics`, closed.

A market is eligible when all of these hold:

1. two outcomes, "Yes" and "No", resolved cleanly (final prices exactly 1 and 0);
2. traded volume of at least 10,000 USD;
3. at least 14 days between its start date and its close;
4. its start date is at least 30 days **after the model's training cutoff** (so the model cannot
   know the answer). The cutoff is the one the model's provider states; it is passed in as a parameter;
5. it is the highest-volume eligible market of its event (one question per event).

Sample: 300 eligible questions drawn at random with seed 20261110 (all of them if fewer).
The 300 earliest eligible questions outside the sample give the base rate.

## What the model is given

The question, the market's resolution rules, the start date and the close date. No news, no
search, no market price. Every arm gets the same information, so the comparison is between
methods, not between information sets.

## Arms

| Arm | What produces the probability |
|---|---|
| `half` | always 0.5 |
| `base_rate` | share of "Yes" among the base-rate questions |
| `market` | the market's own price about 7 days after it started (reference only) |
| `L` | the model, asked directly |
| `L2` | the model after writing a structured list of drivers (no engine) |
| `LE1` | the engine alone: share of census worlds in which the outcome ends above zero |
| `LE2` | the model after being shown the engine's output for its own drivers |

`L2` is the control that matters: without it, any gain in `LE2` could come from thinking twice.

## The engine arm

The model writes 3 to 6 drivers. Each has a direction (toward Yes or No), a strength
(weak 0.2, medium 0.5, strong 0.8), a present level from 0 to 1, and a delay in weeks (0 to 8).
It also gives a starting tendency from -1 to 1.

The repository's engine runs weekly turns to the close date (at most 26). Each driver is held at
its level; one edge per driver feeds an outcome variable (response 0.3 per week) whose baseline is
the stated tendency: the drivers move the outcome away from where things stand today. Each driver's strength is an uncertain axis at 0.5x, 1x and 1.5x, so the census
has 3^k worlds. `LE1` is the share of worlds whose outcome is above zero at the close, clipped to
0.02..0.98. The model is then shown that share, and which drivers flip the result, and gives `LE2`.

This mapping from a yes/no question to an engine run is a design made for this test. A failure
could be the mapping's fault and not the engine's; that limit is stated with the result.

## Metrics and what counts as passing

- Brier score (mean squared error of the probability; lower is better) for every arm.
- Primary comparisons: `LE2` against `L2`, and `LE2` against `L`, as paired differences with a
  bootstrap 95% interval (10,000 resamples of questions).
- **Pass:** `LE2` has a lower Brier score than both `L2` and `L`, and both intervals exclude zero.
  Anything else is reported as not passing.
- A question on which the model's reply cannot be parsed after one retry is dropped from every
  arm, and the number dropped is reported.

## Changes after results were seen

Before any forecast existed: the parity check against the engine showed my quick replica let the
starting tendency decay, while the engine keeps it as the baseline. The replica and the wording above
were corrected to the engine's behaviour. No result had been seen.

Before any forecast existed (2026-11-10): no API key was available, so the model is Claude Opus 5.5
run as sub-agents of the coding session instead of an API. Differences from the text above:

- training cutoff taken as 2026-06-30 (the stated cutoff is June 2026), so questions start on or
  after 2026-07-30;
- questions are answered in batches of 30 per sub-agent, each stage by a fresh sub-agent, instead of
  one request per question; temperature cannot be set;
- sub-agents are instructed to use no tool except reading their input file and writing their output
  file. This is an instruction, not a technical block: a sub-agent that searched the web would know
  outcomes. Each is asked to state whether it used any other tool;
- there is no retry: a question with an unusable answer at any stage is dropped from every arm.
