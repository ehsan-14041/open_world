# Fourth comparison: does the dossier add anything to one narrator?

Written 2026-11-11, before any output of the two new arms existed. The dossier outputs
(`v3/<scenario>/chat.json`) already exist from the third comparison and are reused unchanged; they were
written before this protocol and without knowledge of it.

## Question

In the third comparison one narrator with rich dossiers beat separate seats 12 to 0. The narrator is one
language-model call. Does the structured input we built around that call (background, public and private
file per actor, action lists) make its output better than the same model gets from a short question?

## Arms (all: one Claude Sonnet sub-agent per scenario, one answer, same four scenarios, five stages)

- **dossier:** the existing narrator output. Input: researched background, a public and a private file per
  actor, action lists, variables, drawn events.
- **raw:** input is a question of one or two sentences (the hypothetical trigger only, written by me in
  `v4.py` before any output), the four actors by name, variables, drawn events. No background, no files.
- **background:** as raw, but with the full researched background paragraph in place of the short question.
  No actor files.

All three get the same variables with labels and start values, the same drawn outside events, the same
output shape and the same limits (0 to 100, at most 25 points per stage, message limits). The two new arms
have no action lists and write each action as short free text.

Two comparisons, judged separately: **dossier vs raw** and **dossier vs background**. The second isolates
the actor files; the difference between the two shows what the researched background alone is worth.

## Judging

`render4.py` renders each pair in one layout, unlabeled, X/Y by seed 20261114 (raw) and 20261115
(background). Listed action names in the dossier output are shown as their Persian descriptions so that
both outputs read alike. The page head shows what a reader would know: the researched background, the
actors, the variables and the events; **not** the actor files. Judges are told the background is true.
Three fresh Claude Opus judges per comparison, same four dimensions as before.

Decision rule per comparison, over 12 judgments: dossier preferred 9 or more = the dossier adds value;
4 to 8 = no clear difference; 3 or fewer = the dossier adds nothing a reader can see (or hurts).

In `key.json` and the score output the dossier arm is stored under the label "harness" and the other arm
under "chat", only because `score.py` uses those labels.

## Stated in advance

- The private files are invented by a model. Judges do not see them, so a detail taken from them reads as
  an unverified specific. If the dossier wins, that does not show the invented details are right; it shows
  the output reads as more believable and useful. If a user supplied true private facts, the value would
  be at least what is measured here; this test cannot measure that.
- If the dossier loses or ties against **background**, the actor files written by a model add nothing
  visible and the product claim reduces to "supply current facts and ask well".
- If it loses or ties against **raw** as well, even that reduces to "ask the model".
- Same limits as before: four scenarios, single runs, model judges from the same family.
