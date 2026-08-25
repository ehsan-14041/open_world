# Three wedges — how the product is put together

One instrument, three businesses. Everything that runs a comparison is shared; a wedge only
declares what makes it that business.

```
event_sim/wedge/          shared machinery — no business vocabulary in here
  spec.py                 the whole contract a wedge must declare
  accounting.py           the identities: revenue, gross profit, cash, capacity
  compare.py              one slice, one config, three runs + fingerprints
  sensitivity.py          the census over a finite grid
  evidence.py             the four customer-facing evidence classes and the sources
  report.py               the bundle the page reads
  registry.py             the three wedges and the chooser
  templates/chooser.html  "What kind of business do you run?"

event_sim/cafe|shop|salon/
  baseline.py             that business's intake fields and demo figures
  worlds.py               the shock and the three decisions
  evidence.py             the assumption registry
  wedge.py                the WedgeSpec: everything above plus the page's wording

world_models/small_business/
  cafe_cost_shock_v1.json         4 variables, 2 edges
  shop_cost_shock_v1.json         4 variables, 2 edges
  salon_capacity_pricing_v1.json  4 variables, 2 edges
```

If a new wedge needs the shared code to grow a special case, that is a signal the wedge does
not fit the engine — not a signal to add a flag.

## Generating

```bash
python scripts/wedge_report.py --all          # the three demos
python scripts/build_demo_site.py             # chooser + the three reports
```

For a real business: `python scripts/wedge_report.py shop --inputs their_shop.json --out reports/their_shop`

A few minutes each — 162 assumption combinations run against three decisions.

## The engine / accounting boundary

The engine carries **only** behaviour: how a cost shock reaches unit cost through an inventory
delay, and how demand responds to price through an elasticity. Everything downstream of that is
arithmetic, and lives in `wedge/accounting.py`:

    revenue      = units × price
    unit cost    = units × cost each × index/100
    gross profit = revenue − unit cost
    cash(t)      = cash(t−1) + gross profit − fixed costs per day
    served       = min(wanted, slots available)          ← salon only

None of these is a causal claim, and none of them belongs in a module. Cash in particular must
be free to go negative — that is the insolvency signal an owner cares about, and the engine's
one stock rule is a capacity-bounded queue floored at zero, which cannot represent it.

The capacity clip is in the same category: a business cannot serve appointments it has no slots
for. That is a fact about slots, not a behaviour to simulate. Keeping it in the accounting layer
also keeps the salon module acyclic — price moves demand, and nothing feeds back.

## One trap worth knowing about

**An event HOLDS its target variable, discarding the relaxation term.** So any edge pointing at
a variable an event targets is silently switched off.

The salon's demand increase was originally injected straight into `appointment_demand`, the
same variable the price elasticity feeds. Every option then showed identical demand, and the
elasticity did nothing at all — a bug visible only by reading the output, because nothing
errored. Shocks now land on an exogenous driver (`market_demand`, `input_cost`,
`supplier_cost`) which reaches the endogenous variable through an edge.

`test_no_event_target_is_also_an_edge_target` enforces this for every wedge.

## Fingerprints, and one caveat

Each report records three:

| | What it covers | Stable across repository states? |
|---|---|---|
| `module_semantic_hash` | the world module | yes |
| `shared_fingerprint` | variables, edges, axes, config — what the three worlds must share | yes |
| `engine_fingerprint` | the engine's own hash of the whole slice + events + interventions | **no** |
| `trajectory_fingerprint` | the same, minus registry-dependent fields | yes |

`EventSimulation.fingerprint()` hashes the whole slice dict, which contains
`excluded_systems` — a list of every *other* module in the repository. Adding the shop and
salon modules therefore changed the cafe's engine fingerprints while leaving its coefficients,
lags, events, interventions and every output identical. That was verified directly: with the
two new module files temporarily moved out of the tree, the cafe's engine fingerprints match
its original audit exactly.

The engine was deliberately not modified — it is frozen scientific infrastructure, and its
behaviour errs in the safe direction (it can report a difference that is not there; it cannot
report an equivalence that is not there). `trajectory_fingerprint` is the companion figure that
is stable across repository states, and it is what the regression test pins.

## What is fixed, and why

| Fixed | Where |
|---|---|
| The three decisions per wedge | `<wedge>/worlds.py`, as named constants |
| The models: variables, edges, lags, ranges | `world_models/small_business/*.json` |
| The horizon: 90 days | `<wedge>/worlds.py` |
| The sweep: 5 assumptions, 162 combinations | `<wedge>/wedge.py` |
| The accounting identities | `wedge/accounting.py` |

Two businesses of the same type are compared by the same instrument. Change a model for one
customer and you no longer have a product; you have a consulting engagement.

## Language

Never *predict*, *forecast*, *guaranteed*, *optimal*, *probability*, *confidence*. Say
*compare*, *scenario*, *under these assumptions*, *ranked first*, *tested cases*, *trade-off*,
*biggest unknown*. The count is a census over a grid — **never** a probability.
`test_no_customer_facing_copy_predicts_or_gives_odds` checks every wedge's copy, and it
distinguishes a claim from a denial so the disclaimers survive.

## What is deliberately not built

A fourth wedge. Billing, accounts, dashboards, SaaS infrastructure. Competitor reactions,
advertising, marketplace ranking, macroeconomic conditions — all outside what this engine can
honestly represent. Three wedges is enough to answer whether the architecture generalises, and
the commercial question is still open: see [THREE_WEDGE_PROTOCOL.md](THREE_WEDGE_PROTOCOL.md).
