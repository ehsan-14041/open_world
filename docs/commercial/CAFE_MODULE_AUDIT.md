# Cafe cost-shock module — design audit

> Audit performed before any production code, against the actual engine and schemas. The
> specification file named in the brief (`Cafe_Cost_Shock_Wedge.md`) does not exist in the
> repository, its history, or anywhere on this machine; the brief's own description of it —
> a proposed WorldModule and a price elasticity of `0.3–0.9` labelled `literature_backed` —
> was treated as the set of claims to audit.

## 1. What the engine can and cannot represent

Two properties of `event_sim/engine.py` decided the whole design.

**Every non-stock variable relaxes toward a linear pressure.**
`dev(t+1) = dev + response · (Σ coef·dev(source, t−lag) − dev)`. That is the right shape for
*behaviour* — customers adjusting to a price over weeks, purchasing passing a supplier
increase through as old stock runs out. It is the wrong shape for an *accounting identity*.
Gross margin is `revenue − COGS` by definition; modelling it as a variable that relaxes toward
a pressure would smear a definition across time and, with both revenue and COGS feeding it,
double-count the mechanism.

**The only stock rule is a capacity-bounded queue.** `processed = min(queue + arrivals,
capacity)`, floored at zero, with capacity read from another variable. Cash is an
*integrator* — `cash += net cash flow` — and it must be allowed to go negative, because that
is the insolvency signal. The queue rule cannot express it.

**Decision:** the module holds only the behavioural relationships, in index space. Revenue,
gross profit, margin and cash are computed by `event_sim/cafe/accounting.py` as identities
over the engine's trajectories. Both layers are deterministic and reproducible; the report
says which is which. **The engine was not modified.**

## 2. The audited chain

| Link in the brief | How it is represented | Audit finding |
|---|---|---|
| materials cost → COGS | edge `input_cost → cogs_per_order`, coefficient 1.0 central, lag 5–10 days, response 0.25/day | Correct: COGS per order rises to the new input level after about a week of old stock. Pass-through above 1.0 not modelled. Low setting 0.70 represents substitution/contracts. |
| COGS → margin | **not an edge** — `gross_profit = revenue − cogs` in accounting | A margin edge would double-count (COGS already lowers it by definition). Removed from the model by design. |
| menu price → demand | edge `menu_price → demand`, coefficient = elasticity magnitude, negative polarity, lag 0, demand response 0.05/day | Correct: demand settles at `100 − ε·Δprice` with a ~2-week half-life. Verified: B settles at 91.98 for ε = 0.81, Δprice = 10. |
| price / demand → revenue | **not an edge** — `revenue = orders × price` | Identity. Also where the index-vs-currency conversion lives: indices scale the customer's own baseline orders and average ticket. |
| margin / revenue → cash | **not an edge** — `cash(t) = cash(t−1) + gross_profit − fixed` | Identity; may go negative; reports the first negative day. |

### Specific checks from the brief

| Check | Result |
|---|---|
| Double counting | None. Each mechanism appears exactly once: two edges, and identities that reference engine output only. |
| Incorrect stock accumulation | No stocks in the module; cash accumulation is an explicit identity, floored nowhere. |
| Index vs currency confusion | All engine variables are indices (100 = pre-shock). Currency enters only in `accounting.py`, multiplied against the owner's baseline. |
| Interpretation of margin | Gross margin % = gross profit / revenue, computed daily; never a state. |
| Impossible units | Variable ranges: input cost 0–300, COGS 0–300, price 50–200, demand 0–200. Clamping never engaged in any run of the demo or the 162-point sweep. |
| Unintended edge interactions | `menu_price` has no incoming edges (it is a decision, not an outcome — tested). `input_cost` is held by the event. The two edges do not share endpoints. |
| Intervention semantics | Offsets add to the relaxed endogenous state each turn. For `menu_price` (endo = 0) the offset *is* the price. For `cogs_per_order`, the −6-point reformulation adds to the relaxed 130 → 124. For `demand`, the −2-point item-removal loss adds to the elasticity response. |
| Clipping | Not triggered. |
| Lag behaviour | COGS: flat to day 5, 113 at day 10, 125 at day 14, 130 by day 30. Demand: 97.9 at day 7, 93.9 at day 28, 92.0 at day 90. Both as intended. |
| World C's COGS intervention | Represents removing/reformulating items that make up a share of orders: COGS per order falls by `share × 0.30` points; orders fall by one third of that. Both constants are expert assumptions; the first is swept. |

## 3. Elasticity — the `0.3–0.9` claim

The brief reports the missing spec labelled restaurant price elasticity `literature_backed`
at `0.3–0.9` without a source. Checked against the sources themselves:

| Source | Level | Estimate |
|---|---|---|
| Andreyeva, Long & Brownell 2010, *AJPH* — systematic review, 160 US studies | **Category** ("food away from home") | **0.81**, 95% CI **0.56–1.07**, range 0.23–1.76, 13 estimates |
| Bijmolt, van Heerde & Pieters 2005, *JMR* — meta-analysis, 1,851 elasticities | **Brand / outlet** (mostly packaged goods) | mean **−2.62** |

**The `0.3–0.9` range is not justified.** The category CI alone reaches 1.07, and the
single-outlet case — a cafe raising prices while competitors hold theirs — faces substitution
the category estimate does not capture. The paper itself draws exactly this
category-vs-brand distinction.

**Range adopted:** low **0.50**, central **0.81** (literature), high **1.60** (expert
judgement, placed between the category CI top and the brand-level mean, discounted because an
independent cafe is differentiated by location and habit). The central setting is labelled
`literature_backed`; the high setting is labelled `expert_assumption`, and the report says so
when it is selected.

The transfer question is reframed as a question the owner can answer — *will your competitors
raise prices too?* — and that becomes the sensitivity axis. It turned out to be the only
assumption that changes the decision.

## 4. Engine limitations discovered

1. **No integrator stock.** Cash cannot be an engine variable. Handled by the accounting
   layer; documented, not patched.
2. **Axis settings are discrete.** A custom numeric elasticity cannot be expressed through an
   axis; `run.py` applies it to an in-memory copy of the slice and labels the result
   `user_assumption`. The module on disk is never modified (tested).
3. **Sweep cost.** 162 combinations × 3 worlds × 90 days takes ~2.5 minutes; the full report
   with the in-page grid ~5 minutes. Acceptable for a per-customer report; not for live
   re-simulation in a browser. The demo therefore precomputes the grid and does accounting in
   the page — every number on screen is still an engine output.

Nothing in the engine or in the existing port-disruption models was changed. Frozen hashes
`d4670fb1…` / `324a8bf1…` verify.
