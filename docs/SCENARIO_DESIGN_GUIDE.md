# Scenario Design Guide

**How to think a messy real-world decision into a scenario the engine can stress-test.**

The engine is only as good as the world you describe. This guide teaches the *thinking* —
how to turn "Should we raise prices 30%?" into a structured world with actors, feedback
loops, constraints, and failure modes — and how to avoid the input mistakes that quietly
produce confident-but-worthless robustness verdicts.

Prerequisite: [`SCENARIO_GRAMMAR.md`](./SCENARIO_GRAMMAR.md) defines the formal vocabulary
and the five elements. This guide is the *pedagogy* on top of it.

Three parts:
1. A systems-thinking framework for decomposing a decision.
2. The 4-level completeness ladder — how to climb from "it runs" to "ready for RDM".
3. The anti-pattern catalog (Scenario Smells) — how each one distorts the output.

---

## Part 1 — A mental framework: from a sentence to a system

A bad scenario is a sentence: *"Raise prices 30% to grow revenue."* A good scenario
answers six questions. Work them in order; each maps to a grammar element.

### Q1. What is the lever, and what variable does it move directly?
The **decision**. "Raise prices 30%" → moves `price` (+30%). One concrete, declared
variable. If your decision doesn't name a variable it moves, you have a wish, not a lever.
→ `allowed_actions` / `action_tradeoffs` / `decision_input`.

### Q2. Who is affected, and *who reacts*?
The **actors**. Not just you (the decider). Who else has goals that this disturbs?
- Customers (will they churn at the higher price?)
- Competitors (will they hold price and take your share?) ← *almost always forgotten*
- Regulators, suppliers, your own team.
Each becomes an `initial_agents` entry with its own `objectives`. The point of a
multi-agent simulation is to surface *their reactions* — if you only model yourself, a
single LLM prompt would do as well.

### Q3. What accumulates (Stocks) vs. what flows (Flows)?
- **Stocks** have memory and accumulate: `cash`, `customers`, `brand`, `capacity`,
  `market_share`. (`behavior_type: STOCK`.)
- **Flows** are per-period rates: `revenue`, `churn_rate`, `acquisition`, `utilization`.
  (`behavior_type: FLOW`.)
→ `initial_state` + `variable_specs`. Declare a spec for anything not on a 0–100 scale.

### Q4. How do they connect — and where is the loop?
The **causal links**. price → churn_rate → customers → mrr → cash. Then ask the systems
question: *does anything loop back?* (cash → hiring → capacity → acquisition → customers).
A world with no feedback loop is a slide, not a system.
→ `causal_links` with `from`/`to`/`polarity`/`strength`.

### Q5. What can run out? (the constraint)
Every real decision is bounded by something finite: `cash`, `runway`, `capacity`,
`inventory`. Name it. Without a constraint, the engine thinks growth is free and every
decision looks robust (see Smell: *Infinite Growth*).

### Q6. How does it break? (the failure mode)
What threshold turns a bad turn into a collapse? "If churn crosses 40%, revenue cascades."
This is a **non-linear rule** — and it is what lets the robustness engine distinguish a
*fragile* decision from a *robust* one. A purely linear world cannot break; it only drifts.
→ `rules` with `var_above` + `scale_var`.

> Answer Q1–Q3 → you have an **L1** scenario. Add Q4 → **L2**. Add Q2's rivals + Q5 + Q6
> + an alternative → **L3**. Calibrate the uncertainty → **L4**.

---

## Part 2 — The completeness ladder (climbing L1 → L4)

(Full predicates in `SCENARIO_GRAMMAR.md` §7.5. Here is how to *climb*.)

### L1 → L2: make the relationships sound
Symptoms of L1-only: a one-way fan-out (price → everything), variables on raw scales with
no spec, only the decider as an actor.
Do: add the **feedback loop** that closes the system; declare specs for `cash`/`mrr`/etc.;
add the customer as an actor.

> *Before:* price → churn → mrr. *After:* …→ mrr → cash → marketing → acquisition →
> customers → mrr. Now the decision has second-order consequences that return to it.

### L2 → L3: make it strategically complete
This is the leap from a *model* to a *war-game*. Add:
- the **second mover** (competitor reacts to your price),
- a **constraint** (runway can deplete),
- a **failure mode** (the churn cliff rule),
- at least **one alternative** ("hold price + cut cost") to compare.

> At L3 the decision can *lose*, others *push back*, and there is a real *choice* — the
> three things a chatbot answer cannot give you.

