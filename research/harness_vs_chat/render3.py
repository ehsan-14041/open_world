"""Render both arms of the third comparison into one layout, unlabeled: pairs_v3/<scenario>.md + key.json."""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDS = ["opec_quota", "chip_controls", "app_store", "ev_tariffs"]
rng = random.Random(20261113)
out = HERE / "pairs_v3"
out.mkdir(exist_ok=True)
key = {}
clean = lambda s: str(s).replace("|", "/").replace("\n", " ").strip()


def block(title, sc, stages, events):
    names = list(sc["variables"])
    L = [f"## خروجی {title}", ""]
    for i, st in enumerate(stages, 1):
        e = events[i - 1]
        L += [f"### مرحلهٔ {i}", "", "رویداد بیرونی: " + (e or "هیچ"), "", "| بازیگر | کنش | دلیل |", "|---|---|---|"]
        for s in sc["seats"]:
            d = st["actions"].get(s["name"]) or {}
            L.append(f"| {s['name']} | {clean(d.get('chosen_action', '-'))} | {clean(d.get('justification', ''))} |")
        msgs = [m for m in (st.get("messages") or []) if m.get("text")]
        L += ["", "پیام‌های خصوصی: " + ("هیچ" if not msgs else "")]
        L += [f"- {m.get('from')} به {m.get('to')}: {clean(m['text'])}" for m in msgs]
        L += ["", "خلاصه: " + clean(st.get("summary", "")), "",
              "وضعیت پس از این مرحله: " + "، ".join(f"{v}={round(float(st['state'][v]))}" for v in names), ""]
    L += ["### از شروع تا پایان", "", "| متغیر | شروع | " + " | ".join(f"م{i}" for i in range(1, len(stages) + 1)) + " |",
          "|---|---|" + "---|" * len(stages)]
    for v in names:
        L.append(f"| {v} | {sc['variables'][v]['start']} | " + " | ".join(str(round(float(st["state"][v]))) for st in stages) + " |")
    return L + [""]


for sid in IDS:
    d = HERE / "v3" / sid
    sc = json.loads((d / "scenario.json").read_text("utf-8-sig"))
    events = json.loads((d / "events.json").read_text("utf-8"))
    t = (d / "chat.json").read_text("utf-8-sig")
    arms = {"harness": json.loads((d / "run.json").read_text("utf-8"))["stages"],
            "chat": json.loads(t[t.find("{"): t.rfind("}") + 1])["stages"]}
    x = rng.choice(["harness", "chat"])
    key[sid] = {"X": x, "Y": "chat" if x == "harness" else "harness"}
    head = [f"# {sid}", "", (d / "dossier.md").read_text("utf-8"), ""]
    (out / f"{sid}.md").write_text("\n".join(head + block("X", sc, arms[key[sid]["X"]], events)
                                             + block("Y", sc, arms[key[sid]["Y"]], events)), encoding="utf-8")
(out / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
print("pairs written:", ", ".join(IDS))
