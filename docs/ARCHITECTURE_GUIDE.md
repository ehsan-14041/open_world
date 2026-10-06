# Architecture Guide: Deterministic Decision Physics Runtime

This document is the **Formal Execution Contract** of the system. It defines the exact
state-transformation mechanics, phase precedence, and propagation physics per simulation
tick. It is *not* a code summary — it is the operational truth the runtime enforces and
the Linter validates.

> Accuracy rule: every claim below maps to real code (`simulation/loop.py`,
> `core/soft_constraints.py`, `core/physics_core.py`, `core/rule_engine.py`,
> `core/threshold_rules.py`, `core/world_model.py`). If the runtime changes, this file
> changes in the same commit. Where a mechanism is subtle, the source is cited inline.

---

## 1. The core loop execution cycle ($t \to t+1$)

Each tick is a discrete state transition driven by `SimulationLoop.step()`. The phases run
in this exact order:

```
[State S_t]
   │
   ├── 1. Ingestion        read S_t (world.snapshot)
   ├── 2. Proposal         agents observe S_t, emit raw per-agent deltas
   ├── 3. Merge            net additive merge -> delta_after_merge
   ├── 4. Dynamism Guard   _ensure_minimum_delta (only if ALL deltas ~0)
   ├── 5. Soft Constraints  apply_all_constraints -> delta_applied  (scale-aware)
   ├── 6. Physics + Propagation  world.apply_delta (STOCK/FLOW update, then causal graph)
   ├── 7. Cascade (Rules)  run_rules on post-propagation snapshot (non-linear shocks)
   └── 8. Commit           regime detect, objectives, snapshot -> S_(t+1) + provenance
```

### 1.1 Phase precedence protocol

