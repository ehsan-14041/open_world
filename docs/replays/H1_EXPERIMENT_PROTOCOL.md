# H1 experiment protocol — pre-registration

> **Written before any replay of the experimental model was run.** The acceptance criteria in
> §5 are fixed at the moment this file was committed and are not to be revised after results
> are seen. Results go in `H1_EXPERIMENT_RESULTS.md`.

## 1. Question

Does adding **only** the independently supported vessel-queue stock mechanism reduce the
measured early-timing bias on the existing historical replays, **without retuning any
existing model parameter**?

This is an experimental structural test, not a production upgrade. All four answers are
acceptable outcomes: yes, partially, no, inconclusive.

## 2. What is being compared

```
port_disruption                          (frozen baseline, 8 variables, 9 edges)
        vs
port_disruption_h1_queue_experimental    (baseline + vessel_queue stock)
```

Everything that still applies is held identical. The baseline module file is not modified;
the experimental module is a separate, separately selectable module.

## 3. The mechanism under test

H1: the physical vessel/cargo queue at a disrupted port is a **stock** that accumulates when
arrivals exceed processing capacity and drains only when processing exceeds arrivals.

```
processed(t) = min( queue(t) + arrivals(t), processing_capacity(t) )
queue(t+1)   = max( 0, queue(t) + arrivals(t) − processed(t) )
processing_capacity(t) = (port_capacity(t) / 100) × surge
```

Invariants guaranteed by construction: the queue cannot go negative; it persists across
turns; restoring capacity does not delete it (only raises the drain rate); processing is
bounded by capacity.

**Unit: normal-flow-weeks of unprocessed arrivals.** Chosen because it requires no
unsupported conversion. Converting to vessels or TEU would need a conversion factor that no
data supports for these events.

### Topology change (the smallest that expresses H1)

```
BASELINE       port_capacity ──(linear, lag 0–1)──▶ shipping_delay

EXPERIMENTAL   port_capacity ──(conservation)──▶ vessel_queue ──(linear, lag 0–1)──▶ shipping_delay
```

**Design decision — why the direct edge is replaced rather than kept alongside.** The
baseline edge's own stated mechanism is *"lost berth and yard throughput queues vessels and
boxes; queueing time is added to transit time"* — that **is** the queue, in reduced form.
Keeping it and adding the queue path would double-count the same physical mechanism, which
§6 of the task brief forbids. The direct edge is therefore superseded, not supplemented. This
is a topology decision justified by the module's own mechanism text, not a tuning decision.

Everything downstream of `shipping_delay` is untouched.

### Explicitly NOT changed

- `order_backlog` remains a relaxation variable. **H2 is `not_supported` and is not
  implemented.** No downstream accumulation, memory or lag change.
- No existing coefficient, lag, polarity, baseline, scale, response or threshold is altered.
- No new nonlinearity, no new recovery rule, no hardcoded recovery delay.

## 4. New parameters — all of them

| Name | Meaning | Unit | Value / range | Evidence status | Why necessary |
|---|---|---|---|---|---|
| `inflow` (arrivals) | normal inbound flow | normal-flow-weeks per week | **1.0, fixed** | definitional | Defines "normal": at full capacity and no surge, arrivals = processing, so the queue is exactly 0 in steady state. Not a free parameter. |
| `surge` (`queue_clearance` axis) | processing headroom above nominal while a backlog exists | multiple of nominal capacity | **1.05 / 1.15 / 1.35** (slow/central/fast) | `expert_assumption` | Without headroom a backlog can *never* be worked off, because restored capacity exactly equals arrivals. Ports clear backlog with overtime, extra gangs, extended gates. Swept, not fitted. |
| `vessel_queue → shipping_delay` effect | how much waiting cargo shows up as transit delay | dimensionless (deviation units) | **0.08 / 0.15 / 0.25** | `expert_assumption` | Replaces the coefficient of the superseded direct edge. Bound to the existing `alternative_capacity` axis, so no new axis binding is introduced. |

