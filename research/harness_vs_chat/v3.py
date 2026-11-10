"""
Third comparison (PROTOCOL_V3.md): rich dossiers, private information, events drawn by code, a referee.

    python v3.py check      # validate the four scenario files
    python v3.py init       # draw outside events, write dossier.md and the narrator brief
    python v3.py actors     # write the seat prompts of the next stage
    python v3.py referee    # check seat answers, write the referee prompts
    python v3.py close      # check referee answers, write stage_N.json (and run.json at stage 5)
    python v3.py chatcheck  # check the narrator outputs against the same limits
"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / "v3"
IDS = ["opec_quota", "chip_controls", "app_store", "ev_tariffs"]
CAP, STAGES, SEED = 25, 5, 20261112
sys.stdout.reconfigure(encoding="utf-8")
J = lambda o: json.dumps(o, ensure_ascii=False)


def load(p):
    t = p.read_text("utf-8-sig").strip()
    return json.loads(t[t.find("{"): t.rfind("}") + 1])


def done_stages(d):
    out = []
    while (d / f"stage_{len(out) + 1}.json").exists():
        out.append(json.loads((d / f"stage_{len(out) + 1}.json").read_text("utf-8")))
    return out


def event_text(sc, name):
    if not name:
        return "هیچ رویداد بیرونی"
    e = next(x for x in sc["events"] if x["name"] == name)
    return f"{name}: {e['description']} ({e['effects']})"


def act_text(seat, r):
    a = r.get("chosen_action")
    return str(r.get("custom_action", "")).strip() if a == "custom" else a


def dossier(sc, private=True):
    L = [sc["description"], "", f"هر مرحله: {sc['stage_length']}", "", "متغیرها (۰ تا ۱۰۰):"]
    L += [f"- {v}: {x['label']} (شروع: {x['start']})" for v, x in sc["variables"].items()]
    for s in sc["seats"]:
        L += ["", f"### {s['name']} ({s['role']})", "", "آشکار: " + s["public"], ""]
        if private:
            L += ["پنهان (فقط خودش می‌داند): " + s["private"], ""]
        L += ["کنش‌ها: " + "؛ ".join(f"{k} = {v}" for k, v in s["actions"].items())]
    L += ["", "رویدادهای بیرونی ممکن (احتمال در هر مرحله):"]
    L += [f"- {e['name']} ({e['probability']}): {e['description']} {e['effects']}" for e in sc["events"]]
    return L


def check_state(sc, prev, state, problems, tag=""):
    new = {}
    for v in sc["variables"]:
        x = state.get(v)
        val = x.get("value") if isinstance(x, dict) else x
        if not isinstance(val, (int, float)):
            problems.append(f"{tag}{v} missing")
            continue
        if not 0 <= val <= 100:
            problems.append(f"{tag}{v}={val} outside 0..100")
        if abs(val - prev[v]) > CAP + 1e-9:
            problems.append(f"{tag}{v} moved {val - prev[v]:+.0f}, cap {CAP}")
        new[v] = round(float(val), 1)
    return new


mode = sys.argv[1]
rng = random.Random(SEED)
for sid in IDS:
    d = HERE / sid
    sc = json.loads((d / "scenario.json").read_text("utf-8-sig"))
    seats = sc["seats"]
    names = [s["name"] for s in seats]
    start = {v: x["start"] for v, x in sc["variables"].items()}

    if mode == "check":
        p = []
        if len(seats) != 4:
            p.append(f"{len(seats)} seats")
        if not 6 <= len(sc["variables"]) <= 9:
            p.append(f"{len(sc['variables'])} variables")
        for s in seats:
            p += [f"{s.get('name')} lacks {k}" for k in ("name", "role", "public", "private", "actions") if not s.get(k)]
            if len(s.get("actions", {})) < 4:
                p.append(f"{s['name']} has {len(s['actions'])} actions")
        for e in sc["events"]:
            if not 0 < e["probability"] <= 0.3:
                p.append(f"event {e['name']} p={e['probability']}")
        print(sid, "OK" if not p else p, "|", names, "|", len(sc["variables"]), "vars |", len(sc["events"]), "events |",
              sum(len(s["public"].split()) + len(s["private"].split()) for s in seats), "dossier words")
        continue

    if mode == "init":
        ev = []
        for _ in range(STAGES):
            hits = [e["name"] for e in sc["events"] if rng.random() < e["probability"]]
            ev.append(rng.choice(hits) if hits else None)
        (d / "events.json").write_text(json.dumps(ev), encoding="utf-8")
        (d / "dossier.md").write_text("\n".join(dossier(sc)) + "\n", encoding="utf-8")
        L = ["You are given a real-world situation with a hypothetical trigger, four actors with detailed files, and a set of",
             f"variables. Play the situation forward {STAGES} stages and write how it unfolds, as realistically as you can.",
             "Each actor knows what is public and its own private part only; write their choices accordingly.",
             "The private parts are invented for this exercise.", ""] + dossier(sc)
        L += ["", "Outside events, already fixed by a draw (use exactly these, add no others):"]
        L += [f"- stage {i}: {event_text(sc, e)}" for i, e in enumerate(ev, 1)]
        L += ["", "Limits:", "- Every variable stays within 0 to 100 and moves at most 25 points in one stage.",
              "- In each stage every actor takes ONE action: one of its listed action names, or, if none fits, a short",
              "  free-text action of at most 15 words.",
              "- Actors may exchange private messages: at most two per actor per stage, at most 30 words each; a message",
              "  is read by its recipient at the start of the next stage.", "",
              "Write your answer as one JSON object (UTF-8, no BOM, no markdown fence, nothing else) to the answer path you",
              "were given. Persian text fields in Persian. Shape:",
              '{"stages": [ {"actions": {"<seat name>": {"chosen_action": "...", "justification": "<the actor\'s real reason, at most 40 words>"}, ... all four seats ...},',
              '              "messages": [{"from": "<seat>", "to": "<seat>", "text": "..."}, ...],',
              '              "summary": "<what publicly happened in this stage, at most 60 words>",',
              '              "state": {"<variable>": <number>, ... every variable ...}}, ... ' + str(STAGES) + ' stages ... ]}',
              "", "Seat names: " + ", ".join(names), "Variable names: " + ", ".join(sc["variables"])]
        (d / "chat_brief.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        print(sid, "events:", ev)
        continue

    if mode == "chatcheck":
        ch = load(d / "chat.json")["stages"]
        p, prev = [], start
        if len(ch) != STAGES:
            p.append(f"{len(ch)} stages")
        for i, st in enumerate(ch, 1):
            p += [f"s{i} lacks {n}" for n in names if n not in st.get("actions", {})]
            prev = check_state(sc, prev, st.get("state", {}), p, f"s{i} ") or prev
        print(sid, "chat OK" if not p else p)
        continue

    (d / "prompts").mkdir(exist_ok=True)
    (d / "answers").mkdir(exist_ok=True)
    events = json.loads((d / "events.json").read_text("utf-8"))
    done = done_stages(d)
    n = len(done) + 1
    if n > STAGES:
        print(sid, "already complete")
        continue
    state = done[-1]["state"] if done else start
    cond = done[-1]["conditions"] if done else []
    ev_now = event_text(sc, events[n - 1])

    def record(private):
        L = []
        for k, st in enumerate(done, 1):
            L.append(f"Stage {k}: outside event: {st['event_text']}")
            for a in names:
                x = st["seats"][a]
                L.append(f"  {a} -> {x['action']}" + (f" | public statement: {x['public_statement']}" if x["public_statement"] else "")
                         + (f" | private reasoning: {x['private_reasoning']}" if private else ""))
            if private:
                L += [f"  private message {m['from']} -> {m['to']}: {m['text']}" for m in st["messages"]]
            L += [f"  summary: {st['summary']}", f"  state after stage {k}: {J(st['state'])}"]
        return L or ["(nothing has happened yet)"]

    def base(private):
        L = ["Situation: " + sc["description"], "", f"Each stage lasts: {sc['stage_length']}. This is stage {n}.", "",
             "Variables (0 to 100), meaning, current value:"]
        L += [f"- {v}: {x['label']} = {state[v]}" for v, x in sc["variables"].items()]
        L += ["", "Conditions in force now: " + (J(cond) if cond else "none"), "",
              "Record so far:" if private else "Public record so far:"] + record(private)
        L += ["", f"Outside event at the start of stage {n}: {ev_now}"]
        return L

    if mode == "actors":
        for s in seats:
            L = ["You are playing one seat in a step-by-step scenario exercise built on a real situation with a hypothetical",
                 "trigger. Play it the way this actor really would: pursue its interests, protect what it hides, and use what",
                 "only it knows. The private parts are invented for the exercise.", ""] + base(False)
            L += ["", f"YOUR SEAT: {s['name']} ({s['role']})", "What everyone knows about you: " + s["public"],
                  "What ONLY you know: " + s["private"], "", "The other seats (what is publicly known about them):"]
            L += [f"- {o['name']} ({o['role']}): {o['public']}" for o in seats if o is not s]
            L += ["", "Your listed actions:"] + [f"- {k}: {v}" for k, v in s["actions"].items()]
            notes = done[-1]["notes"].get(s["name"]) if done else None
            inbox = [m for m in done[-1]["messages"] if m["to"] == s["name"]] if done else []
            L += ["", "Your private notes from the previous stage: " + (J(notes) if notes else "none"),
                  "Private messages you received (sent during the previous stage): "
                  + ("; ".join(f"from {m['from']}: {m['text']}" for m in inbox) if inbox else "none")]
            L += ["", "Task: choose the ONE action your seat takes in this stage: one of your listed actions, or \"custom\" with your",
                  "own action if none fits. The exercise goes on for a number of stages you do not know; think several stages",
                  "ahead. Do not keep repeating a move that has stopped working. Consider what the others want and what they",
                  "may be hiding; you may offer, threaten, concede or bluff. You may send up to two private messages (each to",
                  "one other seat); they are read at the start of the next stage and nobody else sees them.", "",
                  "Reply with one JSON object only:",
                  '{"chosen_action": "<listed action name or custom>", "custom_action": "<Persian, at most 15 words, only if custom>",',
                  ' "private_reasoning": "<Persian, at most 40 words: your real reason>",',
                  ' "public_statement": "<Persian, at most 30 words: what you say in public, or empty>",',
                  ' "messages": [{"to": "<seat name>", "text": "<Persian, at most 30 words>"}],',
                  ' "beliefs": "<Persian, at most 40 words: what you now think the others want, hide or will do>",',
                  ' "plan": "<Persian, at most 50 words: private note to your later self>"}']
            (d / "prompts" / f"stage_{n}_{s['name']}.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        print(f"{sid}: stage {n} seat prompts written | event: {events[n - 1]}")
        continue

    acts, problems = {}, []
    for s in seats:
        p = d / "answers" / f"stage_{n}_{s['name']}.json"
        if not p.exists():
            problems.append(f"missing {p.name}")
            continue
        r = load(p)
        a = r.get("chosen_action")
        if a != "custom" and a not in s["actions"]:
            problems.append(f"{s['name']} chose {a}, not one of its actions")
        if a == "custom" and not str(r.get("custom_action", "")).strip():
            problems.append(f"{s['name']} chose custom without text")
        r["messages"] = [m for m in (r.get("messages") or []) if m.get("to") in names and m.get("to") != s["name"] and m.get("text")][:2]
        acts[s["name"]] = r
    if problems:
        print(f"{sid}: stage {n} PROBLEMS:", problems)
        continue

    if mode == "referee":
        L = ["You are the neutral referee of a step-by-step scenario exercise built on a real situation with a hypothetical",
             "trigger. Four actors have each chosen an action for this stage. You see everything, including what each",
             "actor hides. You decide what actually happens in this stage.", ""] + base(True)
        L += ["", "The four seats:"]
        for s in seats:
            L += [f"- {s['name']} ({s['role']})", "  public: " + s["public"], "  private: " + s["private"]]
        L += ["", f"Actions chosen in stage {n}:"]
        for a, r in acts.items():
            desc = next(s for s in seats if s["name"] == a)["actions"].get(r["chosen_action"], "own action")
            L += [f"- {a} -> {act_text(a, r)} ({desc})", f"  private reasoning: {r.get('private_reasoning', '')}",
                  f"  public statement: {r.get('public_statement', '')}"]
            L += [f"  private message to {m['to']}: {m['text']}" for m in r["messages"]]
        L += ["", "Your tasks:",
              "1. State after this stage: a new value for EVERY variable, with the cause.",
              "   - Values stay within 0 to 100. No variable moves more than 25 points in one stage.",
              "   - Decide how such a situation really moves in a stage of this length. Real actions by actors this large",
              "     have real consequences: do not shrink every effect into a small step, and do not exaggerate either.",
              "   - Effects can be delayed, build up, saturate or cancel one another. A condition in force keeps acting",
              "     until something ends it. Each actor's true constraints (its private part) bind what it can actually",
              "     deliver, whatever it says in public.",
              "   - The outside event of this stage is the one stated above; add no other outside event.",
              "   - Do not favour any seat and do not invent convenient rescues.",
              "2. Conditions in force after this stage: short Persian phrases (measures, deals, deadlines that persist).",
              "3. A summary of the stage in Persian, at most 60 words, containing ONLY what would be publicly visible",
              "   (the actors will read it; do not reveal private reasoning, private messages or private parts).", "",
              "Reply with one JSON object only:",
              '{"state": {"<variable>": {"value": <number>, "why": "<Persian, at most 20 words>"}, ... every variable ...},',
              ' "conditions": ["...", ...], "summary": "..."}']
        (d / "prompts" / f"stage_{n}_referee.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        print(f"{sid}: stage {n} referee prompt written |", {a: act_text(a, r) for a, r in acts.items()})
        continue

    # close
    p = d / "answers" / f"stage_{n}_referee.json"
    if not p.exists():
        print(f"{sid}: stage {n} PROBLEMS: missing referee answer")
        continue
    r = load(p)
    new = check_state(sc, state, r.get("state", {}), problems)
    if problems:
        print(f"{sid}: stage {n} PROBLEMS:", problems)
        continue
    stage = {"event": events[n - 1], "event_text": ev_now,
             "seats": {a: {"action": act_text(a, x), "private_reasoning": x.get("private_reasoning", ""),
                           "public_statement": x.get("public_statement", "")} for a, x in acts.items()},
             "messages": [{"from": a, "to": m["to"], "text": m["text"]} for a, x in acts.items() for m in x["messages"]],
             "notes": {a: {"beliefs": x.get("beliefs", ""), "plan": x.get("plan", "")} for a, x in acts.items()},
             "state": new, "why": {v: (r["state"][v].get("why", "") if isinstance(r["state"][v], dict) else "") for v in new},
             "conditions": r.get("conditions", []), "summary": r.get("summary", "")}
    (d / f"stage_{n}.json").write_text(json.dumps(stage, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sid}: stage {n} closed | messages: {len(stage['messages'])} | state: {J(new)}")
    if n == STAGES:
        allst = done_stages(d)
        (d / "run.json").write_text(json.dumps({"stages": [
            {"actions": {a: {"chosen_action": x["action"], "justification": x["private_reasoning"]} for a, x in s["seats"].items()},
             "messages": s["messages"], "summary": s["summary"], "state": s["state"]} for s in allst]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{sid}: run.json written")
