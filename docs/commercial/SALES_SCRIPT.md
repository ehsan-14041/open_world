# Showing the cafe comparison to an owner — script and test protocol

> **Superseded for the customer-validation phase by [`docs/pilot/`](../pilot/README.md).** Kept for history. Two statements below have been corrected: a payment is evidence of willingness to pay, not validation of the model; and the price is set by the project owner before sessions — the $99 figure was a placeholder, never a tested price.

Ten to twenty minutes, laptop open, one page. You are not selling software; you are offering
to compare one real decision they are facing, three ways, on one model, for a fee.

## The pitch, in one breath

> "Give me one real decision in your business — your ingredient costs went up, say — and
> I'll show you three ways you could respond, side by side, on the same model of your cafe,
> so the differences come from the decision and not from different guesses."

If they ask how that differs from asking ChatGPT three times: *that gives you three answers
from three different invented cafes. This gives you one cafe, one set of assumptions, three
decisions. And you can change any assumption and watch all three move together.*

## The walk (section by section)

**The decision.** Don't explain; let them read the question and the three cards. Point at the
one tagged *Ranks first under current assumptions*, then at the one in red. *"That's doing
nothing."* Then the sentence under the cards. Wait.

**How stable is this result?** Point at the big number. *"Raise 10% came first in 130 of the
162 assumption combinations we tested — that's a count of cases, not a probability."* Then the
box beside it: *"And this is the one thing the answer hinges on."* Tap **High**. Watch the
cards re-order and the line under the buttons change. Tap **Medium** to put it back.

**What could change the answer?** Two cards, two leaders. Then the amber box: *"So the real
question isn't our model — it's whether your competitors will raise prices too. A small price
test would tell you more than any assumption we make."*

**The next 90 days.** Point at the hump in the grey line around day 14. *"That's the two weeks
you're still using stock bought at the old price. It looks fine, then it doesn't."* Hover to
show day-by-day values.

**Where did these numbers come from?** Don't read it. *"Four boxes: yours, research, our
assumptions, and what we calculated. Nothing hidden."* Point at the amber note: *"and these two
only affect option C — they're our judgement until you cost the items yourself."*

**What this does — and doesn't do.** Read the "does not" list aloud. Every time.

**The ask.** Tap *Try your business* at the top. *"Eight numbers. Want to put yours in now?"*

## What you are actually testing

This is a market experiment with a fixed protocol, not a sales push. Run it the same way
each time and write down what happened.

| Phase | Who | What you offer |
|---|---|---|
| 1 | First 3 owners | A free customised report in exchange for their real eight numbers, one real decision, and 20 minutes of feedback |
| 2 | Owners 4 onward | The same report at a real price **set by the project owner in advance**. Do not optimise pricing yet. |

Quote the price before you generate the report, not after.

## Before you show anything — three things to collect first

Do not ask "do you like this?". Ask for:

1. **One real decision** they are facing in the next 60 days. Write it in their words.
2. **Their real numbers** — the eight inputs. If they guess, note which ones are guesses.
3. **Their current intuition**: *"Before I show you anything — what do you think you'll do, and
   why?"* Write it down verbatim. Whether the report changes it is one of the most useful
   things you will learn.

## After showing it — record every one of these

| Question | Answer |
|---|---|
| Did they provide real data (not round guesses)? | yes / partly / no |
| Did they understand the three-world comparison without help? | yes / with prompting / no |
| Did they challenge or change an assumption? | which one |
| Did they ask for a rerun? | what changed |
| Did it change what they wanted to investigate? | how |
| Would they use it for another decision? | which |
| Would they pay? | yes / no / maybe |
| What price felt reasonable to them? | their number |
| Their strongest objection, verbatim | |

## Two rules that protect the experiment

**Do not modify the model after Customer 1 to make Customer 2 happier.** Every owner sees the
same instrument. If the model changes between customers, you have no comparison.

**Keep product feedback separate from model calibration.** "The chart is confusing" is product
feedback — act on it. "My customers are more loyal than 0.81" is a calibration claim — record
it, run it for them as a custom assumption, and do not change the default.

## Signals — record every one

**Strong** (each one is a data point):

- They give you real operational numbers, not round guesses.
- They name a real decision they are facing in the next 60 days.
- They ask to change an assumption and rerun.
- They ask *"can you compare something else?"* — note what.
- They pay.

**Weak** (pleasant, worth nothing):

- "Cool." "Interesting." "The AI is impressive."
- Any compliment about the chart.
- Clicks, opens, forwards.

## The evidence ladder

| Level | Signal | Worth |
|---|---|---|
| 0 | "Looks cool." | Almost nothing |
| 1 | Provides real business data | Meaningful |
| 2 | Provides a real upcoming decision | Strong |
| 3 | Requests a rerun / changes an assumption | Very strong |
| 4 | Pays | Willingness-to-pay evidence (not validation of the model) |

## The provisional bar

Roughly **10 serious demonstrations → at least 2 reach Level 1 → at least 1 reaches Level 4.**

This is a commercial go/no-go, not a statistical test. Hitting it means: build the next
scenario. Missing it means: the product as framed does not clear the bar, and that is a
result — write it down before deciding what to change.

## Things not to say

- *predict*, *forecast*, *will happen*, *guaranteed*, *optimal* — the report avoids them and
  so must you.
- *AI* — the numbers are not produced by an AI, and the owner should hear that as a feature.
- Anything about the simulation engine's scientific validation. A sale does not validate the
  engine; a failed benchmark does not invalidate the product. Different tracks.

## After each demo, write down

Name, date, eight inputs (if given), the decision they named, what they asked to change,
price quoted, price paid, and the exact words of their strongest objection. That last one is
the most valuable thing you will collect.
