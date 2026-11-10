You will answer four independent prompts, each from a different simulation. For each one: read the prompt
file, decide as the seat it addresses, and write your reply to the answer file. Treat the four as unrelated.
Read ONLY this file and your four prompt files, nothing else in these folders, and run no code at all (no
JSON check either).

Each prompt file has a CONTEXT block (the situation, your seat, its goals, what each action does, what
happened in earlier stages and the state after each), then the simulation engine's SYSTEM and PROMPT text
with the reply schema. Play your seat realistically: choose the one action this seat would most plausibly
take in this stage given its goals, character, the current state and what the others did so far, from the
actions that belong to your seat (or hold_position). If your seat is "environment", choose the outside
event that would most plausibly occur in this stage given the state, or hold_position if nothing notable
would. Where the engine text conflicts with the CONTEXT block about style, follow the CONTEXT block.

Each answer file must contain only one JSON object (UTF-8, no BOM, no markdown fence, no "### ACTION_JSON"
line) with the keys: chosen_action, primary_variable, probability, justification, causal_chain,
expected_effect. justification and causal_chain in Persian, justification at most 40 words.
expected_effect is the listed effect of the action you chose.

Reply with one line listing the four actions you chose.
