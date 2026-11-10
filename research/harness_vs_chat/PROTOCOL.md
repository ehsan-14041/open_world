# Harness vs plain chat: a quick blind comparison

Written 2026-11-10, before any output of either arm was produced.

## Question

Is the output of the original multi-agent loop (one language-model call per seat per stage, the engine
keeping the state) preferred over one plain language-model answer to the same event, when both are shown
in the same format with no label? The answer decides whether the "harness" product is worth building.

## Material

Four events chosen by the assistant before any run, from four different domains:

1. `phone_ban`: a mid-sized country suddenly bans imports of phones priced above 600 dollars. Stage: 1 month.
2. `free_coder`: a large AI company makes its strongest coding model free; the effect on software
   outsourcing firms. Stage: 1 month.
3. `water_ration`: severe drought, a large city starts water rationing. Stage: 2 weeks.
4. `truck_strike`: a nationwide strike of truck drivers. Stage: 3 days.

For each event one sub-agent writes a scenario in the repository's own scenario format: an `environment`
agent plus four actors, 6 to 8 variables on 0 to 100, causal links, an action list with trade-offs.
The same scenario (actors, variables, initial state, action list, stage length) is given to both arms.

## Arms

- **Chat:** one sub-agent gets the event, the actors, the variables with their initial values, the action
  list and the stage length, and writes all five stages in one answer: each actor's action and reason per
  stage, and the value of every variable after each stage. It does not see the causal weights and does not
  run any code.
- **Harness:** the original `simulation.loop.SimulationLoop`. For every stage the engine's own prompt for
  every seat is written to a file; a separate sub-agent answers each seat (it sees only that prompt); the
  engine validates and applies the answers and produces the next state. Scenario-level settings are the
  ones already used on 2026-11-09: `behavior_type: FLOW` and `max_delta` from the scenario. Engine code
  is not changed.

Both arms use the same model (Claude Sonnet sub-agents). One seat sub-agent answers the same seat number
in all four scenarios in a stage; seats of the same scenario are never answered by the same sub-agent in
the same stage.

## Judging

Both outputs are rendered by the same script into the same layout and shown as "X" and "Y"; which arm is
X is decided by a seeded random draw per scenario. Three judge sub-agents (Claude Opus), each seeing all
four pairs, give for each pair:

- a 1 to 5 score for each output on: believable actor behaviour, consistency of numbers with the story,
  non-obvious insight, usefulness to someone who must decide;
- one overall preference (X, Y, or tie).

## Decision rule (12 judgments = 4 scenarios x 3 judges)

- harness preferred in 9 or more: the harness shows a clear advantage; build.
- harness preferred in 4 to 8: no clear advantage.
- harness preferred in 3 or fewer: plain chat is at least as good; do not build for this reason.

## Amendment 1 (2026-11-10, before any scenario or output existed)

Dumping the engine's own seat prompt showed that it carries only the variable values, the causal links
and the action list: no description of the situation, no goals or character of the seat, no clock, no
record of what the others did. A seat answered from that prompt alone would be deciding blind, and the
result would say nothing about the product in question. So each seat prompt is the engine's prompt with
a context block in front of it, written by `step.py`: the situation, the stage length and number, the
seat's goals and character, the effect of each action, and every earlier stage's actions and resulting
state. The chat arm receives the same situation, seats, goals, actions and effects. Engine code is still
unchanged; the context block is what the proposed build would add.

## Known limits, stated in advance

- Four scenarios and model judges: this is a signal, not a proof. The unlabeled pairs are also saved for
  the owner to judge personally.
- The judges are from the same model family as the writers.
- The harness is tested as it is today (no time unit inside the engine, no lags, one shared action list,
  no referee, single run). A negative result says today's harness has no advantage, not that an improved
  one could not.
- The chat arm gets a structured brief, which is a stronger baseline than a casual chat question.
