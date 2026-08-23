# Cafe cost-shock decision comparison — how to run it for a real cafe

This is the commercial wedge: one question, three responses, one model. The only thing this
track is testing is whether a small-business owner will provide real numbers and pay for a
consistent comparison of their options. It is **not** a test of the simulation engine; that
is a separate track (`docs/replays/`), and a sale does not validate it.

## What the customer gets

A self-contained HTML report, five screens:

1. **The decision** — the three responses side by side, the top-ranked one marked, a one-paragraph
   verdict in plain language.
2. **What happens** — cash in the bank over 90 days, one chart, one table.
3. **Trade-offs** — what each response gives up, read directly from the runs.
4. **What could change the result** — every uncertain assumption moved across a range; which
   ones change the answer; live controls to flip them.
5. **Evidence & assumptions** — where every number comes from, with the research cited.

Plus a "Try your business" panel at the end where the owner can enter their own eight figures
and watch the whole page re-run — in the room, on a laptop, without touching the model.

## Producing a report for a new cafe

### 1. Collect eight numbers

| Ask the owner | Field |
|---|---|
| Monthly sales, typical month | `monthly_revenue` |
| Orders (transactions) per day | `daily_orders` |
| Monthly ingredient / input cost — what they pay suppliers for what they sell | `monthly_cogs` |
| Monthly fixed costs — rent, wages, utilities, loan payments, everything that won't move in 90 days | `monthly_fixed_costs` |
| Cash in the business account today | `cash_on_hand` |
| The supplier increase they're facing, as a % of ingredient cost | `supplier_increase_pct` |
| Rough share of orders on items they could drop or reformulate | `low_margin_share_pct` |
| Business name | `name` |

A guess is fine for the last percentage — it is swept as an assumption. Everything else they
can read off their books in minutes. Do not ask for anything more; the whole pitch is that
eight numbers are enough.

### 2. Put them in a JSON file

```json
{
  "name": "Corner Bean",
  "monthly_revenue": 32000,
  "daily_orders": 140,
  "monthly_cogs": 11200,
  "monthly_fixed_costs": 20500,
  "cash_on_hand": 6000,
  "supplier_increase_pct": 40,
  "low_margin_share_pct": 30
}
```

### 3. Generate

```bash
python scripts/cafe_decision_report.py --inputs corner_bean.json --out reports/corner_bean
```

Takes about five minutes (it runs 486 simulations for the sensitivity grid). Produces:

- `reports/corner_bean/cafe_decision_report.html` — the thing you show or send
- `reports/corner_bean/cafe_decision_report.json` — every number, every assumption, and the
  reproducibility record (model hash, configuration fingerprint, per-world engine fingerprints)

Open the HTML in any browser. Add `?theme=light` to the URL for the print/projector version.

### 4. Before showing it, check three things

- The "Demo data" flag is **gone** from the top bar (it disappears when `is_demo` is false).
- The headline states *their* supplier increase.
- The evidence table lists *their* numbers as "Customer input".

## Changing an assumption for a customer who pushes back

They will. The usual one is "my customers are more loyal than that" or "my competitors will
raise prices too". Both are the same assumption — price sensitivity — and it is the one that
changes the answer.

- In the room: screen 4, first dropdown. Pick *Low* (loyal customers, competitors raising too)
  or *High* (competitors hold prices). The whole page re-runs on the precomputed grid.
- For the written report: rerun with a specific number. This applies the value in memory only;
  the model file is never edited, and the report labels the elasticity as the customer's value.

```bash
python scripts/cafe_decision_report.py --inputs corner_bean.json --out reports/corner_bean_loyal --custom-elasticity 0.5
```

The headline comparison then uses 0.5 and the evidence table shows it as the customer's own
value. The sensitivity grid still sweeps the three standard settings, so the "what could change
it" screen keeps its meaning.

If the owner has costed the items they would remove, override the reformulation saving too:

```bash
python scripts/cafe_decision_report.py --inputs corner_bean.json --out reports/corner_bean --reformulation-effectiveness 0.2
```

(points of average ingredient cost saved per point of low-margin share; default 0.30.)

Inside the page, the owner's eight numbers drive *everything*: the cards, the chart, and the
"ranked first in N of 162" census are all recomputed for their cafe, not the demo's.

## What is fixed, and why

| Fixed | Where |
|---|---|
| The three decisions: do nothing / +10% / +5% + trim | `event_sim/cafe/worlds.py` |
| The model: two behavioural edges, lags, ranges | `world_models/small_business/cafe_cost_shock_v1.json` |
| The horizon: 90 days | `worlds.py` |
| The sensitivity grid: 5 assumptions, 162 combinations | `event_sim/cafe/sensitivity.py` |
| The accounting identities | `event_sim/cafe/accounting.py` |

Two cafes are compared by the same instrument. If you change the model for one customer,
you no longer have a product; you have a consulting engagement. Don't.

## Language

Never say *predict*, *forecast*, *will happen*, *guaranteed*, *optimal*. Say *scenario*,
*comparison*, *under these assumptions*, *model-implied*, *relative difference*, *depends
mainly on*. The report's own copy is tested against the banned list.

## What is not built, on purpose

Accounts, billing, login, multi-tenancy, other scenarios, other industries, an LLM writing the
numbers. Expansion is gated on evidence of willingness to pay — see
[SALES_SCRIPT.md](SALES_SCRIPT.md) for what counts as evidence.

Small things that *would* be worth doing after the first real customer, not before:
a PDF export; a currency symbol on the report; a second shock size on the same page.
