# Harness vs plain chat: result of the quick blind comparison

Run on 2026-11-10. Protocol, written before any output: `research/harness_vs_chat/PROTOCOL.md`.
Raw result: `research/harness_vs_chat/results.json`. Unlabeled pairs: `research/harness_vs_chat/pairs/*.md`
(key in `pairs/key.json`).

## Result

| | harness (original engine, one call per seat per stage) | plain chat (one answer) |
|---|---|---|
| preferred, out of 12 judgments | 3 | 9 |
| believable behaviour (1 to 5) | 3.00 | 4.00 |
| numbers consistent with the story | 3.17 | 3.83 |
| non-obvious insight | 3.00 | 3.25 |
| usefulness to a decision maker | 2.92 | 3.58 |

By the rule fixed in advance (3 or fewer), the outcome is: **plain chat is at least as good; this result
gives no reason to build the harness.** The three judges agreed on every scenario.

| scenario | preferred | why, in the judges' words (shortened) |
|---|---|---|
| phone import ban | chat 3 of 3 | harness pushed legal supply to 100 while the ban was in force; seats repeated one action |
| free coding model | chat 3 of 3 | harness path was rosy and repetitive; chat had a turning point (downturn, layoffs, partial recovery) |
| water rationing | harness 3 of 3 | harness exposed the trade-off: free tankers drained the utility budget to 7 and rationing had to tighten; chat leaned on convenient rain |
| truck strike | chat 3 of 3 | harness repeated the same moves for five stages, fuel never addressed, prices rose to 93 while supply recovered |

## Why the harness lost, as far as this run shows

1. **The engine's arithmetic produced values that contradict the story.** An event is applied as a one-off
   change; afterwards the causal links and other actions pull the variable back, so a ban "wears off"
   without anyone lifting it. Two variables ran into the ceiling of 100.
2. **Separate seats were short-sighted.** Each seat picked the locally sensible action every stage, often
   the same one, so there was no negotiation, no deal and no arc. The single chat answer could plan a
   coherent path across seats and stages.
3. **Where the harness won, it was because of bookkeeping.** In the water scenario the budget was a stock
   that every action drew on, and the engine kept the account honestly; the chat answer glossed over it.

## Second round: referee harness, no engine formula

Protocol written before the run: `research/harness_vs_chat/PROTOCOL_V2.md`. Raw result:
`research/harness_vs_chat/results_v2.json`. Pairs: `research/harness_vs_chat/pairs_v2/`.

Change: the numeric engine was removed. Four separate actor seats chose actions (each with a private
multi-stage plan and the option of a public message); a separate neutral referee, also playing the
environment, wrote the state after every stage inside a framework checked by code (bounds, a cap of 25
points per stage, seat ownership of actions). Same scenarios, same chat outputs, three fresh judges.
All 20 referee replies passed the framework checks on the first attempt.

| | referee harness | plain chat |
|---|---|---|
| preferred, out of 12 judgments | 1 | 11 |
| believable behaviour | 3.17 | 3.92 |
| numbers consistent with the story | 3.50 | 3.50 |
| non-obvious insight | 2.33 | 3.92 |
| usefulness to a decision maker | 3.00 | 3.92 |

By the rule fixed in advance the outcome is again "plain chat is at least as good", and by the stopping
rule in PROTOCOL_V2.md this line of work stops.

What the judges said: removing the formula did fix the contradictions (consistency is now equal), and
actors did react to one another (a deal ended the truck strike in stage 3; the phone ban was softened
with a quota). But the paths were flat: the referee chose "no outside event" in 19 of 20 stages, numeric
responses were small, one seat repeated the same action five times, a settled scenario left two empty
stages, and some seats reasoned from "this is the last stage". The chat answers contained shocks, turning
points and second-round effects, which is what the judges found useful.

Two caveats specific to this round: the referee was instructed that "in many stages nothing notable
happens" and to avoid convenient rescues, and the seats were told the exercise has five stages; both are
choices of this design and contributed to the flat paths and the last-stage reasoning. And judges reward
eventful paths, which is not the same as realistic ones.

## Third round: rich dossiers, hidden information, real global actors

Run on 2026-11-11. Protocol written before the run: `research/harness_vs_chat/PROTOCOL_V3.md`. Raw result:
`research/harness_vs_chat/results_v3.json`. Pairs: `research/harness_vs_chat/pairs_v3/`.

Change: four new scenarios with real named actors and a hypothetical trigger (OPEC+ quota, US chip
controls, EU app-store rules, EU duties on Chinese EVs). Every seat had a public file and a private file;
seats could write their own action, send private messages, kept private notes and were not told the number
of stages; outside events were drawn by code and given to both arms; the referee saw everything. The
narrator received all files including every private part. All 20 referee replies passed the framework
checks on the first attempt. Seats sent 142 private messages and wrote 4 actions of their own.

