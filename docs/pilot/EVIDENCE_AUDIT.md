# Evidence and assumption audit — café pricing pilot

Audited 2026-09-11 against the code, the generated reports, the model files and the published
sources, before the customer-validation pilot. It separates five questions that are easy to
blur: *does the software do what it says*, *do its implementations agree*, *is the model right
about cafés*, *do owners understand and use it*, and *will anyone pay*.

---

## 1. Evidence inventory

| # | Claim | Supporting evidence | Limitation | Still unknown |
|---|---|---|---|---|
| 1 | The software computes what its model and inputs imply, deterministically and reproducibly | Deterministic engine with no randomness; engine and trajectory fingerprints on every run; ~1,400 automated tests; every report regenerates with identical figures | Shows the code matches its own specification — nothing about the world | — |
| 2 | Python, PHP and browser give the same figures | `scripts/verify_php_port.py`: worst difference **0.0** at all 162 grid points, all three trades; the page's own engine rebuilds all **486** precomputed cases before it may run an owner's option (worst disagreement 0.001 on a 100-based index, the last rounded digit); the browser census now counts what the report counts (§4); for an owner's own inputs, the page's figures now equal the Python pipeline's (five custom owners checked, all within rounding; census counts identical) | Agreement between three copies of the **same model**. It cannot show the model is right | — |
| 3 | The café model describes how cafés respond to price and cost changes | **One** coefficient setting is published: the central price sensitivity 0.81 (Andreyeva et al. 2010, §2) — a *category-level* US estimate for eating out, from studies up to 2007. Every other number is our assumption (§3) | Nothing in the model has been compared with any café's actual results. The published figure is for a market-wide price change, not one café raising while competitors hold | Whether the model's comparisons match real café outcomes |
| 4 | Shop and salon models describe those trades | Shop: only the **high** setting (2.60) is a published figure, and it is brand-level. Salon: **no** published elasticity at all | Same as row 3, weaker | Same as row 3 |
| 5 | Owners understand the comparison and find it useful | **None yet.** No owner session has been run | — | Everything; this is what the pilot tests |
| 6 | Owners will pay for it | **None.** No offer has been made, no payment taken. The "$99" in older documents was a placeholder, never tested | — | Everything |
| 7 | Validation from the port-disruption work applies here | **It does not.** Those replays test a different model in a different domain, with mixed results. Nothing about cafés follows from them | — | — |

**A correction.** An earlier project summary said, in effect, that "the engine works wherever
data exists". That overstates it. The accurate statement is:

> The engine computes, consistently and reproducibly, what follows from a model's stated
> structure and inputs. Where outcome data exists, a model can be tested against it. The port
> model was tested against a handful of historical events with mixed results; the café, shop
> and salon models have not been tested against real business outcomes at all.

No customer-facing text claimed port validation for cafés; the one overstatement found in the
product was the home page's "every assumption … named, sourced and testable". Most assumptions
are not sourced. It now reads that each is *named and marked* as the owner's number, published
research, or our assumption.

---

## 2. Sources, checked against the publications

| Source (as cited) | What was checked | Result |
|---|---|---|
| Andreyeva T, Long MW, Brownell KD. *Am J Public Health* 2010;100(2):216–222. doi:10.2105/AJPH.2008.151415 | Full text (PubMed Central), Table 1 | **Verified exactly**: food away from home, mean 0.81, 95% CI 0.56–1.07, range 0.23–1.76, 13 estimates |
| Bijmolt THA, van Heerde HJ, Pieters RGM. *J Marketing Res* 2005;42(2):141–156 | Bibliographic record and abstract via the universities' research portals | **Verified**: 1,851 elasticities from 81 studies, mean −2.62 |
| Tellis GJ. *J Marketing Res* 1988;25(4):331–341 | Article text (JSTOR copy) | **Verified**: 367 elasticities from about 220 brands/markets; the −1.76 mean is the total row (337 observations) of the article's estimation-method table |

What each source licenses is already recorded in `event_sim/wedge/evidence.py` and is
unchanged. The key limitation stands: Andreyeva is category-level demand for eating out; the
two meta-analyses measure switching between brands inside a shop, not between shops or cafés.

---

## 3. What drives the café recommendation

### Inputs, by kind

