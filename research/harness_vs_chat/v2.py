"""
Referee harness (PROTOCOL_V2.md): separate actor seats choose actions, a referee writes the next state.
No numeric engine. Runs across all four scenarios.

    python research/harness_vs_chat/v2.py actors    # write the actor prompts of the next stage
    python research/harness_vs_chat/v2.py referee   # check actor answers, write the referee prompts
    python research/harness_vs_chat/v2.py close     # check referee answers, write stage_N.json (and run.json at 5)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDS = ["phone_ban", "free_coder", "water_ration", "truck_strike"]
CAP = 25
sys.stdout.reconfigure(encoding="utf-8")
J = lambda o: json.dumps(o, ensure_ascii=False)


def load(p):
    t = p.read_text("utf-8-sig").strip()
    return json.loads(t[t.find("{"): t.rfind("}") + 1])


def stages(d):
    out = []
    while (d / f"stage_{len(out) + 1}.json").exists():
        out.append(json.loads((d / f"stage_{len(out) + 1}.json").read_text("utf-8")))
    return out


def history(sc, done):
    lines = []
    for k, st in enumerate(done, 1):
        lines.append(f"Stage {k}:")
        for a, d in st["actions"].items():
            lines.append(f"  {a} -> {d['chosen_action']}: {d.get('justification', '')}")
        for m in st.get("messages", []):
            lines.append(f"  message from {m['from']} to {m['to']}: {m['text']}")
        lines.append(f"  referee summary: {st.get('summary', '')}")
        lines.append(f"  state after stage {k}: {J(st['state'])}")
    return lines or ["(nothing has happened yet; the event in the situation begins in stage 1)"]


def common(sc, done, n):
    state = done[-1]["state"] if done else sc["initial_state"]
    cond = done[-1].get("conditions", []) if done else []
    lines = ["Situation: " + sc["description"], f"Each stage lasts: {sc['stage_length']}. This is stage {n} of 5.", "",
             "Variables (0 to 100), meaning, current value:"]
    lines += [f"- {v}: {sc['variable_labels'].get(v, '')} = {state[v]}" for v in sc["initial_state"]]
    lines += ["", "Conditions in force now: " + (J(cond) if cond else "none"), "", "History so far:"] + history(sc, done)
    return lines, state


mode = sys.argv[1]
for sid in IDS:
    sc = json.loads((HERE / sid / "scenario.json").read_text("utf-8"))
    d = HERE / "v2" / sid
    (d / "prompts").mkdir(parents=True, exist_ok=True)
    (d / "answers").mkdir(exist_ok=True)
    done = stages(d)
    n = len(done) + 1
    actors = [a for a in sc["initial_agents"] if a["name"] != "environment"]
    own = sc["action_owner"]
    eff = sc["action_tradeoffs"]
    if n > 5:
        print(sid, "already complete")
        continue
    base, state = common(sc, done, n)

    if mode == "actors":
        for a in actors:
            mine = [x for x in sc["allowed_actions"] if own.get(x) == a["name"]]
            lines = ["You are playing one seat in a step-by-step scenario exercise. Play it the way this actor really would.", ""]
            lines += base
            lines += ["", f"Your seat: {a['name']} ({a['role']}). Goals: {J(a['objectives'])}. Character: {a['personality']}",
                      "Other seats: " + ", ".join(f"{b['name']} ({b['role']})" for b in sc["initial_agents"] if b["name"] != a["name"]),
                      "", "Your own actions, with the typical direct effect of each in one stage:"]
            lines += [f"- {x}: {J(eff.get(x, {}))}" for x in mine] + ["- hold_position: {}"]
            lines += ["", "Actions of the other seats (for reference): "
                      + J({b["name"]: [x for x in sc["allowed_actions"] if own.get(x) == b["name"]] for b in sc["initial_agents"] if b["name"] != a["name"]})]
            prev = done[-1].get("plans", {}).get(a["name"]) if done else None
            lines += ["", "Your private plan note from the previous stage: " + (prev or "none")]
            lines += ["", "Task: choose the ONE action your seat takes in this stage (one of your own actions, or hold_position).",
                      "Think about where you want to be by stage 5, not only about this stage. Do not keep repeating an action",
                      "that has stopped working. Consider what the others want and whether a deal, a threat or a concession",
                      "would serve your goals; you may send one short public message to one other seat.", "",
                      "Reply with one JSON object only:",
                      '{"chosen_action": "...", "justification": "<Persian, at most 40 words>", "message_to": "<seat name or empty>",',
                      ' "message": "<Persian, at most 25 words, or empty>", "plan": "<Persian, at most 50 words: private note to your later self>"}']
            (d / "prompts" / f"stage_{n}_{a['name']}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{sid}: stage {n} actor prompts written")
        continue

    # both later modes need the actor answers
    acts, problems = {}, []
    for a in actors:
        p = d / "answers" / f"stage_{n}_{a['name']}.json"
        if not p.exists():
            problems.append(f"missing {p.name}")
            continue
        r = load(p)
        if own.get(r.get("chosen_action")) not in (a["name"], "any"):
            problems.append(f"{a['name']} chose {r.get('chosen_action')} which is not its action")
        acts[a["name"]] = r
    if problems:
        print(f"{sid}: stage {n} PROBLEMS:", problems)
        continue

    if mode == "referee":
        envs = [x for x in sc["allowed_actions"] if own.get(x) == "environment"]
        lines = ["You are the neutral referee of a step-by-step scenario exercise, and you also play the outside world.",
                 "Four actors have each chosen an action for this stage. You decide what actually happens.", ""]
        lines += base
        lines += ["", "Seats and their goals:"] + [f"- {a['name']} ({a['role']}): {J(a['objectives'])}" for a in actors]
        lines += ["", "Typical direct effect of each action in one stage (guidance, not arithmetic):"]
        lines += [f"- {x} [{own.get(x)}]: {J(eff.get(x, {}))}" for x in sc["allowed_actions"]]
        lines += ["", "Known influences between variables (direction only): "
                  + "; ".join(f"{l['from']} {'raises' if l['weight'] > 0 else 'lowers'} {l['to']}" for l in sc["causal_links"])]
        lines += ["", f"Actions chosen in stage {n}:"]
        for a, r in acts.items():
            lines.append(f"- {a} -> {r['chosen_action']}: {r.get('justification', '')}")
            if r.get("message") and r.get("message_to"):
                lines.append(f"  message from {a} to {r['message_to']}: {r['message']}")
        lines += ["", "Your tasks:",
                  f"1. Outside event: choose one of {J(envs)} or hold_position. Choose what would most plausibly happen in this",
                  "   stage given the state, not what makes a good story; in many stages nothing notable happens.",
                  "2. State after this stage: a new value for EVERY variable, with the cause.",
                  "   - Values stay within 0 to 100.",
                  f"   - No variable moves more than {CAP} points in one stage, unless a chosen action's listed effect on it is larger.",
                  "   - A condition in force keeps acting every stage until an action ends it (a ban keeps holding legal supply",
                  "     down while it stands; a strike keeps holding freight down while it lasts).",
                  "   - Effects can be delayed, saturate, reinforce or cancel one another. Use judgment about how such a",
                  "     situation really moves in a stage of this length; do not just add up the listed effects.",
                  "   - Do not favour any seat, and do not invent convenient rescues.",
                  "3. Conditions in force after this stage: short Persian phrases (measures, deals, shortages that persist).",
                  "4. A summary of the stage in Persian, at most 50 words.", "",
                  "Reply with one JSON object only:",
                  '{"environment": {"chosen_action": "...", "justification": "<Persian, at most 40 words>"},',
                  ' "state": {"<variable>": {"value": <number>, "why": "<Persian, at most 20 words>"}, ... every variable ...},',
                  ' "conditions": ["...", ...], "summary": "..."}']
        (d / "prompts" / f"stage_{n}_referee.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{sid}: stage {n} referee prompt written |", {a: r["chosen_action"] for a, r in acts.items()})
        continue

    # close
    p = d / "answers" / f"stage_{n}_referee.json"
    if not p.exists():
        print(f"{sid}: stage {n} PROBLEMS: missing referee answer")
        continue
    r = load(p)
    env = r.get("environment", {})
    chosen = [x["chosen_action"] for x in acts.values()] + [env.get("chosen_action")]
    if own.get(env.get("chosen_action")) not in ("environment", "any"):
        problems.append(f"outside event {env.get('chosen_action')} is not an environment action")
    new = {}
    for v in sc["initial_state"]:
        x = r.get("state", {}).get(v)
        val = x.get("value") if isinstance(x, dict) else x
        if not isinstance(val, (int, float)):
            problems.append(f"{v} missing")
            continue
        cap = max([CAP] + [abs(eff.get(c, {}).get(v, 0)) for c in chosen if c])
        if not 0 <= val <= 100:
            problems.append(f"{v}={val} outside 0..100")
        if abs(val - state[v]) > cap + 1e-9:
            problems.append(f"{v} moved {val - state[v]:+.0f}, cap {cap}")
        new[v] = round(float(val), 1)
    if problems:
        print(f"{sid}: stage {n} PROBLEMS:", problems)
        continue
    actions = {"environment": {"chosen_action": env["chosen_action"], "justification": env.get("justification", "")}}
    for a, x in acts.items():
        actions[a] = {"chosen_action": x["chosen_action"], "justification": x.get("justification", "")}
    stage = {"actions": actions, "state": new, "why": {v: (r["state"][v].get("why", "") if isinstance(r["state"][v], dict) else "") for v in new},
             "conditions": r.get("conditions", []), "summary": r.get("summary", ""),
             "messages": [{"from": a, "to": x["message_to"], "text": x["message"]} for a, x in acts.items() if x.get("message") and x.get("message_to")],
             "plans": {a: x.get("plan", "") for a, x in acts.items()}}
    (d / f"stage_{n}.json").write_text(json.dumps(stage, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sid}: stage {n} closed | event: {env['chosen_action']} | state: {J(new)}")
    if n == 5:
        allst = stages(d)
        (d / "run.json").write_text(json.dumps(
            {"states": [sc["initial_state"]] + [s["state"] for s in allst], "turns": [s["actions"] for s in allst]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{sid}: run.json written")
