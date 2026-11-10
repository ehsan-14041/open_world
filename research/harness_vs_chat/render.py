"""
Render both arms of every scenario into the same layout, unlabeled, as pairs/<scenario>.md.
Which arm is "X" is a seeded random draw per scenario; the key goes to pairs/key.json.

    python research/harness_vs_chat/render.py
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDS = ["phone_ban", "free_coder", "water_ration", "truck_strike"]
V2 = len(sys.argv) > 1 and sys.argv[1] == "v2"      # referee harness (PROTOCOL_V2.md): new seed, own folder
rng = random.Random(20261111 if V2 else 20261110)
out = HERE / ("pairs_v2" if V2 else "pairs")
out.mkdir(exist_ok=True)
key = {}


def block(title, sc, stages, start):
    names = list(sc["initial_state"])
    labels = sc.get("variable_labels", {})
    roles = {a["name"]: a["role"] for a in sc["initial_agents"]}
    lines = [f"## خروجی {title}", ""]
    for i, st in enumerate(stages, 1):
        lines += [f"### مرحلهٔ {i}", "", "| بازیگر | کنش | دلیل |", "|---|---|---|"]
        for a in roles:
            d = st["actions"].get(a) or {}
            why = str(d.get("justification", "")).replace("|", "/").replace("\n", " ")
            lines.append(f"| {roles[a]} | {d.get('chosen_action', '-')} | {why} |")
        lines += ["", "وضعیت پس از این مرحله: " + "، ".join(
            f"{v}={round(float(st['state'].get(v, 0)))}" for v in names), ""]
    lines += ["### از شروع تا پایان", "", "| متغیر | معنا | شروع | " + " | ".join(f"م{i}" for i in range(1, len(stages) + 1)) + " |",
              "|---|---|---|" + "---|" * len(stages)]
    for v in names:
        lines.append(f"| {v} | {labels.get(v, '')} | {round(float(start[v]))} | "
                     + " | ".join(str(round(float(st["state"].get(v, 0)))) for st in stages) + " |")
    return lines + [""]


for sid in IDS:
    f = HERE / sid
    sc = json.loads((f / "scenario.json").read_text("utf-8"))
    run = json.loads(((HERE / "v2" / sid if V2 else f) / "run.json").read_text("utf-8"))
    harness = [{"actions": t, "state": s} for t, s in zip(run["turns"], run["states"][1:])]
    chat = json.loads((f / "chat.json").read_text("utf-8-sig"))["stages"]
    x_is = rng.choice(["harness", "chat"])
    key[sid] = {"X": x_is, "Y": "chat" if x_is == "harness" else "harness"}
    arms = {"harness": harness, "chat": chat}
    head = [f"# {sid}", "", sc["description"], "", f"هر مرحله: {sc.get('stage_length', '')}", "",
            "بازیگران: " + "، ".join(f"{a['name']} ({a['role']})" for a in sc["initial_agents"]), "",
            "اثر هر کنش در یک مرحله: `" + json.dumps(sc["action_tradeoffs"], ensure_ascii=False) + "`", ""]
    body = block("X", sc, arms[key[sid]["X"]], sc["initial_state"]) + block("Y", sc, arms[key[sid]["Y"]], sc["initial_state"])
    (out / f"{sid}.md").write_text("\n".join(head + body), encoding="utf-8")
(out / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
print("pairs written:", ", ".join(IDS))
