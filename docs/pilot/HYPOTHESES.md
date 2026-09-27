# Hypotheses the hosted build can test

The nine facilitated sessions (`FACILITATOR_PACK.md`, `PILOT_SCORECARD.md`) remain the primary
evidence. They are the only way to see completion, comprehension and hesitation, and the only
way to hear why.

The hosted build adds a second, weaker channel: **owners who use the open link on their own and
choose to answer the short card under their decision sheet.** It can test more owners than
nine sessions can, and more cheaply — but only what owners are willing to say in four clicks, and
only from the owners who got as far as a sheet and chose to answer.

**Fixed before the link is shared.** Do not edit a threshold once a batch has started. If you
must, record the change, date and reason at the bottom, and report both readings. Every line
here is an internal decision chosen so that a count leads to an action; none is a scientific
benchmark.

---

## 1. What the build records, and what it does not

| Recorded (only when an owner presses Send) | Never recorded |
|---|---|
| Is this a decision you face: now / later / no | Which screens were seen, clicks, time spent |
| Did the comparison help: yes / partly / no | Who dropped out, or where |
| Next step: one of the options / their own option / run the price test / undecided / nothing | Business figures, name, IP address |
| Hardest number to give (one of the questions) / none | Anything from owners who do not press Send |
| What was missing, in their words (phone numbers, email, web addresses removed) | |
| The paid follow-up: book / maybe / no — only when a price is set | |
| Worked example or own numbers; business type; language; invitation tag; build; the day | |
| A contact — **only** with "book" chosen and its box ticked, in a separate file | |

Two consequences follow, and they are deliberate:

- **Completion cannot be measured online.** Tracking who stops where would need observation the
  owner did not agree to. Completion and comprehension are measured in the sessions only.
- **Answers are self-selected.** Owners who answer are those who reached a sheet and chose to
  reply — likely the more engaged. Read online counts as an upper bound on usefulness, never as
  a rate for "café owners".

## 2. How a batch is read

- **One build per batch.** `admin.php` splits answers by build; a new build starts a new batch.
- **Count owners, not rows.** Each browser counts once (its latest answer); `admin.php` does this.
- **Only owners with their own numbers** count toward H1–H5. The worked example tells you about
  curiosity, not about a decision.
- **A batch is read at 20 owners with their own numbers**, or after six weeks, whichever comes
  first. Below 20, report the counts and do not apply the thresholds.
- **Report counts** ("9 of 20"), never percentages.
- **Unanswered questions are not "no".** Each threshold is read over the owners who answered that
  question; write the denominator every time.

## 3. The hypotheses

Each has: what would support it, what would count against it, and what it points to. Between the
two lines the result is **unresolved** — say so, and let the sessions decide.

### H1 — Relevance: owners who use it face a real pricing decision

- Source: `real`. Sessions: Part A, and the "relevance / urgency" failure mode.
- Supports: at least **8 of 20** answer "now".
- Against: **4 or fewer of 20** answer "now", **or** at least **10 of 20** answer "no".
- If against: the link is reaching the wrong owners, or pricing is not a pressing decision.
  Compare invitation tags before concluding the second; if every tag is low, apply the scorecard's
  "change the decision use case" route and read the free text for what they do need.

### H2 — Inputs: owners can supply what the comparison asks for

- Source: `hard`. Sessions: S3 (from records / estimated / could not give).
- Supports: no single question is named hardest by more than **5 of 20**, and at least **8 of
  20** answer "none".
- Against: one question is named hardest by at least **8 of 20**.
- If against: simplify or re-word that one question, or offer a way to estimate it. Do not
  change the model's assumptions to avoid asking it.

### H3 — Usefulness: the comparison helps with the decision

- Source: `helped`, among owners who answered "now" or "later" to H1.
- Supports: at least **12 of 20** answer "yes" or "partly", with at least **5** "yes".
- Against: at least **10 of 20** answer "no".
- If against: read the free text and the session D sections — is it the result they distrust
  (model credibility), or the form it takes (usability)? They lead to different fixes.

### H4 — The experiment is a step owners will take

- Source: `next` = "run the price test first"; later, shared measurements (`admin.php` shows the
  count). Sessions: S7 and the six-week follow-up.
- Supports: at least **5 of 20** choose the test, **and** at least **2** supported measurements are
  shared within eight weeks of the batch starting.
- Against: **1 or fewer of 20** choose the test.
- If against: the price test as designed is too heavy to be the product's next step. Consider the
  simpler experiment in the improvement list (costing the low-margin items) before building more.

### H5 — Willingness to pay for the follow-up

- Source: `offer` and `bookings.jsonl` (only when `offer_price` is set). Sessions: S9.
- Levels, kept separate exactly as in the facilitator pack:
  - "maybe" / "no" — recorded, carries little weight;
  - **booking request** — "book" with a contact. Not yet a commitment;
  - **explicit commitment** — you contacted them and they agreed the price and a date;
  - **completed payment** — money received.
- Supports: at least **2** explicit commitments per batch of 20.
- Against: no booking request at all in a batch of 20, **or** requests that none turn into a
  commitment when contacted.
- If against: follow the scorecard's "revisit the offer or business model" route — a different
  payer, offer or frequency — before building more product. Never lower the price mid-batch.

### H6 — Which invitations bring owners it helps (descriptive only)

- Source: `src`. Too few owners per tag for thresholds. Report counts per tag for H1 and H3 so the
  next batch's invitations go where relevant owners are.

## 4. What this channel can and cannot show

**Can:** whether the owners it reaches face the decision; which input is the obstacle; whether
those who finish find it useful; whether anyone asks to pay, at a stated price; which invitations
work; what owners say is missing.

**Cannot:** completion or comprehension (sessions only); whether the model's comparisons match
what happens in a real café (that needs owners' recorded results against what the page said, over
many businesses — see `EVIDENCE_AUDIT.md`); market size or product–market fit.

---

## Record of changes

| Date | Change | Reason | Owners answered at the time |
|---|---|---|---|
| | | | |
