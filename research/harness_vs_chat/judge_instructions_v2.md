You are judging pairs of scenario analyses. Read ONLY this file and these four files, nothing else in
this folder or its sub-folders (in particular not key.json), and run no code:

- E:\owe\research\harness_vs_chat\pairs_v2\phone_ban.md
- E:\owe\research\harness_vs_chat\pairs_v2\free_coder.md
- E:\owe\research\harness_vs_chat\pairs_v2\water_ration.md
- E:\owe\research\harness_vs_chat\pairs_v2\truck_strike.md

Each file describes a situation (an event, five seats: an "environment" seat for outside events plus four
actors, variables on a 0 to 100 scale, and a fixed list of actions with their one-stage effects). Then it
shows two outputs, X and Y, produced by two different methods from the same brief. Each output plays the
situation forward five stages: every seat's action and reason in each stage, and the variables after each
stage. Which method is X differs from file to file; do not try to guess the method, judge only what is
on the page.

Imagine a reader who must make a real decision about this situation and wants to understand how it could
unfold. For each file, score X and Y separately from 1 (poor) to 5 (excellent) on:

- behaviour: do the actors behave the way such actors really would, stage after stage, including reacting
  to one another?
- consistency: do the numbers follow from the actions and from each other, and do they agree with the
  reasons given? Are there values that make no sense for the story?
- insight: does the path show something non-obvious (a second-round effect, a trade-off, a turning point)
  rather than a generic story?
- usefulness: how much would this output help that reader?

Then give one overall preference for the file: "X", "Y" or "tie", and a reason of at most 40 words.

Write your result as one JSON object to the answer path you were given (UTF-8, no BOM, nothing else in the
file), in this shape:

{"phone_ban": {"X": {"behaviour": n, "consistency": n, "insight": n, "usefulness": n},
               "Y": {"behaviour": n, "consistency": n, "insight": n, "usefulness": n},
               "prefer": "X|Y|tie", "why": "..."},
 "free_coder": {...}, "water_ration": {...}, "truck_strike": {...}}

Reply with one line: your four preferences in file order.
