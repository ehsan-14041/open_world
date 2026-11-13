# Draft issue for TianyiPeng/InventoryBench (not yet posted)

**Title:** OR baseline treats lost orders as in transit forever; a simple lost-order-aware rule matches or exceeds the published LLM arms

---

Thank you for releasing the benchmark with full order logs. That made an exact, zero-LLM-call replication possible.
I would value your view on the findings below, and I may well have misread something.

Everything refers to commit `62b1f1162f19a41d428d47c6cd4ca431f098f6f3`.

## What reproduced

- Re-simulating all 1,320 instances from the logged orders reproduces every reward in your results (15,840 logged
  rewards, zero difference), and the scores from `eval/evaluate_results.py`.
- A re-implementation of the capped OR policy in `scripts/run_or.py` gives identical orders on all 1,320 instances.

## Observations

1. **The OR baseline never writes off a lost order.** In the stochastic lead-time setting a lost order stays in
   the in-transit quantity (`or_agent/envs/VendingMachine/env.py`, around line 252), and `scripts/run_or.py`
   subtracts that quantity from its base stock for the rest of the episode. It also keeps using the promised
   lead time rather than the lead times it has observed.
2. **The LLM prompt is told about lost orders** (`scripts/run_llm.py`, around lines 560-591), so in that setting
   the LLM and OR arms do not work from the same information.
3. **The "perfect score" is p x total demand**, an upper bound that no ordering policy can reach. A
   perfect-foresight policy that respects the lead times reaches about 0.90 of it at L=4 and about 0.69 in the
   stochastic setting.
4. **Clipping the normalised reward at 0** hides negative-reward instances: between 113 and 323 per arm.
5. Minor: the README says 48 periods for the real trajectories; the data has 47.

## What a corrected statistical baseline scores

No LLM is called. The rule uses only what the environment shows at decision time: a CUSUM change detector on
demand, and a supply side that drops an order from the inventory position once it is overdue and uses the
observed mean lead time.

All 1,320 instances, benchmark metric:

| arm | score |
|---|---|
| OR (published) | 0.445 |
| OR + lost-order-aware supply only | 0.505 |
| CUSUM + lost-order-aware supply (declared before running) | 0.536 |
| Gemini 3 Flash (LLM) | 0.494 |
| Gemini 3 Flash (OR->LLM), best published arm | 0.538 |

The supply fix alone closes about 91% of the gap between OR and Gemini 3 Flash (LLM) in the stochastic setting,
and changes nothing in the fixed lead-time settings.

A second step split the benchmark in half by demand trajectory. A supply rule designed only on one half was
frozen and then run once on the other half (660 instances):

| arm | all | stochastic lead |
|---|---|---|
| OR (published) | 0.447 | 0.155 |
| frozen rule | 0.558 | 0.417 |
| Gemini 3 Flash (LLM) | 0.492 | 0.357 |
| Gemini 3 Flash (OR->LLM) | 0.536 | 0.385 |

Frozen rule minus Gemini 3 Flash (OR->LLM), stochastic-lead instances: +0.032, 95% cluster-bootstrap interval
[+0.020, +0.044]. The unclipped and feasible-clairvoyant-normalised metrics agree in sign. On the fixed
lead-time instances the rule is indistinguishable from the Gemini and Grok LLM->OR arms.

## Limits of this replication

- The rule was written after reading the benchmark's code and encodes its lead-time process (1, 2, 3 or lost).
  It says nothing about other supply processes or real systems.
- Before the split, pooled results on all instances had already been seen.
- Synthetic trajectories in the two halves can share a generating pattern.
- Two of the frozen rule's constants sit at the edge of the search grid.
- Each published LLM arm is one run per instance.

## Questions

- Is the OR arm's handling of lost orders intended, as a deliberately naive baseline?
- Would you consider adding a lost-order-aware OR baseline, and reporting unclipped scores and a feasible bound
  beside the current normalisation?

Code and protocols (written before each run): `<link to be added once the branch is public>`