1. **Ingestion** — `self.world.snapshot()` provides the immutable read of $S_t$.
2. **Proposal** — agents are **simultaneous-move** (every agent sees the *same* $S_t$;
   no agent sees another's move this tick) but are executed **sequentially** in a loop
   (`step()` iterates `self.agents`). Each emits `delta_raw_per_agent[name] = {var: Δ}`.
3. **Merge** — `merge_delta_raw` performs a **net additive** combine per variable
   → `delta_after_merge`. (Agent 1 `+10` and Agent 2 `−4` on $V$ ⇒ net `+6`.)
4. **Dynamism Guard** — `_ensure_minimum_delta` fires **only when no variable changed at
   all** (`not has_changes`). It then injects a *negligible, bounded* liveliness nudge into
   one randomly chosen variable: `gauss(0, 0.1%·|value|)` clamped to `±0.5%·|value|` and to
   the variable's `rate_limit`. It is a frozen-world fallback, **not** a floor applied to
   small intentional deltas. A deliberate `steady` no-op therefore leaves large variables
   essentially flat.
5. **Soft Constraints** — `core/soft_constraints.apply_all_constraints` filters the merged
   delta: `rate_limit` per variable → `change_budget` scaling → diminishing returns
   (`soft_max`/`softness`) → hard clip. Bounds come from `_effective_spec` (§3.3), which is
   **scale-aware**: a variable outside the default $[0,100]$ with no explicit spec is left
   unbounded. Output: `delta_applied`.
6. **Physics + Propagation** — `world.apply_delta(combined_delta)` (`core/physics_core`):
   each target updates by behavior type (§3.1), then **structural propagation** runs along
   `causal_links` (`core/propagation`), then specced variables are clamped
   (`clamp_state_to_specs`).
7. **Cascade (Rules)** — `core/rule_engine.run_rules(snapshot, world, rules)` evaluates
   each rule's `condition_key` against the **post-propagation** snapshot; a fired effect
   mutates state immediately via `world.apply_delta` (additively, §3.1).
8. **Commit** — regime is detected (`core/regime_detector`), the turn record (delta
   lifecycle, propagation trace, regime) is appended to `provenance`, and $S_{t+1}$ is
   snapshotted.

---

## 2. Layered execution stack

Responsibilities isolate into five conceptual layers. Definition flows downward; execution
reads upward. (Conceptual model — the loop is the single executor.)

```
┌───────────────────────────────────────────────────────────┐
│ Layer E: Constraint   scale-safe specs, rate_limit, clamp  │
├───────────────────────────────────────────────────────────┤
│ Layer D: Event        rule_engine, non-linear cliffs       │
├───────────────────────────────────────────────────────────┤
│ Layer C: Causal       causal_links, graph propagation      │
├───────────────────────────────────────────────────────────┤
│ Layer B: Structural   initial_state, variable_specs        │
├───────────────────────────────────────────────────────────┤
│ Layer A: Intent       agents.objectives, proposals         │
└───────────────────────────────────────────────────────────┘
```

- **A — Intent** (teleological): what agents *want* (`objectives`). Cannot touch state
  directly; only proposes deltas.
- **B — Structural**: the scenario's physical constants — variable values, types, scales.
- **C — Causal**: the propagation graph; how a change in $X$ forces a change in $Y$.
- **D — Event**: non-linear interventions that break linear propagation at tipping points.
- **E — Constraint**: systemic safeguards — scale preservation, bounds, rate limits.

---

## 3. Propagation semantics & conflict resolution

### 3.1 How effects are actually applied (all additive at apply-time)

There is **no global `(V + Σadd) × Πmult` formula**. Every mutation reaches a variable as
an **additive delta** through `world.apply_delta`. "Multiplicative" shocks are converted to
their equivalent additive delta *at fire time* from the current value:

- `scale_var` (`core/threshold_rules`) returns `numeric_updates = {target: current·(factor−1)}`,
  so applying it additively yields `current·factor`.

The per-variable update inside `apply_delta` (`core/physics_core`) depends on behavior type:

- **STOCK:** $V_{t+1} = V_t\,(1-\text{decay}) + \Delta_{\text{eff}}\,(1-\text{inertia})$,
  where $\Delta_{\text{eff}}$ may be scaled by a saturation factor as $V$ nears `max`.
- **FLOW:** $V_{t+1} = V_t + \text{net}$ (direct additive).

`decay` for an unspecified large-magnitude variable is **0** (scale-aware, §3.3), so such
variables do not bleed toward a baseline.

### 3.2 Ordering & precedence (the real determinism guarantees)

- **Agent merge** is net-additive per variable (Phase 3).
- **Soft constraints run on the delta** (Phase 5), *before* physics — `rate_limit`,
  `change_budget`, diminishing returns, then hard clip.
- **Causal propagation runs before rules** (Phase 6 before 7): rules evaluate the
  *post-propagation* state. If a causal link pushes a variable past a threshold, the rule
  fires in the **same tick**.
- **Rule effects apply additively and are not re-clamped by specs** — `run_rules` calls
  `world.apply_delta` without `variable_specs`, so a deliberate cascade (e.g. an mrr cliff)
  lands at full magnitude. Use this intentionally for catastrophic shocks.
- **Spec clamping happens in two places**: on the *delta* in Phase 5 (`apply_hard_clip`,
  scale-aware) and on the *resulting state* for specced variables inside Phase 6
  (`clamp_state_to_specs`). Unspecified out-of-range variables are clamped at neither.

### 3.3 Scale-aware spec resolution (`_effective_spec`)

The single rule that prevents scale-blind corruption (the historical −99% mrr bug):

- Explicit `variable_specs[var]` → always used.
- No explicit spec, value within default $[0,100]$ → `DEFAULT_VARIABLE_SPEC`
  (`{min:0, max:100, rate_limit:10}`) — genuine normalized variables stay protected.
- No explicit spec, value **outside** $[0,100]$ → **unbounded** (no clip, no rate_limit;
  and `decay = 0`). A value like `mrr = 10000` is clearly on a different scale; clamping it
  to 100 would wipe it.

This same predicate governs clipping (`soft_constraints._effective_spec`) and STOCK decay
(`physics_core._get_spec_decay`). It is the load-bearing invariant of the runtime's
domain-agnosticism — **changing it requires re-validating every scenario.**

---

## 4. Time & stability model

Time is **discrete**: each tick is one `step()`. Compute per tick is bounded —
`O(agents + |causal_links|·max_hops + |rules|)` — with no unbounded recursion, so a tick
cannot hang on a resonant loop.

### 4.1 Propagation convergence (`core/propagation`)
Structural propagation is a bounded BFS/wave from the primary deltas. For hop distance $d$:
$$\Delta_d = \Delta_0 \cdot w \cdot (\text{decay\_factor})^{d}$$
Three independent brakes guarantee a cascade cannot explode:
- **Hop bound** — `max_hops` (default **3**).
- **Geometric decay** — `PROPAGATION_DECAY_FACTOR` (default `1.0`) compounded per hop,
  plus `PROPAGATION_DAMPING` (`0.6`).
- **Significance cutoff + epsilon** — contributions below `PROPAGATION_SIGNIFICANCE_THRESHOLD`
  are dropped; iteration stops at `PROPAGATION_EPSILON` (`1e-6`), capped at
  `PROPAGATION_MAX_ITER` (`5`). Each hop's contribution is also `rate_limit`-clamped.

### 4.2 Regime-aware physics (`core/regime_detector` + `loop.step`)
Each tick computes a regime from variable saturation and entropy growth:
`CRISIS` iff `percent_high > 0.3 AND entropy_growth > REGIME_ENTROPY_GROWTH_THRESHOLD`
(`0.5`); `FRAGILE` iff `percent_high > 0.15`; else `NORMAL`. In `CRISIS` the runtime
*hardens* physics to suppress runaway:
- `decay_factor → ×0.7` (propagation dies faster across the graph),
- per-variable STOCK `decay → ×1.5` and `inertia → +0.2` (state becomes more sluggish).

### 4.3 Entropy, SSI & surprise
- **World entropy** is tracked across turns; **SSI** (System Stability Index)
  `= exp(−α · normalized_entropy)`, `normalized_entropy = entropy / num_variables`.
- **Surprise analysis** flags deltas deviating from prediction beyond
  `DEVIATION_THRESHOLD` (`2.0`), feeding calibration. None of these mutate state — they are
  observability signals consumed by regime detection and the brief.

---

## 5. Regret & metrics layer (post-processing isolation)

**Architectural contract: the robustness/RDM layer never mutates engine state.** It is a
pure read-only post-processor over completed runs. This separation is what keeps the engine
domain-agnostic and the metrics swappable.

```
 engine (mutates)                      metrics (read-only)
 SimulationLoop.run() ──► RunResult ──► aggregate_robustness ──► report
                          (provenance)  compare_scenarios       (ordinal only)
```

- **`simulation/ensemble.run_ensemble`** spins up **N independent** `SimulationLoop`
  instances over perturbed scenario copies (`perturb_scenario`). Members are independent
  (fresh world/agents) and run sequentially (engine touches process-global state).
- **`goal_score`** is **scale-invariant**: per-goal-variable percent change normalized by
  the **base (unperturbed) initial value** — a constant across members — so perturbing a
  goal variable's start cannot create a spurious correlation in the pivotal step.
- **`simulation/robustness.aggregate_robustness`** derives: outcome distribution, variable
  spread bands, failure modes (worst-vs-best tercile contrast), divergence point, and the
  **pivotal assumption via Spearman** rank correlation (robust to monotone non-linearity).
- **`compare_scenarios`** emits the RDM trade-off: **maximin** (best worst-case),
  **expected value** (best median), **minimax-regret** (least regret under per-state
  alignment). No single "winner" is forced.

### 5.1 Honesty invariant
The layer **never emits an absolute probability**. Outputs are counts ("16 of 20 runs"),
spreads, and named patterns, each carrying `DISCLAIMER`. Calibrated confidence can only
come later, from the Decision Journal's recorded real outcomes (a separate data loop).

---

## 6. Determinism contract

**Guarantee:** identical `(scenario, base_seed, perturb_config)` ⇒ byte-identical ensemble.

The runtime draws randomness from **two isolated sources**, and both are pinned per member:
1. **Perturbation randomness** — a *local* `random.Random(base_seed + i)` for member $i$.
   Independent of global state; this is what makes perturbation reproducible and
   per-member distinct.
2. **Engine-internal randomness** — the loop uses the **global `random` module** (the
   `_ensure_minimum_delta` nudge, optional drift/shocks). `run_member` therefore calls
   `random.seed(base_seed + i)` (and `numpy.random.seed`) *before* running the loop, so the
   member's internal draws are deterministic too.

### 6.1 Regret alignment requirement
For a valid **per-state** regret matrix, member $i$ of every option must face the *same*
perturbation. The API enforces this by running all options with the **same `base_seed`**
(`/api/robustness`). If member counts differ across options, minimax-regret is **omitted**
with a note rather than computed incorrectly.

### 6.2 Single-run determinism
For non-ensemble runs, `RANDOM_SEED` (config / env) plus `ENABLE_UNCERTAINTY=False` and
`ENABLE_SHOCKS=False` yields a fully deterministic trajectory.

---

## 7. Engine failure modes (degenerate-state catalog)

The runtime actively detects and contains degenerate dynamics. Each entry: the failure,
the guard, and where it lives.

| Failure mode | Guard / behavior | Location |
|---|---|---|
| **Action oscillation** (agent flips `increase_X`↔`decrease_X`) | reduce that objective's weight by 40% | `_apply_oscillation_penalty` |
| **Frozen world** (all deltas ≈ 0) | inject one bounded liveliness nudge (≤0.5% of value, rate-limited) | `_ensure_minimum_delta` |
| **Scale-blind corruption** (unspecified large var clamped to 100 / 1%/turn decay) | scale-aware spec: out-of-range unspecified var → unbounded, no decay | `_effective_spec`, `_get_spec_decay` |
| **Runaway cascade** | hop bound + geometric decay + rate-limit clamp + CRISIS hardening | `core/propagation`, §4 |
| **Low-signal robustness** (no causal graph, or flat goal_score) | `low_signal=true` + reason; verdict marked weak | `aggregate_robustness` |
| **Fragility blindness** (linear-only world cannot break) | requires a non-linear `rule`; documented as an L3 gate | grammar §7.5, rules |
| **Invalid regret** (misaligned option ensembles) | omit minimax-regret with a note | `compare_scenarios` |
| **Silent rule skip** (unregistered `condition_key`/`effect_key`) | rule is skipped; Linter must catch as an error | `rule_engine`, grammar §7 |

> Design principle: degenerate states are **contained and surfaced**, never silently
> "fixed" into fake signal. A scenario that cannot produce a meaningful verdict says so
> (`low_signal`) rather than emitting confident noise.

---

## Appendix — Source map

| Concern | File |
|---|---|
| Tick orchestration | `simulation/loop.py` (`SimulationLoop.step`, `run`) |
| Delta merge / min-delta guard | `simulation/loop.py` (`_ensure_minimum_delta`) |
| Soft constraints / scale-aware specs | `core/soft_constraints.py` (`_effective_spec`) |
| Stock/flow physics + decay | `core/physics_core.py` (`_get_spec_decay`) |
| Structural propagation | `core/propagation.py` |
| Non-linear rules | `core/rule_engine.py`, `core/threshold_rules.py` |
| Regime detection | `core/regime_detector.py` |
| Perturbation / ensemble | `simulation/perturbation.py`, `simulation/ensemble.py` |
| Robustness / RDM | `simulation/robustness.py` |
| Scenario schema | `schemas/scenario_schema.py` |

