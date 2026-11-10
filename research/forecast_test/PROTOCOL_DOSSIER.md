# Forecast test 2: does the dossier method make one narrator more accurate?

Written 2026-11-11, before any dossier or dossier forecast existed. The direct forecasts (`L`) and the
driver-list forecasts (`L2`) of the first test already exist and are reused unchanged.

## Why

In `research/harness_vs_chat` (round 4) one narrator with actor dossiers was preferred by blind judges over
the same model asked directly (22 of 24 judgments). Those judges scored how the output reads, not whether it
is right. This test asks the remaining question on outcomes that are known: does the same method produce
better probabilities?

## Setup

- **Questions:** the same 300 sampled Polymarket politics questions as the first test
  (`batches/q_00..09.json`): opened on or after 2026-07-30, resolved cleanly. Same model: Claude Opus 5.5 as
  sub-agents (stated training cutoff June 2026), batches of 30, no news, no search, no market price.
- **Step D1, dossier (one sub-agent per batch):** for every question, from its own knowledge as of its
  training data: a short background, 2 to 4 actors each with a public part and a private part (likely red
  lines, constraints, intentions: its best estimate), and up to 3 outside events with a rough chance.
  No probability is asked for.
- **Step D2, narrator (a fresh sub-agent per batch):** given the question and the dossier, plays the
  situation forward in three stages from the start date to the close date, then states the probability of
  "Yes". This is arm `D`.

## What this test can and cannot say

The dossier is written by the model from memory. A dossier written with web search would see the outcome,
because every question is already resolved and a search cannot be limited to a date; that would leak the
answer. So this test measures the **method** (structure and playing forward) with no new information. It
does not measure what a dossier with true, current, pre-event facts would add; that needs questions that
are still open.

## Metrics and what counts as passing

Brier score. Paired differences `D - L` and `D - L2` with a bootstrap 95% interval (10,000 resamples), on
the questions that have a usable answer in all three arms.

- **Pass:** `D` has a lower Brier score than both `L` and `L2` and both intervals exclude zero.
- **Fail (method hurts):** `D` is higher than `L` with an interval excluding zero.
- Anything else: no detectable difference.

`L` and `L2` were produced on 2026-11-10 in separate runs of the same model on the same batches; run-to-run
variation of the model is part of the paired differences. Sub-agents are instructed to use no tool except
reading their input files and writing their output file; this is an instruction, not a technical block.
No retry: a question with an unusable answer is dropped from every arm.
