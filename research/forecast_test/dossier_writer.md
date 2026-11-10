You are preparing short briefing files for a set of yes/no questions about politics. Use ONLY your own
knowledge. Use no tool except reading the one input file you were given and writing the one output file:
no web search, no other files, no code. You have no information after your training data and must not
pretend to; write what you know and your best estimates as of that point.

The input file is a JSON list of questions, each with: id, question, rules (how it resolves), start (the
date the question opened; treat it as "today") and close.

For EVERY question write a dossier:

- "background": at most 50 words: the situation as far as you know it, with the facts that matter.
- "actors": 2 to 4 actors who will decide the outcome (people, parties, institutions, electorates). For each:
  - "name"
  - "public": at most 35 words: declared position, resources, track record in similar episodes.
  - "private": at most 35 words: your best estimate of what it would really accept, its red lines,
    constraints, deadlines and undeclared intentions.
- "events": up to 3 outside events that could change the outcome before the close date, each with "name"
  and "chance" (0 to 1, over the whole period).

Do not state a probability for the question and do not say which way it will resolve.

Write one JSON object to the output path (UTF-8, no BOM, no markdown fence, nothing else):

{"dossiers": {"<id>": {"background": "...", "actors": [{"name": "...", "public": "...", "private": "..."}],
                       "events": [{"name": "...", "chance": 0.2}]}, ... every id ...}}

Reply with one line: the number of dossiers written, and whether you used any tool other than reading the
input file and writing the output file.