| Kind | Café inputs |
|---|---|
| **Owner's facts** | monthly sales, daily orders, monthly ingredient cost, monthly fixed costs, cash available, supplier increase, share of orders on low-margin items |
| **Owner's measured observation** | a price-test result — used only if it meets every condition (§5) |
| **Sourced assumption** | price sensitivity at the *central* setting: 0.81 |
| **Our assumptions** | price sensitivity low 0.50 and high 1.60; cost pass-through 100% (70% low); cost lag 5–10 days; how fast customers react (half the reaction in ~2 weeks; ~1 month slow; ~1 week fast); menu-trim saving 0.30 points of cost per point of low-margin share (swept 0.15–0.45); orders lost from trimming = one third of the cost saving; 90-day horizon; fixed costs and post-change prices constant; demand responds in a straight line to price |
| **Calculated** | average order value, cost per order, daily revenue, gross profit, cash path, monthly profit rate, the ranking |

### Price sensitivity is the hinge — and the setting that flips the answer is ours

Census of the demo café (162 cases):

| Price-sensitivity setting | Status | Which option leads |
|---|---|---|
| Low 0.50 | our assumption | +10% in all 54 |
| Central 0.81 | **published (category-level)** | +10% in all 54 |
| High 1.60 | our assumption | +10% in 22, +5% & trim in 32 |

Every case where the answer changes is at the **high** setting, which no study supports
directly: it is placed between the category estimate's upper bound and the brand-level mean.
The page now states, next to the setting, whether it is a published figure or our assumption.

### Other drivers

- **Demand dynamics.** Demand relaxes toward `100 − ε·Δprice` at 5% of the gap per day (central).
  Under the slow setting it has closed only about 60% of that gap even after six weeks. This
  shapes both the 90-day comparison and what a short test can show (§5).
- **Costs and margins.** Owner facts, with pass-through and lag assumed. In the demo, pass-through
  and the trim saving change the size of the gap but never the leader on their own.
- **Time horizon.** Ranked by **cash at day 90**. Each card's figure is the monthly profit rate
  over the last 30 days. In 27 of the café's 162 cases (15 shop, 12 salon) those two
  orderings disagree. The ranking measure is now stated under the verdict, and the owner's own
  option is compared on the same measure.
- **Differences between trades.** Shop and salon use their own ranges (§1 rows 3–4). Bakery and
  fast food reuse the café's numbers with only the wording changed. Each carries its own note
  saying the borrowed evidence is a longer reach for it.
- **Extrapolation.** The precomputed options go up to +10% (café). An owner's own option goes to
  30%. Past the largest compared rise, the result rests on the demand response staying a straight
  line, and the page now says so. That boundary is a property of **this comparison**, not an
  economic threshold. A figure of "about 15%" mentioned in an earlier conversation had no
  evidential support and was not used.

No coefficient, range or scenario definition was changed in this audit.

---

## 4. The count of tested cases

The number shown ("first in 130 of 162 tested cases") is a **count over a full grid**:
3 price-sensitivity × 2 pass-through × 3 supplier increases × 3 trim savings × 3 reaction speeds.
Every combination has equal weight. It is **not a probability**, and the page says so.

Audit points:

- **The ranges decide the count.** Adding or dropping a setting changes it. For the demo café,
  all 32 non-default wins come from one unsupported setting (§3).
- **It includes the owner's facts at values they did not report.** The supplier increase is
  tested at 20%, 30% and 40% whatever the owner entered. At the owner's own 30% alone, the split
  is +10% 43 / +5% & trim 11 of 54 — about the same share. A salon's diary fullness is tested at
  75% and 95%. The new "How is this counted?" note names these ranges beside the owner's own
  value. **The page now also shows the count at the owner's own increase** beside the full count
  ("first in 130 of 162 · 43 of the 54 at your own 30%"). At a tested size it is that slice of the
  census; between the tested sizes the browser engine runs the other 54 combinations at the
  owner's figure. For a café at 25% the page gives +10% in 43 of 54, exactly what the Python
  pipeline gives when swept at 25% alone (+10% 43, +5% & trim 11) — checked in
  `tests/test_launch_page.py`. It is still a count over ranges we chose, not a probability.
- **Salon parity defect, fixed.** The page census ignored the swept diary fullness while the
  report's census swept it, so the page counted the same 81 runs twice. It now counts what the
  report counts. See the before/after in §6.

---

## 5. The experiment loop

### What was wrong

1. **A before/after count was treated as a measurement.** Two numbers — daily orders before and
   after — produced a figure the page called "not a guess any more — you measured it".
2. **It changed the comparison automatically.** The price-sensitivity setting moved to whichever
   tested value was nearest, with no check of what else happened in those weeks.
