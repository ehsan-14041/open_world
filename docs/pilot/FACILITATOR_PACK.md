# Café pricing pilot — facilitator pack

Nine exploratory sessions with café owners who face a real pricing decision soon. The aim is
to learn whether this workflow helps an owner make or test that decision:

> a real decision → a comparison under stated assumptions → a practical experiment →
> observation → cautious revision of assumptions.

This is **not** a statistically representative study. Nine sessions can show patterns, surface
problems and suggest the next experiment. They cannot establish market size, product–market
fit or the accuracy of the model. Nothing in these sessions tests whether the model predicts
real sales; see `EVIDENCE_AUDIT.md` for what is and is not verified.

Companion documents:

- `OBSERVATION_TEMPLATE.md` — one copy per session.
- `PILOT_SCORECARD.md` — the evaluation rules, fixed **before** the first session.
- `EVIDENCE_AUDIT.md` — what the product can and cannot claim.

---

## 0. Before the first session — owner decisions

These are decisions for the project owner, not the facilitator. Write them down and do not
change them during the pilot.

| Decision | Value |
|---|---|
| Price of the paid follow-up (section 5) | **__________** (set before session 1) |
| How payment would be taken, if someone commits | __________ (outside OWE; no billing is built) |
| Who delivers the follow-up | __________ |
| OWE build used for all sessions | zip name / `?version` output: __________ |
| Where session notes are stored | outside the repository (see section 8) |
| Thank-you for participants, if any | none / __________ (record it — gifts distort willingness to pay) |

Use one build for the whole pilot. If a blocking bug forces a change, finish the current
batch of three, change the build, and record the new version on every later session sheet.
**Never change the model's assumptions between sessions to please a participant.**

---

## 1. Recruitment

### Who qualifies — all five must be true

1. **Runs an independent café or small restaurant** (owner, or manager with pricing authority).
   Bakeries and fast food are covered by the same model, but keep all nine to cafés if you can.
   If you include other trades, mark them and read their results separately.
2. **Faces a real pricing decision in the next 60 days** — for example, a supplier has raised
   prices and they are deciding whether and how to respond. A hypothetical decision does not
   qualify.
3. **Can supply their own figures** — monthly sales, daily orders, monthly ingredient cost,
   monthly fixed costs, cash available — from their till, books or accounts. Rough figures are
   acceptable; note which ones were guesses.
4. **Has authority to act** on prices without asking someone else. If someone else decides,
   record who; the session may still run, but the payer and the decider differ.
5. **Has not seen OWE before** and is not involved in the project.

### Who to avoid, or cap

- Friends, family, investors, colleagues and anyone who wants the project to succeed: **none**
  if possible, and never more than one in nine. Mark them on the session sheet.
- No more than **two** participants from any one introduction source (one supplier, one
  association, one friend).
- At least **three** of the nine should be recruited "cold": a walk-in, a trade association
  list, a supplier's customer list.
- People who want to sell you something, or who are primarily curious about the technology.

### Screening conversation (2–3 minutes; do not show the tool)

> "We're testing a simple tool that helps café owners compare pricing decisions — for example
> when a supplier puts prices up. It's an early version and we want honest feedback. Are you
> facing a decision like that in the next couple of months?"
>
> «داریم ابزار ساده‌ای را آزمایش می‌کنیم که به صاحبان کافه کمک می‌کند تصمیم‌های قیمتی را با
> هم مقایسه کنند — مثلاً وقتی تأمین‌کننده گران می‌کند. نسخهٔ اولیه است و نظر صادقانه می‌خواهیم.
> در یکی دو ماه آینده با چنین تصمیمی روبه‌رو هستی؟»

Then ask, and record the answers:

1. What is the decision, and by when do you need to make it?
2. Who decides on prices here?
3. Could you bring, or look up during a 30-minute session, your monthly sales, daily orders,
   ingredient costs, fixed costs and the cash you have available?
4. Have you seen or used this tool, or heard about it from us, before?

Invite only if all five qualification criteria hold. Do not describe what the tool
"recommends" or how good it is.

### Consent (read at the start of the session)

> "I'll take notes while you use the tool. Your business figures go into the page on this
> screen and stay in this browser; I won't copy them into anything else unless you agree. I
> won't record audio unless you say yes. You can stop at any time, and you can ask me to
> delete my notes. There's no right answer — we're testing the tool, not you."

Record: consent to notes (y/n), consent to audio (y/n), consent to follow-up contact
(y/n + channel).

---

## 2. Session set-up

- Use **a fresh private (incognito) browser window** for each session, so nothing from a
  previous owner remains in the page's storage. If the owner uses their own phone, it is
  theirs; show them "Start over" at the end if they want their figures cleared.
- Open the home page of the pilot build, in the owner's preferred language.
- Keep the question box's router **off** (the default). Do not type owner figures into the
  question box — with the router on, that text goes to a third-party provider.
- Have the observation template open, or on paper.
- Time box: 25–35 minutes. Do not run over by more than five minutes.

---

## 3. The session script (25–35 minutes)

