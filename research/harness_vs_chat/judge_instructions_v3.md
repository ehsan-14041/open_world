You are judging pairs of scenario analyses. Read ONLY this file and these four files, nothing else in
this folder or its sub-folders (in particular not key.json), run no code and do not search the web:

- E:\owe\research\harness_vs_chat\pairs_v3\opec_quota.md
- E:\owe\research\harness_vs_chat\pairs_v3\chip_controls.md
- E:\owe\research\harness_vs_chat\pairs_v3\app_store.md
- E:\owe\research\harness_vs_chat\pairs_v3\ev_tariffs.md

Each file describes a real situation with a hypothetical trigger: four named actors, each with a public
file and a private file (the private parts are invented for the exercise), variables on a 0 to 100 scale,
and possible outside events. Then it shows two outputs, X and Y, produced by two different methods from the
same material. Each output plays the situation forward five stages: the outside event of the stage (the
same in both outputs), every actor's action and reason, private messages between actors, a summary, and the
variables after the stage. Which method is X differs from file to file; do not try to guess the method,
judge only what is on the page.

Imagine a reader who must make a real decision about this situation and wants to understand how it could
unfold. For each file, score X and Y separately from 1 (poor) to 5 (excellent) on:

- behaviour: do the actors behave the way these actors really would, stage after stage, given their public
  and private files, including reacting to one another and handling what they do not know?
- consistency: do the numbers follow from the actions and from each other, and do they agree with the
  reasons given? Are there values that make no sense for the story?
- insight: does the path show something non-obvious (a second-round effect, a trade-off, a turning point,
  a consequence of hidden information) rather than a generic story?
- usefulness: how much would this output help that reader?

An eventful or tidy path is not better for being eventful or tidy; a quiet path is not better for being
quiet. Judge whether it is believable and informative.

Then give one overall preference for the file: "X", "Y" or "tie", and a reason of at most 40 words.

Write your result as one JSON object to the answer path you were given (UTF-8, no BOM, nothing else in the
file), in this shape:

{"opec_quota": {"X": {"behaviour": n, "consistency": n, "insight": n, "usefulness": n},
                "Y": {"behaviour": n, "consistency": n, "insight": n, "usefulness": n},
                "prefer": "X|Y|tie", "why": "..."},
 "chip_controls": {...}, "app_store": {...}, "ev_tariffs": {...}}

Reply with one line: your four preferences in file order.