3. **The reading guide contradicted the model's own dynamics.** It read a two-week drop against
   the long-run settings: for a café, "lost less than 5% — not very price-sensitive". By the
   model's own assumptions, the second week after a change shows only 24–68% of the eventual
   reaction. A café at the *published central* setting would therefore expect a 2.0–5.5% drop,
   and the old guide would have labelled it insensitive.
4. **Weekdays, holidays, promotions, stock-outs and simultaneous changes** were not asked about.

### What it does now

- **Records.** The owner records the rise and how many days ago it was made. They give daily
  counts of the repriced items before the change and in the latest days, and — strongly
  recommended — the same counts for similar items they did not reprice. They also confirm four
  conditions: same days and hours; no promotion, holiday or event; no stock-outs; no other
  simultaneous change.
- **Observed.** The page reports the repriced items' change, the unchanged items' change, and the
  ratio between them. The ratio removes whatever moved the whole business.
- **Uncertainty.** Only ordinary counting noise is allowed for: two standard errors on the log
  ratio, treating daily totals as Poisson counts. The page says real weeks vary more. The range is
  used to decide what the result cannot rule out; it is never shown as a precise interval.
- **Inferred.** For each setting, and at each of the model's reaction speeds, the page computes
  the drop the model expects over the same days. A setting "fits" if any speed puts it inside the
  observed range.
- **Result**, one of four:

  | Result | Rule | Effect |
  |---|---|---|
  | **Supported** | exactly one setting fits; unchanged items counted; all four conditions confirmed; each count covers ≥ 7 days; ≥ 14 days since the change; not a diary-capped business | the comparison uses that setting, shown and reversible |
  | **Provisional** | one setting fits, but a condition is missing | kept as a note; nothing changes |
  | **Inconclusive** | more than one setting fits | kept as a note; stated as a normal result |
  | **Outside** | no setting fits | kept as a note; something else probably changed |

- **Only a supported result** is filed under "your numbers", offered for sharing, or allowed to
  set the comparison. Earlier stored results, and old sheet links, show as notes.
- **Salon results never update automatically.** A full diary hides fewer bookings, so the salon
  test counts requests, not appointments.

### Minimum practical observations

Daily counts of 3–5 repriced items and a few similar unchanged items: at least a week before,
and a latest window of at least 7 days that ends 14 or more days after the change. Same days
and hours throughout. For a salon: requests, two weeks before and at least four after.

### What this still cannot do

- **Separate the settings with café-sized counts.** At about 20 sales a day of the test items,
  a week's counts fit every setting, so the result is inconclusive. Longer tests, more items and
  larger volumes help, but **two weeks is not always enough**, and the page says so.
- **Separate price sensitivity from reaction speed.** A small, fast reaction and a large, slow one
  look alike early on. The overlap between the ranges is exactly this.
- **Rule out substitution.** Customers who switch from repriced to unchanged items push the
  comparison items up. That inflates the apparent sensitivity. It is not corrected.
- **Speak for the whole business.** The test covers a few items; generalising is a judgement.

---

## 6. Numerical behaviour changes

No model coefficient, range, scenario definition or accounting rule changed. What changed is how
the page counts, compares and reads.

