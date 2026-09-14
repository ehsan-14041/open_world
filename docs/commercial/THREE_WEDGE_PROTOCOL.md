# Three wedges: the first-customer protocol

> **Superseded for the customer-validation phase by [`docs/pilot/`](../pilot/README.md).** Kept for history. Two statements below have been corrected: a payment is evidence of willingness to pay, not validation of the model; and the price is set by the project owner before sessions — the $99 figure was a placeholder, never a tested price.

Three decision products, one instrument:

| | Business | The decision being compared | Where the answer hinges |
|---|---|---|---|
| ☕ | Cafe / Restaurant | Ingredient costs jumped: hold, +10%, or +5% and simplify the menu | How price-sensitive customers are |
| 🛍 | Shop / Online Store | Supplier raised prices: hold, +8%, or +4% and drop low-margin lines | How much dropping those lines really saves, and price sensitivity |
| ✂ | Salon / Service | The diary is filling up: hold, +10%, or +5% and shift the mix | Nothing we tested changes it — see below |

The purpose of this round is to find out whether a small-business owner will hand over real
figures and pay for a comparison. It is **not** a test of the simulation engine. A sale does
not validate the engine, and a failed engine benchmark does not invalidate the product.

## Scale of the experiment

**Three free reports per wedge. Nine interviews, maximum.** Then stop and read the results
before building anything else. Do not add a fourth business type during this round, however
easy it looks — three is already enough to tell whether the architecture generalises, and a
fourth would only delay the answer to the commercial question.

## Before you show anything

Record all three, in the owner's own words, **before** they see a single number:

1. **The decision they are actually facing** in the next 60 days.
2. **What they currently think they will do**, and why.
3. **What they are unsure about.**

The third one is the most valuable thing you will collect. If the report's "biggest unknown"
matches what they already told you they were unsure about, the product is speaking to a real
question. If it does not, that is a finding — write it down rather than explaining it away.

## Collecting the numbers

Each wedge asks for eight or nine figures an owner can read off their own books in a couple of
minutes. Note which ones they had to guess at.

```bash
python scripts/wedge_report.py cafe  --inputs their_cafe.json  --out reports/their_cafe
python scripts/wedge_report.py shop  --inputs their_shop.json  --out reports/their_shop
python scripts/wedge_report.py salon --inputs their_salon.json --out reports/their_salon
```

A few minutes each: the full sweep is 162 combinations run against three decisions.

Before showing it, check three things:

- the **Demo** flag is gone from the top bar;
- the headline states **their** shock, not the demo's;
- the sensitivity count was recomputed on their figures (it will rarely be the demo's count).

## Showing it

Follow the page top to bottom. It is built in the order a decision gets made, not the order the
work was done: the decision, then the money, then the trade-off, then the uncertainty, and only
then the method.

Read the **"What this does not do"** list aloud. Every time.

**On the salon report, say the awkward thing plainly.** Raising prices ranked first in all 162
combinations tested, and two of the three options never rank first anywhere. That is a real
result, not a bug — when the diary is already full and products are a small share of revenue,
price is the dominant lever, and appointments lost to a price rise were partly being turned
away anyway. But it also means this report does not identify a hinge, and the honest framing is:
*"nothing we tested changes this answer; what would change it is if your clients are far more
price-sensitive than any setting we consider plausible — and for salons there is no published
figure at all, so your own price test is worth more here than in any other trade."*

## After showing it — record every one

| Question | Answer |
|---|---|
| Did the report show them anything they did not already know? | what |
| Did it change what they intend to do? | how |
| Did it name an uncertainty they agreed mattered? | which |
| Did they challenge an assumption? | which one, and what did they say the number should be |
| Did they ask for a rerun? | what changed |
| Would they pay [the price set by the project owner]? | yes / no / maybe |
| Would they use it for another decision? | which decision |
| Would they recommend it to another owner? | yes / no |
| Their strongest objection, verbatim | |

## Two rules that protect the experiment

**Do not modify a model after customer 1 to make customer 2 happier.** Every owner of the same
business type sees the same instrument. If the model changes between customers you no longer
have a product, you have a consulting engagement — and you cannot compare the two interviews.

**Keep product feedback separate from calibration claims.** "The chart is confusing" is product
feedback: act on it. "My customers are far less price-sensitive than that" is a calibration
claim: record it, rerun it for them as a custom value, and do not change the default.

```bash
python scripts/wedge_report.py shop --inputs their_shop.json --custom-elasticity 0.8 \
    --out reports/their_shop_loyal
```

The report then labels that elasticity as **the customer's own value**, and the sweep still
tests the standard range, so the "what could change the answer" screen keeps its meaning.

## What counts as evidence

| Level | Signal | Worth |
|---|---|---|
| 0 | "Looks cool" | Almost nothing |
| 1 | Gives real operational figures | Meaningful |
| 2 | Names a real decision in the next 60 days | Strong |
| 3 | Challenges an assumption or asks for a rerun | Very strong |
| 4 | Pays | Willingness-to-pay evidence (not validation of the model) |

Compliments about the chart are level 0. So is any praise for the technology.

## The provisional bar

Across nine demonstrations: **at least three reach level 1, at least two reach level 3, at
least one reaches level 4.**

Read it per wedge as well as overall. Three wedges exist precisely so you can find out whether
demand is uneven — if the cafe lands and the salon does not, that is far more useful than a
single blended number.

## Things not to say

- *predict*, *forecast*, *guaranteed*, *optimal*, *probability*, *confidence*, *AI recommends*
  — the reports avoid all of them and so must you.
- *"There is a 73% chance B is best."* The count is a census over a grid of cases, not a
  probability. Saying it the wrong way once undoes the whole discipline of the report.
- Anything about the engine's scientific validation. Different track.

## After each demo, write down

Name, business type, date, the figures given, the decision they named, what they said they
would do beforehand, what they said afterwards, what they challenged, price quoted, price paid,
and their strongest objection word for word.
