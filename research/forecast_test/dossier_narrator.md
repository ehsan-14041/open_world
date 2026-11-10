You are forecasting a set of yes/no questions about politics. Use no tool except reading the two input
files you were given and writing the one output file: no web search, no other files, no code. You have no
information after your training data and must not assume any.

Input file 1 is a JSON list of questions, each with: id, question, rules (how it resolves), start (treat it
as "today") and close. Input file 2 holds a dossier per question id: a background, the actors who decide
the outcome (each with a public part and a private part, which is an estimate), and possible outside events
with a rough chance over the period.

For EVERY question:

1. Play the situation forward from the start date to the close date in three stages. For each stage write
   at most 35 words: what the actors do, how they react to one another, and whether an outside event
   intervenes. Follow what the actors would really do given their public and private parts.
2. Then state the probability that the question resolves "Yes" under its rules. The path you wrote is one
   way it can go; weigh the other ways before you choose the number.

Write one JSON object to the output path (UTF-8, no BOM, no markdown fence, nothing else):

{"answers": {"<id>": {"path": ["stage 1 ...", "stage 2 ...", "stage 3 ..."], "probability": 0.37}, ... every id ...}}

Reply with one line: the number of questions answered, and whether you used any tool other than reading
the two input files and writing the output file.