| Change | Before | After |
|---|---|---|
| Report figures (options, sensitivity grid, assumptions) | — | **identical** after regeneration (see the final report) |
| Café and shop census on the page | — | unchanged |
| Salon census on the page | the same 81 runs counted twice | counts the swept diary fullness, as the report does — see the table below |
| Reading guide, second week after +10% (café) | low <5.0% · mid ≈8.1% · high >16.0% | low 1.2–3.4% · central 2.0–5.5% · high 3.9–10.9% |
| Reading guide (shop) | <7.0% · ≈13.0% · >26.0% | 2.5–5.9% · 4.7–11.0% · 9.4–21.9% |
| Reading guide (salon) | <3.0% · ≈6.0% · >12.0% | 0.8–2.2% · 1.7–4.5% · 3.4–9.0% |
| A test result | always set the nearest setting | sets it only when supported (§5) |
| Own option's comparison sentence | monthly-rate gap to the best of the three | gap in cash after 90 days — the ranking measure |
| Own option above the largest compared rise | no warning | warns that the result rests on a straight-line response |
| Decision-sheet links | figures in `?sheet=` (reach the server's logs) | figures in `#sheet=` (never sent to the server); old links still open |
| Owner's supplier increase and low-margin share (browser flow) | rounded to the nearest tested increase; the report's own share used | used as entered — see the table below |
| Host-built report for an increase between tested sizes (intake form, e.g. +25%) | the page's self-check failed and **withheld every number** | checked at the report's own increase; numbers shown (regression test added) |

### The owner's own answers now reach the numbers (defect found during this audit)

The browser flow asks the owner for their supplier increase and their low-margin share, but
the page computed with the **nearest tested increase** (20/30/40% for a café) and with **the
report's own low-margin share**. So an owner's answer could be shown and not used, and the
headline showed the rounded increase as if the owner had said it. The page now runs those
worlds for the owner's own figures with its browser engine, which is verified against every
precomputed case first. Its figures now match the Python pipeline for that owner.

Cash after 90 days for options A / B / C, for owners who differ from the report's business:

| Owner | Increase entered → used before | Page before | Page now | Python pipeline | First on the ranking measure, before → now |
|---|---|---|---|---|---|
| Café: 25% increase, 10% low-margin share | 25% → **20%** | 20,427 / 28,280 / 25,281 | 18,407 / 26,401 / 23,015 | 18,407 / 26,401 / 23,015 | +10% → +10% |
| Café: 30% increase, 30% low-margin share | 30% → 30% | 16,388 / 24,522 / **21,462** | 16,388 / 24,522 / 21,811 | 16,388 / 24,522 / 21,811 | +10% → +10% |
| Shop: 20% increase, 10% low-margin share | 20% → **15%** | 24,794 / 36,188 / 38,268 | 18,830 / 30,825 / 29,160 | 18,830 / 30,825 / 29,160 | **+4% & drop lines → +8%** |
| Salon: 40% full, 10% low-margin share | 25% → 25% | 27,092 / 32,514 / **30,276** | 27,092 / 32,514 / 30,070 | 27,092 / 32,514 / 30,070 | +10% → +10% |

For the shop owner, the old page overstated cash by about 6,000, and it put the other option
first.

Census (which option ranks first, out of 162 tested cases):

| Owner | Page before | Page now | Python report census |
|---|---|---|---|
| Café: 25% increase, 10% low-margin share | +10% in 130 (the demo's count) | +10% in 136 | +10% in 136, +5% & trim in 26 |
| Salon: 40% full, demo's low-margin share | +10% in 162 | +10% in 150 | +10% in 150, +5% & mix in 12 |
| Salon: 40% full, 10% low-margin share | +10% in 162 | +10% in 162 | +10% in 162 |

The census still tests the increases 20/30/40% whatever the owner entered, exactly as the
report's census does, and the "How is this counted?" note says so. Beside it, the page now
shows the same count at the owner's own increase (§4).

### Enter on a choice used the default instead of the owner's answer (found in the launch walkthrough)

On a question answered by choosing — the low-margin share, the size of the supplier increase —
a keyboard user who moved to a choice and pressed Enter did not choose it. The step's own Enter
handler took the key, skipped the choice and moved on with whatever value the step already
held: the report business's default. On the last step that meant a comparison computed with a
low-margin share the owner never gave, with nothing on screen to say so. Pointer and touch users
were not affected.

Found by walking the shop flow by keyboard on the PHP host. Before: Enter on "low, about 10%"
produced a result for 20% (the default). After: it records 10%. Figures for any given set of
inputs are unchanged; what changed is which inputs a keyboard user's answers produce. Checked
by `test_enter_on_a_choice_is_left_to_the_choice`, which fails on the previous page.

---

## 7. Validity limits, in one place

- The comparison is only as good as the owner's figures and the named assumptions. The owner's
  figures are not checked against their books.
- Only the café's central price sensitivity is a published figure, and it is category-level,
  US-based and old.
- The model assumes fixed costs, the owner's post-change prices and customer behaviour stay
  stable for 90 days, with a straight-line response to price.
- Reaction speed is unknown; it widens both the comparison's sensitivity and what a test can
  show.
- The grid's ranges are our choice; the count over them is not a probability.
- Nothing here has been compared with real café outcomes. That needs recorded test results from
  many businesses, compared with what the model said — a separate study from this pilot.

## 8. What remains unvalidated

- Whether the model's comparisons match real outcomes, for any trade.
- Whether owners understand the page without help, can supply the inputs, and tell facts from
  assumptions.
- Whether the comparison or the test changes decisions for good reasons.
- Whether owners run the test, and whether the tests they run are informative.
- Whether anyone will commit to paying for the defined follow-up, and at what price.
