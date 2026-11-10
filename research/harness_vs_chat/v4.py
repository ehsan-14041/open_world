"""
Fourth comparison (PROTOCOL_V4.md): one narrator with dossiers vs the same narrator with a short question
("raw") or with the researched background only ("bg").

    python v4.py init     # write raw_brief.md, bg_brief.md per scenario and the two judge instruction files
    python v4.py check    # check raw.json and bg.json against the limits
    python v4.py render   # write pairs_v4_raw/ and pairs_v4_bg/ (unlabeled) with key.json
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HERE = ROOT / "v3"
IDS = ["opec_quota", "chip_controls", "app_store", "ev_tariffs"]
CAP, STAGES = 25, 5
sys.stdout.reconfigure(encoding="utf-8")

RAW = {
    "opec_quota": "فرض کن در نیمهٔ نوامبر ۲۰۲۶ آمریکا و ایران توافق جامع امضا می‌کنند، صادرات نفت خلیج فارس تقریباً به سطح عادی برمی‌گردد و برنت در دو هفته به حدود ۶۸ دلار می‌افتد. اوپک‌پلاس باید تصمیم بگیرد تولید را دوباره کم کند یا برای سهم بازار بجنگد. چه می‌شود؟",
    "chip_controls": "فرض کن در نوامبر ۲۰۲۶ دولت آمریکا اعلام می‌کند تراشهٔ H200 و تراشه‌های میان‌ردهٔ هوش مصنوعی دوباره زیر «فرض رد» مجوز صادرات به چین می‌روند و ارائهٔ پردازش پیشرفتهٔ ابری به شرکت‌های چینی در هر کشوری از ۶۰ روز بعد ممنوع می‌شود. چه می‌شود؟",
    "app_store": "فرض کن در نوامبر ۲۰۲۶ کمیسیون اروپا اعلام می‌کند کارمزد ۱۵٪ اپل برای هدایت کاربر به وب و کارمزد ۵٪ آن برای توزیع بیرون از App Store با قانون بازارهای دیجیتال سازگار نیست و به اپل ۶۰ روز مهلت می‌دهد آن‌ها را حذف کند، وگرنه جریمهٔ روزانه می‌شود. چه می‌شود؟",
    "ev_tariffs": "فرض کن در نوامبر ۲۰۲۶ کمیسیون اروپا پیشنهاد می‌کند یک تحقیق ضدسوبسید بر خودروهای هیبریدی پلاگین ساخت چین با هدف عوارض موقت ظرف چهار ماه باز شود و عوارض جبرانی خودروهای تمام‌برقی BYD از ۱۷ به ۲۷ درصد برسد. چه می‌شود؟",
}


def ev_text(sc, name):
    if not name:
        return "هیچ"
    e = next(x for x in sc["events"] if x["name"] == name)
    return f"{name}: {e['description']} ({e['effects']})"


def brief(sc, events, question):
    names = [s["name"] for s in sc["seats"]]
    L = ["Answer the question below by playing the situation forward " + str(STAGES) + " stages, as realistically as you can.", "",
         question, "", f"Each stage lasts: {sc['stage_length']}", "", "Actors:"]
    L += [f"- {s['name']}: {s['role']}" for s in sc["seats"]]
    L += ["", "Variables to track (0 to 100):"] + [f"- {v}: {x['label']} (start: {x['start']})" for v, x in sc["variables"].items()]
    L += ["", "Outside events, already fixed by a draw (use exactly these, add no others):"]
    L += [f"- stage {i}: {ev_text(sc, e)}" for i, e in enumerate(events, 1)]
    L += ["", "Limits:", "- Every variable stays within 0 to 100 and moves at most 25 points in one stage.",
          "- In each stage every actor takes ONE action, written as short free text of at most 15 words (Persian).",
          "- Actors may exchange private messages: at most two per actor per stage, at most 30 words each; a message",
          "  is read by its recipient at the start of the next stage.", "",
          "Write your answer as one JSON object (UTF-8, no BOM, no markdown fence, nothing else) to the answer path you",
          "were given. Persian text fields in Persian. Shape:",
          '{"stages": [ {"actions": {"<actor name>": {"chosen_action": "...", "justification": "<the actor\'s real reason, at most 40 words>"}, ... all four actors ...},',
          '              "messages": [{"from": "<actor>", "to": "<actor>", "text": "..."}, ...],',
          '              "summary": "<what publicly happened in this stage, at most 60 words>",',
          '              "state": {"<variable>": <number>, ... every variable ...}}, ... ' + str(STAGES) + ' stages ... ]}',
          "", "Actor names: " + ", ".join(names), "Variable names: " + ", ".join(sc["variables"])]
    return "\n".join(L) + "\n"


def stages_of(p):
    t = p.read_text("utf-8-sig")
    return json.loads(t[t.find("{"): t.rfind("}") + 1])["stages"]


clean = lambda s: str(s).replace("|", "/").replace("\n", " ").strip()


def block(title, sc, stages, events):
    names = list(sc["variables"])
    desc = {s["name"]: s["actions"] for s in sc["seats"]}
    L = [f"## خروجی {title}", ""]
    for i, st in enumerate(stages, 1):
        L += [f"### مرحلهٔ {i}", "", "رویداد بیرونی: " + ev_text(sc, events[i - 1]), "", "| بازیگر | کنش | دلیل |", "|---|---|---|"]
        for s in sc["seats"]:
            d = st["actions"].get(s["name"]) or {}
            a = d.get("chosen_action", "-")
            L.append(f"| {s['name']} | {clean(desc[s['name']].get(a, a))} | {clean(d.get('justification', ''))} |")
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


mode = sys.argv[1]
if mode == "init":
    tmpl = (ROOT / "judge_instructions_v3.md").read_text("utf-8")
    for arm in ("raw", "bg"):
        t = tmpl.replace("pairs_v3", f"pairs_v4_{arm}")
        a = t.index("Each file describes")
        b = t.index("Imagine a reader")
        t = t[:a] + ("Each file describes a real situation with a hypothetical trigger: a background paragraph (take it as true), four\n"
                     "named actors, variables on a 0 to 100 scale, and the outside event of each stage. Then it shows two outputs,\n"
                     "X and Y, produced by two different methods. Each output plays the situation forward five stages: the outside\n"
                     "event of the stage (the same in both outputs), every actor's action and reason, private messages between\n"
                     "actors, a summary, and the variables after the stage. Which method is X differs from file to file; do not try\n"
                     "to guess the method, judge only what is on the page. An output may state internal facts about an actor that\n"
                     "you cannot check; a specific detail is not better for being specific, judge whether it is believable.\n\n") + t[b:]
        t = t.replace("given their public\n  and private files, ", "")
        (ROOT / f"judge_instructions_v4_{arm}.md").write_text(t, encoding="utf-8")

for arm, seed in (("raw", 20261114), ("bg", 20261115)):
    rng = random.Random(seed)
    key = {}
    for sid in IDS:
        d = HERE / sid
        sc = json.loads((d / "scenario.json").read_text("utf-8-sig"))
        events = json.loads((d / "events.json").read_text("utf-8"))
        start = {v: x["start"] for v, x in sc["variables"].items()}
        if mode == "init":
            (d / f"{arm}_brief.md").write_text(brief(sc, events, RAW[sid] if arm == "raw" else "Situation and question: " + sc["description"] + " چه می‌شود؟"), encoding="utf-8")
        elif mode == "check":
            p, prev = [], start
            st = stages_of(d / f"{arm}.json")
            if len(st) != STAGES:
                p.append(f"{len(st)} stages")
            for i, s in enumerate(st, 1):
                p += [f"s{i} lacks {x['name']}" for x in sc["seats"] if x["name"] not in s.get("actions", {})]
                for v in sc["variables"]:
                    val = s.get("state", {}).get(v)
                    if not isinstance(val, (int, float)) or not 0 <= val <= 100 or abs(val - prev[v]) > CAP + 1e-9:
                        p.append(f"s{i} {v}={val} (prev {prev[v]})")
                prev = {v: s["state"].get(v, prev[v]) for v in sc["variables"]} if isinstance(s.get("state"), dict) else prev
            print(arm, sid, "OK" if not p else p)
        elif mode == "render":
            out = ROOT / f"pairs_v4_{arm}"
            out.mkdir(exist_ok=True)
            arms = {"harness": stages_of(d / "chat.json"), "chat": stages_of(d / f"{arm}.json")}   # harness = dossier arm
            x = rng.choice(["harness", "chat"])
            key[sid] = {"X": x, "Y": "chat" if x == "harness" else "harness"}
            head = [f"# {sid}", "", sc["description"], "", f"هر مرحله: {sc['stage_length']}", "", "بازیگران: "
                    + "؛ ".join(f"{s['name']} ({s['role']})" for s in sc["seats"]), "", "متغیرها (۰ تا ۱۰۰):"]
            head += [f"- {v}: {x_['label']} (شروع: {x_['start']})" for v, x_ in sc["variables"].items()] + [""]
            (out / f"{sid}.md").write_text("\n".join(head + block("X", sc, arms[key[sid]["X"]], events)
                                                     + block("Y", sc, arms[key[sid]["Y"]], events)), encoding="utf-8")
            (out / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
print(mode, "done")
