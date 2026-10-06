# Scenario Grammar

**The formal contract between a user's intent and the simulation engine.**

This is the most important document in the project, because the engine's biggest
risk is not the math — it is **Garbage In, Garbage Out**. The best Robust Decision
Making engine in the world produces worthless output from a malformed scenario. This
grammar defines what a *valid, well-formed* scenario is, grounds every concept in the
**actual engine schema** (not an aspirational one), and enumerates the validity rules
that the Scenario Intelligence Layer (the "linter", Phase 2) will enforce.

> Rule zero: this document and the engine schema must never diverge. Every element
> below names the real field the engine consumes. If you change the schema, change
> this file in the same commit.

---

## 1. The five elements of a scenario

A scenario is a JSON object. The engine (`simulation/loop.py` → `SimulationLoop`)
consumes it after `schemas/scenario_schema.normalize_scenario`. The five grammatical
elements and the real fields they map to:

| Grammar element | Engine field | Shape |
|---|---|---|
| **Actors** | `initial_agents` | `[{name, role, objectives:{var:weight}, long_term_goals?}]` |
| **Variables** (Stocks & Flows) | `initial_state` + `variable_specs` | `{var: value}` + `{var:{min,max,behavior_type,inertia,decay,rate_limit}}` |
| **Causal links** | `causal_links` | `[{from, to, polarity:"positive"\|"negative", strength:0..1}]` |
| **Decisions** (levers) | `allowed_actions` / `action_tradeoffs` / `decision_input` | see §5 |
| **Shocks & Rules** (non-linearity) | `rules` + `events` | `[{id, condition_key, effect_key, params}]` |

The reference implementation of this grammar is the **operations vertical**:
`schemas/ops_schema.py` (user-facing profile) → `adapters/ops_scenario_builder.py`
(`build_scenario` assembles all five elements) → `config/ops_decisions.json` (decision
templates). Read those three files to see the grammar applied end to end.

---

## 2. Actors  →  `initial_agents`

An actor is a goal-driven entity that acts each turn. The engine extracts agents via
`agents.agents.get_agents_from_scenario`.

```json
"initial_agents": [
  {"name": "founder", "role": "Founder",
   "objectives": {"mrr": 0.6, "customers": 0.4},
   "long_term_goals": ["sustainable_growth"]}
]
```

- `objectives` is a **dict** `{variable_or_goal: weight}`. A raw variable name (`"mrr"`)
  maps to *maximize that variable*; prefix forms work too (`increase_X`, `decrease_X`,
  `minimize_X`) via `core.legacy_semantics.legacy_goal_to_var_direction`.
- Weights drive the agent's utility and the `goal_score` used by the robustness engine.
  **If no actor has objectives referencing real variables, `goal_score` is always 0** and
  the whole robustness analysis is blind.

Recommended actor archetypes for business scenarios (each should be a separate agent so
the simulation can surface their *interaction*, the war-gaming value):

- **Company** (founder / operator) — the decision-maker
- **Customer** — demand, churn, price sensitivity
- **Competitor** — the second mover; *the most commonly forgotten actor*
- **Regulator** — constraints, compliance shocks
- **Supplier** — capacity, lead time, cost

---

## 3. Variables — Stocks & Flows  →  `initial_state` + `variable_specs`

Every quantity in the world is a variable. Its starting value lives in `initial_state`;
its *behavior* lives in `variable_specs`.

```json
"initial_state": {"cash": 1200000, "mrr": 50000, "churn_rate": 0.15, "fill_rate": 0.92},
"variable_specs": {
  "cash":       {"min": 0, "behavior_type": "STOCK"},
  "mrr":        {"min": 0, "behavior_type": "STOCK", "inertia": 0.2},
  "churn_rate": {"min": 0, "max": 0.5, "behavior_type": "FLOW"},
  "fill_rate":  {"min": 0, "max": 1,  "behavior_type": "FLOW"}
}
```

**STOCK vs FLOW** (`core/physics_core.py`):
- **STOCK** accumulates and has memory: `Stock(t+1) = Stock(t)·(1−decay) + inflow·(1−inertia)`.
  Use for levels: cash, inventory, headcount, brand, market share.