Times are guides. Words in quotation marks are said as written, or as close as natural speech
allows. Persian versions are given for the lines the owner hears.

### Part A — Before the tool (6–8 min). Nothing is shown yet.

Record answers **verbatim** where you can.

1. > "Tell me about the pricing decision you're facing."
   > «دربارهٔ تصمیم قیمتی‌ای که پیش رو داری بگو.»
   - What is it, exactly? By when? What happens if they do nothing?
2. > "What do you currently plan to do?"
   > «الان قصد داری چه کار کنی؟»
3. > "How did you arrive at that?"
   > «چطور به این نتیجه رسیدی؟»
   - Who or what did they consult? Past experience? Competitors?
4. > "What information do you feel you're missing to decide?"
   > «فکر می‌کنی برای تصمیم گرفتن چه اطلاعاتی کم داری؟»
5. > "On a scale of 1 to 5, how confident are you in that plan — and why that number?"
   > «از ۱ تا ۵ چقدر به این برنامه مطمئنی — و چرا همین عدد؟»

Do not react to their answers beyond "thank you" or "tell me more".

### Part B — Using the tool without help (12–15 min)

Hand over the device on the home page.

> "Please use this to look at the decision you just described, with your own numbers. Say out
> loud what you're thinking as you go. I'll mostly stay quiet — if you get stuck, try what you
> would try at home first."
>
> «لطفاً با این ابزار همان تصمیمی را که گفتی، با عددهای خودت بررسی کن. هر چه به ذهنت می‌رسد
> بلند بگو. من بیشتر ساکتم — اگر گیر کردی، اول همان کاری را بکن که در خانه می‌کردی.»

Allowed neutral prompts: "What are you looking for?", "What would you do next?", "What do you
make of that?", "Say more." If asked what to choose: "What do you think the page is telling
you?"

**Assistance ladder** — record every intervention with its level and the screen it happened on:

| Level | What the facilitator did |
|---|---|
| 0 | Nothing |
| 1 | A neutral prompt from the list above |
| 2 | Pointed to where something is ("it's further down") |
| 3 | Explained what something means |
| 4 | Did the step for them |

Give level 3 or 4 help only after the owner has been stuck for about a minute, or asks
twice. Never explain the model's assumptions before the owner has looked for them.

**Observe and note** (template section B):

- Where they hesitate, go back, or ask for help.
- Which inputs they can supply from records, which they guess, which they cannot give.
- Whether they open "How is this counted?", the assumptions, or the price-sensitivity setting.
- Whether they try "Or build your own option", and with which price rise.
- Whether they open the test plan.
- Anything they say about trusting or not trusting a number — word for word.

Let them stop when they say they are done, or at 15 minutes.

### Part C — Understanding, in their own words (5 min)

Ask each question, then stay quiet. Score later with the rubric in the template.

1. > "In your own words, what did it compare, and over what period?"
   > «به زبان خودت، چه چیزهایی را مقایسه کرد و برای چه مدتی؟»
2. > "Which of those numbers were yours, and which were the tool's assumptions?"
   > «کدام عددها مال خودت بود و کدام فرضِ ابزار؟»
3. > "What does each option give up, and what does it gain?"
   > «هر گزینه چه چیزی را از دست می‌دهد و چه چیزی به دست می‌آورد؟»
4. > "Is there anything that could change which option comes out ahead?"
   > «چیزی هست که بتواند عوض کند کدام گزینه جلو بیفتد؟»
5. > "If you wanted to find out, what would you test, and what would you write down?"
   > «اگر بخواهی بفهمی، چه چیزی را آزمایش می‌کنی و چه چیزی را یادداشت می‌کنی؟»

### Part D — After (3 min)

1. > "What do you plan to do now?"
   > «حالا قصد داری چه کار کنی؟»
2. > "How confident are you, 1 to 5 — and why?"
   > «چقدر مطمئنی، از ۱ تا ۵ — و چرا؟»
3. If the plan changed: > "What made you change it?" / «چه چیزی باعث شد عوضش کنی؟»
   If it did not: > "Did anything you saw support or weaken your plan?" / «چیزی دیدی که برنامه‌ات
   را محکم‌تر یا سست‌تر کند؟»
4. > "Would you run the price test it describes? What would stop you?"
   > «آزمایش قیمتی را که پیشنهاد می‌کند انجام می‌دهی؟ چه چیزی مانعت می‌شود؟»

**A changed decision is not a success in itself.** Record *why* it changed. A change for a
reason the owner can state and that matches what the page actually showed is a different
finding from a change because "the computer said so". A confirmed original decision, for a
reason the owner can state, can be just as useful.

### Part E — The paid follow-up offer (3–5 min)

See section 5. Read the offer as written; do not improvise a discount.

### Part F — Close (1 min)

> "Thank you. Could I contact you in about two weeks, and again in about six, to hear what you
> decided and whether you ran the test? It takes five to fifteen minutes."
>
> «ممنون. اجازه می‌دهی حدود دو هفتهٔ دیگر و دوباره حدود شش هفتهٔ دیگر تماس بگیرم تا بشنوم چه
> تصمیمی گرفتی و آزمایش را انجام دادی یا نه؟ پنج تا پانزده دقیقه طول می‌کشد.»

