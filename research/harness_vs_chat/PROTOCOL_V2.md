# Second comparison: referee harness (no engine formula) vs plain chat

Written 2026-11-10, after the first comparison (harness 3 of 12) and before any output of this arm existed.

## What changes

The first comparison lost mainly for two reasons: the engine's linear arithmetic produced values that
contradicted the story, and separate seats were short-sighted. This second arm removes the arithmetic and
keeps the structure:

- **Actors (four separate sub-agents per stage)** choose one action from their own list, as before. New:
  each also writes a private plan note for its own later stages and may send one short public message to
  another seat.
- **Referee (a separate sub-agent, also playing the environment seat)** sees all four actions and
  messages, chooses the outside event (or none), and writes the state after the stage: a value and a
  cause for every variable, the list of conditions in force, and a short summary. The listed effects of
  actions and the scenario's influences are given to it as guidance, not as arithmetic.
- **Framework checked by code (`v2.py`):** every variable present and within 0 to 100; no variable moves
  more than 25 points in a stage unless a chosen action's listed effect on it is larger; the outside event
  is one of the environment's own actions or `hold_position`; every actor's action belongs to its seat.
  A reply that breaks a rule is sent back once.
- No numeric engine is used anywhere. There is no separate ledger in this test.

## What stays the same

Same four scenarios (`scenario.json` unchanged), same model for both arms (Claude Sonnet sub-agents), the
same chat outputs (`chat.json`, reused unchanged from the first comparison), the same rendering script and
layout (only actions, reasons and states are shown; plans, messages and referee summaries are not, so the
two outputs look alike), three fresh Claude Opus judges with the same instructions, and the same decision
rule over 12 judgments: 9 or more for the harness = build; 4 to 8 = no clear advantage; 3 or fewer = plain
chat is at least as good. X/Y assignment uses a new seed.

## Stated in advance

- If this arm also ends at 8 or fewer, the conclusion is that separate seats with a step-by-step referee
  do not beat one plain answer in this setting, and the line of work stops.
- Same limits as before: four scenarios, single runs, model judges from the same family, a possible
  preference of judges for tidy story arcs.
