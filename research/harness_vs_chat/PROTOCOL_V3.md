# Third comparison: rich dossiers and hidden information, separate seats vs one narrator

Written 2026-11-11, before any scenario or output of this round existed. PROTOCOL_V2.md said the line of
work stops after a second loss; the owner asked to reopen it for one different question, stated here.

## Question

The first two rounds used thin actor definitions (two weighted goals, one sentence of character, three or
four actions) and no seat knew anything the others did not. Does a harness of separate seats beat a single
narrator when (a) every actor has a detailed dossier and (b) every actor holds private information?

## What is new

- **Four new scenarios with real, named, global actors** and a hypothetical trigger set in November 2026:
  `opec_quota`, `chip_controls`, `app_store`, `ev_tariffs`. Each is written by a separate sub-agent that may
  use web search for public facts. Format: `scenario_spec.md`.
- **Dossier per seat:** a public part (position, goals, resources with numbers, track record) and a private
  part (red lines, breaking points, intentions, facts only that seat knows). Private parts are invented for
  the exercise and say nothing about the real actors.
- **Open actions:** a seat chooses one of its listed actions or writes its own.
- **Private messages:** up to two per seat per stage, read by the recipients at the start of the next stage.
- **Seats are not told how many stages there are.** Each keeps a private note of plan and beliefs.
- **Outside events are drawn by code**, not chosen by a model: each scenario lists events with a per-stage
  probability; `v3.py init` draws them for all stages with seed 20261112 (at most one per stage). **The same
  drawn events are given to both arms.**
- **Referee** (separate sub-agent) sees everything, including private parts and messages, and writes the
  state, the conditions in force and a summary containing only what would be publicly visible. No listed
  numeric effects exist; the framework checked by code is: every variable present, within 0 to 100, at most
  25 points of movement per stage. A reply that breaks a rule is sent back once.

## Arms

- **Harness:** four separate seat sub-agents per stage (each sees the public record, its own full dossier,
  the others' public parts, its own notes and the messages addressed to it), then the referee. Five stages.
- **Narrator (plain chat):** one sub-agent per scenario receives all dossiers including every private part,
  the drawn events and the same limits (bounds, 25 points per stage, message limits), and writes all five
  stages in one answer.

Same model for seats, referee and narrator (Claude Sonnet sub-agents). No numeric engine anywhere; no
engine code is changed.

## Judging and decision rule

Both arms are rendered by `render3.py` into the same layout (dossiers, then per stage: outside event,
each seat's action and reason, private messages, summary, state), unlabeled, X/Y by seed 20261113. Three
fresh Claude Opus judges, same four dimensions as before, plus one added sentence telling them that an
eventful or tidy path is not better for that reason alone (`judge_instructions_v3.md`). Over 12 judgments: 9 or more for the harness =
build; 4 to 8 = no clear advantage; 3 or fewer = the narrator is at least as good.

## Stated in advance

- This round changes several things at once, so a win would not say which change mattered; it would say
  the combination is worth isolating. A loss (8 or fewer) with rich dossiers and hidden information means
  the remaining explanations for the earlier losses are used up, and separate seats are not built.
- A narrator that sees every private part can still write as if actors were surprised; judges cannot tell
  real ignorance from written ignorance. That favours the narrator and is inherent in judging by reading.
- Same limits as before: four scenarios, single runs, model judges from the same family.