- **FLOW** is a rate applied directly (additive). Use for per-period quantities:
  revenue, churn rate, fill rate, utilization.

`variable_specs` keys: `min`, `max`, `clip`, `rate_limit` (max change/turn),
`behavior_type` (`STOCK`|`FLOW`), `inertia` (0..1), `decay` (0..1), `soft_max`+`softness`
(diminishing returns).

### ⚠ The scale rule (hard-won — see CHANGELOG / `core/soft_constraints.py`)

The engine historically assumed **every variable lives in [0, 100]**. Unspecified
variables got a default `{min:0, max:100, rate_limit:10}` plus a 1%/turn STOCK decay.
This silently **wiped large-scale variables** (an unspecified `mrr=10000` was clamped to
100 — a −9900 delta — on a *no-op* turn).

This is now **scale-aware**: a variable with no explicit spec whose value is outside
[0,100] is left unbounded and un-decayed (`_effective_spec`, `_get_spec_decay`). But
relying on that is a smell. **Best practice: declare an explicit `variable_specs` entry
for any variable not on a normalized 0–100 scale** (cash, mrr, headcount, …). The linter
(§7) will warn when a large-magnitude variable has no spec.

---

## 4. Causal links  →  `causal_links`

The structural graph the engine propagates deltas along
(`core/propagation.py` → `propagate_variable_changes_from_state`).

```json
"causal_links": [
  {"from": "price", "to": "churn_rate", "polarity": "positive", "strength": 0.5},
  {"from": "churn_rate", "to": "customers", "polarity": "negative", "strength": 0.7},
  {"from": "customers", "to": "mrr", "polarity": "positive", "strength": 0.8}
]
```

- Use **`from`/`to`** (NOT `source`/`target` — those are silently dropped by
  `_structural_causal_links`).
- Direction via `polarity` (`positive`/`negative`) + `strength` (0..1), or an explicit
  signed `weight`.
- Propagation is **delta-based**: a link only fires when its `from` variable receives a
  delta this turn. A static variable propagates nothing.
- Propagation is **linear with saturation/decay**. Linear chains produce smooth
  gradients, *not* tipping points. Phase transitions require Rules (§6).

> **Relations ≠ causal links.** `relations` (e.g. `founder reports_to investor`) is
> organizational structure between *actors*. It does NOT drive variable propagation.
> Only `causal_links` does.

---

## 5. Decisions — the levers  →  `allowed_actions` / `action_tradeoffs` / `decision_input`

A decision is what the user is evaluating. Three ways to express it, in order of power:

1. **Variable-driven actions** — `allowed_actions: ["increase_price", "decrease_price",
   "steady"]`. `increase_X`/`decrease_X` auto-derive a ±`DEFAULT_VARIABLE_ACTION_MAGNITUDE`
   (5.0) delta on `X` (`agents/base_agent.rule_based_deltas_for_snapshot`). `steady` is a
   genuine no-op (≈ zero delta).
2. **Custom action effects** — `action_tradeoffs: {"raise_price": {"price": 30, "churn_rate": 0.08}}`
   defines the exact multi-variable delta an action applies.
3. **Structured decision input** — `decision_input: {move, actors, constraints,
   horizon_months}` (`schemas/decision_schema.py`), or an ops decision template
   (`config/ops_decisions.json`) whose `tradeoff_hint` *is* the lever's delta.

A decision **must** move at least one declared variable. "Increase sales 50%" with no
lever variable, no cost, no actor reaction is not a scenario — it is a wish (see §7).

---

## 6. Shocks & Rules — non-linearity  →  `rules` (+ `events`)

Linear propagation cannot model a cliff. Tipping points, cascades, and external shocks
are expressed as **rules** evaluated each turn (`core/rule_engine.run_rules`) using the
generic threshold primitives (`core/threshold_rules.py`):

```json
"rules": [
  {"id": "churn_cliff",
   "condition_key": "var_above", "effect_key": "scale_var",
   "params": {"var": "churn_rate", "threshold": 0.45, "target": "mrr", "factor": 0.6}}
]
```

Registered primitives:
- Conditions: `var_above`, `var_below` — params `{var, threshold}` (`core/threshold_rules.py`).
- Effects: `scale_var` (`{target, factor}` — multiplicative shock / cascade),
  `add_to_var` (`{target, amount}` — additive shock).