### L3 → L4: calibrate for robustness
Make sure the perturbation sweeps the coefficients you are **least sure of** (that's the
honest meaning of robustness — see grammar §7.5 L4). Set rule thresholds at
decision-relevant levels. Align options under one `base_seed` so the regret matrix is
per-state valid.

> Only an L4 scenario produces a trustworthy maximin / minimax-regret verdict. Below L4,
> read the war-room output as *directional*, not decisive.

---

## Part 3 — Scenario Smells (anti-patterns that distort RDM)

Each smell is a *plausible-looking* scenario that produces *misleading* robustness output.
For each: the symptom, **how it corrupts the verdict**, the fix, and which level/linter
rule catches it.

### 🔴 Single-Cause Thinking
**Symptom:** one cause drives everything; no competitor, no reaction, no feedback.
**Corrupts RDM:** nothing pushes back, so *every* option looks robust. The war-game has
no opponent — you're shadow-boxing. (This is the failure mode of most boardroom decks.)
**Fix:** add a reacting actor (competitor/regulator) and a feedback loop. → blocks **L3**.

### 🔴 Infinite Growth Assumption
**Symptom:** no constraint variable; no `max`/`soft_max`; growth links with no balancing
loop.
**Corrupts RDM:** `goal_score` grows unbounded; the engine never finds a failure; the
decision is reported "robust" because nothing can stop it — a dangerous false positive.
**Fix:** add a constraint variable (cash/capacity) and a saturation (`soft_max`+`softness`
or a balancing loop). → smell warning "Missing liquidity"; blocks **L3**.

### 🔴 Missing Failure Mode
**Symptom:** purely linear causal graph; no non-linear `rule`.
**Corrupts RDM:** *empirically proven in this project* — linear dynamics produce a smooth
gradient, not a bimodal outcome. The robustness engine cannot separate *fragile* from
*robust*; the regime label may flip but `goal_score` just drifts. The "is this safe?"
question becomes unanswerable.
**Fix:** add a threshold rule (`var_above` → `scale_var`) at the real breaking point.
→ blocks **L3**.

### 🟠 No Constraint Variable
**Symptom:** no `cash`/`runway`/`capacity` — nothing finite.
**Corrupts RDM:** decisions appear free; trade-offs disappear; maximin is meaningless
(there is no "worst case" if nothing can be exhausted).
**Fix:** add the binding constraint for this decision. → smell warning; blocks **L3**.

### 🟠 Scale Blindness
**Symptom:** a large-magnitude variable (mrr=50000) with no `variable_specs` entry.
**Corrupts RDM:** historically wiped the variable to the default cap of 100 (a −99% delta)
and injected a common-mode trend that masked the real signal. (Fixed in the engine, but
still a smell — you're trusting defaults on a variable you should own.)
**Fix:** declare the spec with the right scale and `behavior_type`. → smell warning;
blocks **L2**.

### 🟠 No Feedback Loop (DAG-only)
**Symptom:** the causal graph is a pure DAG.
**Corrupts RDM:** the consequence map is suspiciously clean — no reinforcing spirals, no
balancing. Second-order effects are understated.
**Fix:** find the one link that closes a loop. → blocks **L2**.

### 🟡 Misplaced Uncertainty
**Symptom:** perturbation sweeps coefficients you're *confident* about and leaves the
*uncertain* ones fixed.
**Corrupts RDM:** the robustness verdict reflects irrelevant noise instead of your real
ignorance; the pivotal-assumption callout points at the wrong thing.
**Fix:** sweep the assumptions you'd least defend in a board meeting. → blocks **L4**.

### 🟡 Probability Theater
**Symptom:** expecting / reporting "73% chance of success".
**Corrupts RDM:** an absolute probability from an uncalibrated model is a prior dressed as
a frequency — false precision that drives real money. The engine deliberately never emits
one.
**Fix:** read the output as ordinal — "robust in 16 of 20 runs under swept assumptions",
"hinges on churn→stability". Confidence becomes real only via the Decision Journal's
recorded outcomes over time.

---

## Quick checklist before you hit "War-room"

- [ ] The decision names a variable it moves (L1)
- [ ] At least one actor *other than the decider* has objectives (L1)
- [ ] There is a feedback loop in the causal graph (L2)
- [ ] Large-scale variables have explicit specs (L2)
- [ ] A competitor / external reactor is modeled (L3)
- [ ] A constraint variable can run out (L3)
- [ ] A threshold rule defines how it breaks (L3)
- [ ] There is at least one alternative to compare (L3)
- [ ] Perturbation sweeps your *least certain* coefficients (L4)

Hit L3 before trusting the trade-off matrix; hit L4 before quoting maximin / regret.
