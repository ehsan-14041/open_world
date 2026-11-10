"""
One round of the comparison across all four scenarios.

    python research/harness_vs_chat/round.py brief     # write <scenario>/chat_brief.md for the chat arm
    python research/harness_vs_chat/round.py open      # merge the answers of the open turn (if any), write next prompts
    python research/harness_vs_chat/round.py close     # merge the last answers and write run.json
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDS = ["phone_ban", "free_coder", "water_ration", "truck_strike"]
sys.stdout.reconfigure(encoding="utf-8")


def step(mode, sid):
    r = subprocess.run([sys.executable, str(HERE / "step.py"), mode, str(HERE / sid)], capture_output=True, text=True,
                       encoding="utf-8")
    print((r.stdout + r.stderr).strip())
    return r.returncode


def turns_done(sid):
    n = 0
    while (HERE / sid / f"turn_{n + 1}.json").exists():
        n += 1
    return n


mode = sys.argv[1]
if mode == "brief":
    for sid in IDS:
        sc = json.loads((HERE / sid / "scenario.json").read_text("utf-8"))
        lines = ["Situation: " + sc["description"], f"Each stage lasts: {sc['stage_length']}. There are 5 stages.", "", "Seats:"]
        for a in sc["initial_agents"]:
            lines.append(f"- {a['name']} ({a['role']}). Goals: {json.dumps(a['objectives'], ensure_ascii=False)}. "
                         f"Character: {a['personality']}")
        lines += ["", "Variables (0 to 100), meaning, value before the event:"]
        for v, x in sc["initial_state"].items():
            lines.append(f"- {v}: {sc['variable_labels'].get(v, '')} = {x}")
        lines += ["", "Actions, the seat each belongs to, and what each does to the variables in one stage:"]
        for act in sc["allowed_actions"]:
            lines.append(f"- {act} [{sc['action_owner'].get(act, 'any')}]: "
                         f"{json.dumps(sc['action_tradeoffs'].get(act, {}), ensure_ascii=False)}")
        (HERE / sid / "chat_brief.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(sid, "brief written")
    sys.exit(0)

for sid in IDS:
    n = turns_done(sid)
    if (HERE / sid / "answers").exists() and any((HERE / sid / "answers").glob(f"turn_{n + 1}_*.json")):
        if step("merge", sid):
            sys.exit(1)
    if mode == "open":
        step("prompts", sid)
    else:
        step("run", sid)

if mode == "open":
    n = turns_done(IDS[0]) + 1
    seats = {}
    for sid in IDS:
        sc = json.loads((HERE / sid / "scenario.json").read_text("utf-8"))
        for k, a in enumerate(sc["initial_agents"]):
            seats.setdefault(k, []).append((f"{sid}/prompts/turn_{n}_{a['name']}.txt", f"{sid}/answers/turn_{n}_{a['name']}.json"))
    for k, pairs in seats.items():
        print(f"SEAT {k}: " + " ; ".join(f"{p} => {a}" for p, a in pairs))
