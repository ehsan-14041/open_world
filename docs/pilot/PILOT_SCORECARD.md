# Pilot scorecard and decision rules

**Fixed before the first session.** Do not edit the thresholds after sessions begin. If you
must, record the change, the date and the reason at the bottom of this file, and report both
the original and the revised reading.

Every threshold here is an **internal pilot decision** — a line the project chose so that the
result of nine sessions leads to an action. None is a scientific benchmark, and hitting them
does not show product–market fit, market size, or that the model is accurate.

---

## 1. What is scored per session

Taken from the observation sheet (`OBSERVATION_TEMPLATE.md`).

| Code | Measure | How it is read |
|---|---|---|
| S1 | **Completion** | Reached a result with their own numbers: yes / partly / no |
| S2 | **Assistance** | Highest level used (0–4); count of level 3–4 interventions |
| S3 | **Inputs** | Fields from records vs estimated vs missing |
| S4 | **Comprehension** | Section C total, 0–10 |
| S5 | **Fact vs assumption** | Section C question 2 scored 2 |
| S6 | **No probability misreading** | Did not treat the tested-case count as a chance |
| S7 | **Actionable next step** | Named a concrete test (items, what to count, how long): yes / partly / no |
| S8 | **Decision effect** | Section E category (a changed decision is **not** scored as good in itself) |
| S9 | **Willingness to pay** | none / hypothetical / explicit commitment / completed payment |
| S10 | **Follow-up** | Acted · ran the test · returned · abandoned (with reason), at ~2 and ~6 weeks |

A session "passes" a measure as follows:

- S1 pass = "yes"; S2 pass = highest level ≤ 2; S4 pass = 7 or more; S7 pass = "yes".
- S8 "valid" = kept or changed the plan for a reason that matches what the page showed.

---

## 2. Classifying what went wrong

Each session gets **one main failure mode** (or none), with the evidence written next to it.
These are kept separate because each leads to a different response.

| Failure mode | Typical evidence | What it points to |
|---|---|---|
| **Usability** | Cannot complete the flow or understand the screens; needs level 3–4 help; comprehension ≤ 4 | Fix the flow or wording |
| **Model credibility** | Understands the result, but rejects an assumption (e.g. "my customers don't react like that") or the approach | Examine that assumption; offer the test; do not change defaults to please |
| **Relevance / urgency** | Understands and trusts it, but takes no step: the decision is not pressing, or pricing is not their real question | Revisit the use case |
| **Offer / business model** | Uses it and finds it useful, but will not commit to paying | Revisit the offer, the payer, the frequency or the price |

---

## 3. Reading the nine sessions

Read overall and, if non-café trades were included, separately by trade. Report counts
("5 of 9"), never percentages of so small a group.

### Continue with the café workflow (with fixes) — all of:

- **S1** pass in at least **6 of 9**, with **S2** pass in at least **6 of 9**;
- **S4** pass in at least **5 of 9**, and **S6** holds in at least **7 of 9**;
- **S7** pass in at least **4 of 9**;
- **S9** explicit commitment or completed payment in at least **2 of 9**;
- at the six-week follow-up, at least **2** ran a test, whatever its result.

### Simplify the workflow — if:

- the relevance signals are there (at least **5 of 9** name a real pricing decision and say
  price sensitivity or customer reaction is what they are unsure about), **but**
- completion or comprehension falls short of the "continue" lines, with usability as the main
  failure mode in at least **3** sessions.

Then: fix the specific screens behind the failures, and run a further batch of three before
anything else.

### Change the decision use case — if:

- relevance / urgency is the main failure mode in at least **4 of 9**, **or**
- at least **5 of 9** say the pricing decision is not the one they most need help with — record
  which decision they name instead.

Then: do not add a new model yet. Run short discovery conversations on the decision owners
actually named, and bring the result back before building.

### Revisit the offer or business model — if:

- the "continue" lines for S1, S4 and S7 are met, **but**
- no participant reaches explicit commitment or payment.

Then: test a different offer, payer (for example an accountant or association serving several
cafés) or frequency before building more product.

### Pause development — if either:

- **S1** pass in **2 or fewer** of 9 **and** **S4** pass in **2 or fewer**, with no explicit
  commitments; **or**
- at least **5 of 9** reject the **same** assumption as not credible and no test the owner
  could run would resolve it.

### Early stop within the pilot

After each batch of three: if **all three** sessions fail completion for the **same** usability
reason, stop, fix that one thing, record the new build, and continue. The sessions before and
after the fix are reported separately.

---

## 4. What nine sessions can and cannot justify

**Can:** identify recurring problems; show whether owners can supply the inputs; show whether
they understand the difference between their facts and the model's assumptions; show whether
anyone commits to paying for a defined deliverable; suggest the next experiment.

**Cannot:** establish market size, product–market fit, a validated price, or that the model's
comparisons match real café outcomes. Model accuracy needs a separate test: owners' recorded
results compared with what the model said, over many businesses. See `EVIDENCE_AUDIT.md`.

---

## Record of changes to this scorecard

| Date | Change | Reason | Sessions completed at the time |
|---|---|---|---|
| | | | |