**Market dynamics (Phase 4, `core/market_dynamics.py`)** add time-based and stochastic
shock conditions (effects are the same `scale_var`/`add_to_var`):
- `at_turn` — params `{turn}` — fires once on that turn (a one-time shock).
- `after_turn` — params `{turn}` — fires every turn ≥ turn (a sustained regime).
- `with_probability` — params `{p}` — fires stochastically (seeded per ensemble member,
  so reproducible).

Builders emit the rule dicts so authors don't hand-write them: `supply_shock(turn, target,
factor)`, `demand_shock(turn, target, amount)`, `probabilistic_shock(p, target, factor)`,
and `contagion_cascade(chain, threshold, factor)` (a failure spreading through coupled
variables). **Network effects** are simply reinforcing causal-link cycles (rewarded at
L2); **contagion** is their non-linear, threshold-triggered counterpart.

`condition_key`/`effect_key` must be **registered** (unregistered keys are silently
skipped — there is no expression parser; you cannot write `"churn > 0.45"` as a string).
External shocks (recession, new competitor, supply crisis, regulation) are modeled as
rules whose condition fires on a turn/threshold and whose effect perturbs the relevant
variables.

---

## 7. Validity rules (the seed of the Scenario Intelligence Layer)

These become the linter in Phase 2. **Errors** make a scenario invalid; **warnings**
flag likely GIGO.

### Errors (block the run)
- A `causal_links` entry references a `from`/`to` variable not present in `initial_state`.
- An actor `objectives` key references a variable that does not exist.
- No actor has objectives referencing any real variable → `goal_score` would be 0.
- A `rules` entry uses an unregistered `condition_key`/`effect_key`.
- A decision/lever moves no declared variable.

### Warnings (likely garbage-in)
- **Missing competitor / external actor** — "You modeled price and demand, but no
  competitor reaction." (The classic blind spot.)
- **No feedback loop** — the causal graph is a pure DAG with no cycle; real economies
  have loops (churn→revenue→runway→hiring→…).
- **Missing liquidity** — no cash / runway variable in a business decision.
- **Large-magnitude variable without a spec** — e.g. `mrr=50000` with no `variable_specs`
  entry (relies on scale-aware defaults; declare it).
- **Shock declared but inert** — a rule/event exists but its effect targets nothing, or
  its `target` variable has no downstream causal link.
- **Trust / brand absent** in a market where it is typically pivotal.
- **Dangling causal link** — `to` variable has no spec and no further downstream effect.

The linter should run **without executing the simulation** — it is pure structural and
referential analysis over the scenario JSON plus the variable graph.

---

## 7.5 Scenario Completeness Levels (maturity model)

Validity (§7) is binary: does it run? **Completeness** is a *gradient* of strategic
depth. The linter reports the highest level a scenario satisfies, so the product can
coach ("valid, but L2 — add the second mover and a constraint to reach L3") instead of
only saying "wrong". Each level is a **computable predicate** over the scenario JSON —
no simulation required — and maps directly to a Scenario-Builder wizard step (Phase 4).

A scenario's level is the highest N for which all checks ≤ N pass.

### L1 — Structurally Valid *(it runs)*
All §7 **errors** clear:
- `initial_state` non-empty; every `causal_links` `from`/`to` is a declared variable.
- ≥1 actor whose `objectives` reference a real variable (else `goal_score` ≡ 0).
- Every `rules` entry uses a registered `condition_key`/`effect_key`.
- The decision/lever moves ≥1 declared variable.
> The engine can execute it and produce a `goal_score`. Syntactic correctness only.

### L2 — Causally Coherent *(relationships are sound)*
L1 **plus**:
- The causal graph contains ≥1 **feedback loop** (a cycle). Pure DAGs miss the
  reinforcing/balancing dynamics that make a simulation worth running.
- No **dangling links** (every `to` either has a downstream link or is an actor objective).
- Every non-normalized variable (|value| > 100) has an explicit `variable_specs` entry
  (scale-safe — no reliance on defaults).
- Actors include the parties the decision actually affects (not just the decider).
> The consequence map is meaningful, not a one-way fan-out.

### L3 — Strategically Complete *(multi-dimensional)*
L2 **plus**:
- A **second mover** is modeled — a `competitor`/`regulator`/`supplier` actor *or* an
  external `rule`/event that reacts. (Defeats Single-Cause Thinking.)
- ≥1 **constraint/limit variable** (cash, runway, capacity) — something that can run out.
- ≥1 **non-linear rule** (a tipping point / failure mode), so the scenario can actually
  *break*, not just drift. (Defeats Missing-Failure-Mode.)
- ≥1 **alternative option** to compare against (for the RDM trade-off matrix).
> The war-gaming is real: the decision can fail, others react, and there is a choice.

### L4 — Robustness-Ready *(calibrated for RDM)*
L3 **plus**:
- The **uncertain coefficients are the swept ones** — the assumptions you are least sure
  of (causal `strength`, key initial values) are the ones perturbation targets, so the
  robustness verdict reflects *your* uncertainty, not arbitrary noise.
- **Failure thresholds are explicit** (rule `threshold`s set at decision-relevant levels).
- Options are **comparison-aligned** (same variable space, runnable under one `base_seed`),
  so the regret matrix is per-state valid.
> Ready for the full N-run RDM war-room with trustworthy maximin / regret output.

| Level | Question it answers | Wizard step |
|---|---|---|
| L1 | Does it run? | Build structure |
| L2 | Are the relationships sound? | Wire feedback loops |
| L3 | Is it strategically complete? | Add rivals, limits, failure modes, options |
| L4 | Is it ready for robustness? | Calibrate uncertainty & thresholds |

---

## 8. A minimal valid scenario (copy-paste runnable, dry-run)

```json
{
  "description": "B2B SaaS: should we raise prices 30%?",
  "initial_state": {"price": 100, "churn_rate": 0.15, "customers": 500, "mrr": 50000, "cash": 1200000},
  "variable_specs": {
    "price":      {"min": 0, "behavior_type": "FLOW"},
    "churn_rate": {"min": 0, "max": 0.5, "behavior_type": "FLOW"},
    "customers":  {"min": 0, "behavior_type": "STOCK", "inertia": 0.2},
    "mrr":        {"min": 0, "behavior_type": "STOCK"},
    "cash":       {"min": 0, "behavior_type": "STOCK"}
  },
  "initial_agents": [
    {"name": "founder", "role": "Founder", "objectives": {"mrr": 0.6, "cash": 0.4}},
    {"name": "customers", "role": "Customer", "objectives": {"churn_rate": -1.0}},
    {"name": "competitor", "role": "Competitor", "objectives": {"customers": 1.0}}
  ],
  "causal_links": [
    {"from": "price", "to": "churn_rate", "polarity": "positive", "strength": 0.5},
    {"from": "churn_rate", "to": "customers", "polarity": "negative", "strength": 0.7},
    {"from": "customers", "to": "mrr", "polarity": "positive", "strength": 0.8},
    {"from": "mrr", "to": "cash", "polarity": "positive", "strength": 0.6}
  ],
  "allowed_actions": ["increase_price", "decrease_price", "steady"],
  "rules": [
    {"id": "churn_cliff", "condition_key": "var_above", "effect_key": "scale_var",
     "params": {"var": "churn_rate", "threshold": 0.40, "target": "mrr", "factor": 0.7}}
  ]
}
```

This scenario passes the validity rules: every link references a declared variable, three
actors (incl. competitor) with real objectives, a feedback loop (price→churn→customers→
mrr→cash), liquidity present, specced variables, and a non-linear tipping point.

---

## 9. How the grammar feeds the roadmap

1. **This document** — the formal language (done).
2. **Scenario Design Guide** — teaches users to *write* this language well (business
   framing, choosing actors/levers, avoiding the §7 smells).
3. **Architecture Guide** — explains how the engine *executes* this language
   (Agent → Loop → Soft Constraints → Physics → Propagation → Rules → Robustness).
4. **Scenario Intelligence Layer** — turns §7 into an automated linter / assistant that
   validates input, finds contradictions, and suggests missing variables and actors.

Once this grammar exists, the linter (Phase 4) almost writes itself: each validity rule
in §7 is one check over the scenario JSON.