If they used their own device and want their figures cleared, show "Start over".

---

## 4. Neutrality rules

- Do not show, explain or demonstrate the tool before Part B.
- Do not defend the model. If they say "that number is wrong for me", ask what it should be and
  record it as a **calibration claim**; do not change any setting for them.
- Do not praise their choices, and do not tell them which option is better.
- Never say *predict*, *forecast*, *guarantee*, *optimal*, *probability*, *chance*, *AI
  recommends*, or *the model is validated*. The count of tested cases is not a probability.
- Do not mention the port or shipping work. It does not validate anything about cafés.
- If they ask how accurate it is, say:
  > "It hasn't been tested against real café results yet. It shows what follows from the
  > numbers and assumptions on the page, and which assumption matters most."
  >
  > «هنوز با نتیجهٔ واقعیِ کافه‌ها آزموده نشده. نشان می‌دهد از عددها و فرض‌های همین صفحه چه
  > نتیجه‌ای می‌آید، و کدام فرض از همه مهم‌تر است.»

---

## 5. The willingness-to-pay test

### What is offered

A clearly defined follow-up the project can actually deliver:

> **Price-test follow-up.** Within the next week, a 30-minute session to set up the price
> test for your own items — which items to reprice, which to leave as a comparison, and what
> to count each day. After two to four weeks, a second 30-minute session to enter your counts,
> see what the test does and does not show, and rerun the comparison. You receive an updated
> decision sheet and a one-page written note of the result, including when the result is
> unclear.

It does **not** promise a better decision, higher profit, or a clear test result.

### The script

Only after Part D, so the offer cannot colour their answers.

> "We offer a follow-up for owners who want to go further: [read the offer above]. It costs
> [PRICE]. Would you like to book it?"
>
> «برای کسانی که بخواهند ادامه بدهند یک پیگیری داریم: [پیشنهاد بالا را بخوان]. هزینه‌اش
> [مبلغ] است. می‌خواهی رزروش کنی؟»

Then **stop talking** and record the answer word for word.

- If yes: "Good — when would suit you for the first session?" Agree a date, and how payment
  will be arranged by [project owner], outside the tool. Do not take payment during the
  session unless the project owner has set that up in advance.
- If they ask for a discount: record their number. Do not agree to it unless the project owner
  set a rule beforehand.
- If no: "That's fine. What would have to be different for it to be worth paying for?" Record
  the answer.

### Recording levels — keep them separate

| Level | What counts |
|---|---|
| **None** | Declines, or no interest shown |
| **Hypothetical** | "Maybe", "I would", "sounds useful", "send me details" — no date, no commitment |
| **Explicit commitment** | Agrees to the price **and** a date, or signs/sends a written yes |
| **Completed payment** | Money received (recorded by the project owner, not the facilitator) |

Only "explicit commitment" and "completed payment" count as willingness-to-pay evidence.
"Would you pay?" answers are recorded but carry little weight.

---

## 6. Follow-up protocol

With consent only. Use the channel the owner chose. Keep each contact short.

### About two weeks after the session (5 min)

1. "What did you decide about prices — and have you acted on it?" (what, when)
2. "Did you start the price test? If not, what got in the way?"
3. "Have you opened the tool again? What for?"
4. If they committed to the paid follow-up: confirm the date.

### About six weeks after the session (10–15 min)

1. "What happened after you decided? What did you notice in your sales or costs?"
2. "Did you run the test? What did you count, and what did the tool say about it?" — ask to see
   the result screen if they are willing. Record whether it was supported, provisional,
   inconclusive, or fitted no setting, and **do not reinterpret it for them**.
3. "Did the test change your view of how your customers react to price?"
4. "Did you go back to the tool? Did you stop using it — and why?"
5. "Knowing what you know now, would you pay for the follow-up? What would it be worth?"

Record each outcome in the template's section F: acted / ran the test / returned to OWE /
abandoned — each with the reason, in the owner's words where possible.

If a participant does not respond after two attempts a week apart, record "no response" and
stop. Do not chase further.

---

## 7. After each session (15 minutes, same day)

1. Complete the observation template while memory is fresh.
2. Keep **direct quotes**, **observed behaviour** and **your interpretation** in their separate
   columns.
3. Classify the main failure mode, if any (see `PILOT_SCORECARD.md`).
4. Do not change the product or the model because of one session. Log ideas in the "product
   notes" section and review them after each batch of three.

---

## 8. Data handling

- Session notes contain business figures and possibly identities. **Keep them outside this
  repository** — a private folder or notebook. If you must keep them next to the code, use the
  folder `pilot_sessions/` at the repository root, which is ignored by git. Never commit it.
- Refer to participants by code (P01–P09) in any summary that is shared.
- Do not paste owner figures, names or quotes into any AI tool, chat or the question box.
- The decision-sheet link carries the owner's figures. Do not send it to yourself or anyone
  else without the owner's explicit agreement.
- Delete notes a participant asks you to delete, and record that you did.