| | harness (separate seats + referee) | narrator (one answer) |
|---|---|---|
| preferred, out of 12 judgments | 0 | 12 |
| believable behaviour | 3.17 | 4.00 |
| numbers consistent with the story | 2.75 | 3.83 |
| non-obvious insight | 2.92 | 4.00 |
| usefulness to a decision maker | 2.75 | 4.00 |

Outcome by the rule fixed in advance: "the narrator is at least as good". The three judges agreed on every
scenario. As stated in advance, separate seats are not built.

What the judges said, shortened:

- **Time did not advance in the harness.** After five monthly stages the OPEC+ path was still "before the
  29 November meeting"; a 60-day deadline was still pending after ten months. The narrator moved through
  the calendar (failed meeting, rollover, January price test, small cut).
- **Repetition remained.** One seat chose the same action four times, another wrote down the same
  inventory twice.
- **Numbers moved without a cause** in the harness (a variable falling with no action behind it), and
  most variables ended within 10 points of the start.
- **The narrator used the hidden information better than the seats that held it.** In the EV scenario it
  played the front-loading of shipments, the battery-licence lever and the misread German vote into a
  path that ended in a quota; the harness seats haggled and left those levers unused.

Caveats specific to this round: the seat and referee prompts gave the stage number and length but no
calendar date, which is a flaw of this harness design and is behind the frozen-time finding; several
things changed at once; a few public figures in the dossiers came from the writers' memory or weak
sources (same for both arms); one seat note contained a stray phrase from another scenario because one
sub-agent answered four scenarios in a row (not visible to judges). A narrator that sees every private
part can write surprise without being surprised, and judges cannot tell the difference.

Across three rounds the harness was preferred in 4 of 36 judgments.

## Fourth round: does the dossier add anything to one narrator?

Run on 2026-11-11. Protocol written before the new outputs: `research/harness_vs_chat/PROTOCOL_V4.md`.
Raw results: `research/harness_vs_chat/results_v4_raw.json`, `results_v4_bg.json` (in those files the
dossier arm is labelled "harness" and the other arm "chat"). Pairs: `pairs_v4_raw/`, `pairs_v4_bg/`.

Three arms, each one call to the same model on the four round-three scenarios: **dossier** (the round-three
narrator: researched background, public and private file per actor, action lists), **raw** (a question of
one or two sentences and the actors' names), **background** (the researched background paragraph, no actor
files). Same variables, drawn events, output shape and limits. Judges saw the background but not the
actor files.

| | dossier vs raw | dossier vs background |
|---|---|---|
| dossier preferred, out of 12 | 12 | 10 (1 for background, 1 tie) |
| believable behaviour | 3.92 vs 3.08 | 3.75 vs 3.58 |
| numbers consistent with the story | 3.50 vs 3.42 | 3.50 vs 3.42 |
| non-obvious insight | 4.08 vs 2.92 | 4.08 vs 3.00 |
| usefulness to a decision maker | 4.08 vs 3.00 | 3.83 vs 3.08 |

By the rule fixed in advance (9 or more), **the dossier adds value in both comparisons**. This is the first
result in this series in favour of something built around the model.

What the judges said, shortened:

- The raw and background outputs were "coherent but generic": a 2020-style price war, an
  escalate-then-truce arc, a tidy fight-then-settle story.
- The dossier outputs had concrete levers: Russia's cut existing only on paper, strategic-reserve buying
  as a soft price floor, the cloud rule traded for rare-earth licences, a quiet deadline extension under
  trade pressure, battery-technology licensing as leverage over a plant in Hungary.
- The raw output got a current fact wrong (it gave the UAE an OPEC+ quota after the UAE had left). The
  background fixed that kind of error and raised the behaviour score (3.08 to 3.58) but not insight
  (2.92 to 3.00). The gain in insight came from the actor files.
- The dossier outputs were not clean: a meeting date reused in a later stage, and China quietly buying
  chips right after the re-denial, which one judge preferred the background output over.

What this does and does not show:

- **It shows** that actor files with concrete constraints make one narrator's output read as more
  specific, more insightful and more useful than the same model produces from a short question or from
  current background alone.
- **It does not show the output is more correct.** The private files were invented by a model. The levers
  the judges praised come largely from those invented files; the judges could not check them and were
  told that a specific detail is not better for being specific, yet specifics clearly drove the
  preference. A fluent path built on invented private facts can mislead a reader more than a generic one.
  The value is real only to the extent the files are true, which means they must come from data or from
  someone who knows.
- Same limits as before: four scenarios, single runs, model judges from the same family as the writers.

## Limits

- Four scenarios, one run per arm, and judges that are language models from the same family as the
  writers. This is a signal, not a proof. The owner can judge the same unlabeled pairs.
- Judges may favour a tidy story with a clean ending, which favours the chat arm; tidy is not the same as
  realistic.
- The harness was tested as it is today plus a context block. Lags, persistent events, a referee and
  repeated runs were not present; this result does not say an improved harness could not do better. It
  does say that the advantage is not there by default and would have to be built and then shown.
- No engine code was changed. Scenario settings: `behavior_type: FLOW`, `max_delta: 40`.
