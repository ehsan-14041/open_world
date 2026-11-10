You are writing one scenario file for a step-by-step scenario exercise. Read ONLY this file; do not read
anything else in this folder or repository. Write exactly one file, at the path you were given, and run no
code.

The scenario uses real, named actors and a HYPOTHETICAL trigger that begins "now" (November 2026). You were
given the topic, the four seats and the stage length. You may use web search (about six searches at most)
to get the public facts right and current: positions, numbers, recent history. If the suggested trigger has
in fact already happened, change it to a nearby hypothetical one that has not.

Write the file as one JSON object (UTF-8, no BOM, no markdown fence, nothing else). All text fields are in
Persian, plain and concrete; names of companies, people and products may stay in Latin script. Shape:

{
 "id": "<the id you were given>",
 "description": "<120 to 180 words: the real background with numbers, then the hypothetical trigger>",
 "stage_length": "<as given, in Persian>",
 "variables": {
   "<snake_case_name>": {"label": "<what it measures, and what 0 and 100 mean>", "start": <0 to 100>}
   ... 7 or 8 variables: outcomes that the actors care about and that can move in both directions ...
 },
 "seats": [
   {"name": "<the seat name you were given>",
    "role": "<short Persian name of the actor>",
    "public": "<100 to 150 words. What everyone knows: goals in order of priority, resources and constraints with real numbers, declared positions, how this actor behaved in similar past episodes, its internal factions if they matter>",
    "private": "<80 to 120 words. What only this seat knows: its true red lines and breaking points with numbers, what it would really accept, a weakness or deadline it hides, an intention it has not declared, something it knows about another seat>",
    "actions": {"<snake_case_action>": "<one Persian sentence: what the action is>", ... 6 actions ...}
   }
   ... exactly the four seats you were given, in the given order ...
 ],
 "events": [
   {"name": "<snake_case>", "description": "<one Persian sentence>", "probability": <0.05 to 0.25, chance per stage>,
    "effects": "<one Persian sentence: what it typically does>"}
   ... 5 outside events that none of the four seats controls ...
 ],
 "sources": ["<url> : <what it supports>", ...]
}

Rules:

- The public parts must be true to the best of your knowledge. The private parts are invented for the
  exercise: make them plausible, specific and consequential, and make them matter, so that what one seat
  hides would change what another seat does if it knew. Do not make any seat a villain or a fool.
- Private parts of different seats should interlock: at least two places where seat A is wrong or uncertain
  about something that seat B's private part settles.
- Actions must be real levers of that actor, varied in kind (escalate, concede, delay, deal, go around),
  not six shades of the same move. No numeric effects are attached to actions.
- Do not write how the situation unfolds, and do not hint at a "right" outcome.

Reply with one line: the id and the number of variables.