Three new parameters, one of which is definitional. **H1 being independently supported does
not make any of these supported** — they are expert assumptions with predeclared ranges.

Ranges were chosen before running anything, by the requirement that the central setting
produce a delay contribution of roughly the same order as the baseline's direct edge, so the
experiment tests *persistence* rather than a change in overall magnitude.

## 5. Acceptance criteria — FIXED

### Primary metrics

`peak_timing_bias`, `recovery_bias`, `combined_timing_bias` — sign preserved. Negative means
the model is early.

Baseline values to beat (already measured, `CROSS_EVENT_DIAGNOSIS.md`):

| Metric | Baseline |
|---|---|
| Yantian — peak timing of `shipping_delay` | **−9 weeks** |
| Baltimore — recovery milestone (`port_capacity`) | **−6 weeks** |
| Combined median timing bias | **−6 weeks** |

### Predicted sensitivity — declared in advance

**Baltimore's only scored milestone is on `port_capacity`, and H1 does not change how
`port_capacity` evolves.** The queue sits *downstream* of capacity; capacity still relaxes
back exactly as before. So the Baltimore scored metric is expected to be **mechanically
insensitive** to this change, and an unchanged Baltimore number is the predicted outcome, not
a failure. Only Yantian's metric is mechanically able to move.

This is a limitation of the available observations, not of H1, and it is stated here so it
cannot be presented afterwards as either a success or an excuse.

### Verdict rule

**`experimental_mitigating`** requires ALL of:

1. **Timing** — combined median timing bias moves toward zero by **≥ 2 turns**.
2. **Per event** — improves on every event whose metric is mechanically sensitive to the
   change, and does **not degrade by more than 1 turn** on any event whose metric is not.
3. **Direction preserved** — direction-match rate is not lower than baseline.
4. **No magnitude blow-up** — envelope coverage does not fall to zero on any variable where
   the baseline was above zero, and peak magnitude error does not more than double.
5. **No retuning** — one shared experimental configuration across both events, and no
   baseline parameter changed.

**`experimental_no_effect`** — combined median timing bias changes by **< 2 turns** in
absolute value and criteria 3–5 hold.

**`experimental_worse`** — combined median timing bias moves *away* from zero by ≥ 2 turns,
**or** direction validity degrades, **or** criterion 4 fails.

Otherwise: **inconclusive**, stated as such.

### Secondary observations (reported, not gating)

direction accuracy · peak magnitude error · envelope coverage · first divergence turn ·
queue trajectory shape (accumulation start, peak, clearance) · whether recovery slowness
*emerges* from residual queue rather than being imposed.

## 6. Anti-retuning constraints

- One configuration for both events. Per-event parameter values are forbidden and are
  checked by a test.
- New parameters are **swept over their predeclared ranges**, never point-fitted.
- No baseline value may change; the frozen-module test must still pass afterwards.
- If the experiment fails, the reported outcome is the failure. No parameter is adjusted to
  rescue it.

## 7. What this experiment cannot establish

Even a clean pass means **`experimental_mitigating`, not validated**. Both events used here
were already used to *diagnose* the defect, so this is in-sample mitigation testing. Claiming
generalisation requires an independent held-out event, which does not exist
([`EVENT3_SEARCH.md`](EVENT3_SEARCH.md)). The `declare_split()` guard remains in force and
will continue to refuse a held-out claim with only two events.

The known defect may move `known → mitigated` on a pass. It may **not** move to
`historically_validated`.

## 8. Order of work

1. ✅ Verify the baseline module's pinned semantics.
2. ✅ Create the experimental module as a separate file.
3. ✅ Write this protocol.
4. Mechanism-level conservation and counterfactual sanity tests — synthetic only, no
   historical events.
5. Only then: run Yantian and Baltimore, baseline vs experimental.
