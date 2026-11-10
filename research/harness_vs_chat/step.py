"""
Step the repository's ORIGINAL simulation loop one stage at a time, with every seat answered from a file.

    python research/harness_vs_chat/step.py prompts <folder>   # replay finished turns, write next turn's prompts
    python research/harness_vs_chat/step.py merge <folder>     # answers/turn_N_<agent>.json -> turn_N.json
    python research/harness_vs_chat/step.py run <folder>       # replay all turns, write run.json

<folder>/scenario.json is in the repository's scenario format. Engine code is not modified.
"""
import contextlib
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import simulation.loop as L  # noqa: E402

mode, folder = sys.argv[1], Path(sys.argv[2])
sys.stdout.reconfigure(encoding="utf-8")
scenario = json.loads((folder / "scenario.json").read_text("utf-8"))
agents = [a["name"] for a in scenario["initial_agents"]]


def load_turns():
    out = []
    while (folder / f"turn_{len(out) + 1}.json").exists():
        out.append(json.loads((folder / f"turn_{len(out) + 1}.json").read_text("utf-8")))
    return out


if mode == "merge":
    n = len(load_turns()) + 1
    merged, missing = {}, []
    for a in agents:
        p = folder / "answers" / f"turn_{n}_{a}.json"
        if not p.exists():
            missing.append(a)
            continue
        txt = p.read_text("utf-8-sig").strip()
        txt = txt[txt.find("{"): txt.rfind("}") + 1]
        merged[a] = json.loads(txt)
    if missing:
        sys.exit(f"turn {n}: missing answers for {missing}")
    (folder / f"turn_{n}.json").write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{folder.name}: merged turn {n}:", {a: merged[a].get("chosen_action") for a in agents})
    sys.exit(0)

turns = load_turns()
target = len(turns) + 1 if mode == "prompts" else None
L.DRY_RUN = False
L.MAX_DELTA = float(scenario.get("max_delta", L.MAX_DELTA))
loop = None
dumped = []


def context(name, turn):
    """What the engine's own prompt leaves out (see PROTOCOL.md, amendment 1): the story, the clock, the
    seat's own goals, what each action does, and what everyone did so far."""
    me = next(a for a in scenario["initial_agents"] if a["name"] == name)
    keep = list(scenario["initial_state"])
    lines = ["=== CONTEXT (added by the harness) ===",
             "Situation: " + scenario["description"],
             f"Each stage lasts: {scenario.get('stage_length', 'not stated')}. This is stage {turn} of 5.",
             f"Your seat: {name} ({me['role']}). Goals: {json.dumps(me['objectives'], ensure_ascii=False)}. "
             f"Character: {me['personality']}",
             "Other seats: " + ", ".join(f"{a['name']} ({a['role']})" for a in scenario["initial_agents"] if a["name"] != name),
             "What each action does to the variables in one stage: "
             + json.dumps(scenario["action_tradeoffs"], ensure_ascii=False),
             "Which seat each action belongs to: " + json.dumps(scenario.get("action_owner", {}), ensure_ascii=False),
             "Variable meanings: " + json.dumps(scenario.get("variable_labels", {}), ensure_ascii=False)]
    for k, t in enumerate(turns[:turn - 1], 1):
        lines.append(f"Stage {k}: " + "; ".join(
            f"{a} -> {t[a].get('chosen_action')} ({t[a].get('justification', '')})" for a in agents if a in t))
        lines.append(f"  state after stage {k}: "
                     + json.dumps({v: round(float(states[k].get(v, 0))) for v in keep}))
    lines.append("Choose only an action that your own seat could really take. Set expected_effect to the listed "
                 "effect of the action you choose. Write justification and causal_chain in Persian.")
    return "\n".join(lines) + "\n"


def responder(prompt, system="", schema=None, **kw):
    m = re.search(r"\(name: ([a-z_0-9]+)\)", prompt) or re.search(r'You are the agent "([a-z_0-9]+)"', system or "")
    turn = loop.world.turn + 1 if loop is not None else 0
    if schema is not None or not m:
        return {} if schema is not None else ""
    name = m.group(1)
    if target is not None and turn == target:
        d = folder / "prompts"
        d.mkdir(exist_ok=True)
        if name not in dumped:          # the engine asks again to repair an empty reply; keep the first prompt
            (d / f"turn_{turn}_{name}.txt").write_text(
                context(name, turn) + "\n=== SYSTEM ===\n" + (system or "") + "\n\n=== PROMPT ===\n" + prompt,
                encoding="utf-8")
            dumped.append(name)
        return ""
    if not (1 <= turn <= len(turns)) or not turns[turn - 1].get(name):
        return ""
    return "### ACTION_JSON\n" + json.dumps(dict({"relation_updates": []}, **turns[turn - 1][name]), ensure_ascii=False)


L.llm_service_call = responder
log = io.StringIO()
states = []
with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    loop = L.SimulationLoop(scenario_data=scenario, dry_run=False)
    states.append(dict(loop.world.global_state))
    for _ in range(len(turns) + (1 if mode == "prompts" else 0)):
        loop.step()
        states.append(dict(loop.world.global_state))

if mode == "prompts":
    print(f"{folder.name}: turn {target} prompts written for", dumped,
          "| state now:", {k: round(float(v)) for k, v in states[len(turns)].items() if k in scenario["initial_state"]})
else:
    flags = ("WARNING", "fallback", "rejected", "degraded", "invalid")
    warn = [ln for ln in log.getvalue().splitlines() if any(f.lower() in ln.lower() for f in flags)]
    (folder / "engine_log.txt").write_text(log.getvalue(), encoding="utf-8")
    keep = list(scenario["initial_state"])
    (folder / "run.json").write_text(json.dumps(
        {"states": [{k: round(float(s.get(k, 0)), 1) for k in keep} for s in states], "turns": turns,
         "flagged": warn[:40]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{folder.name}: {len(turns)} turns | flagged log lines: {len(warn)}")
    for v in keep:
        print(f"  {v}: " + " -> ".join(f"{float(s.get(v, 0)):.0f}" for s in states))
    for w in warn[:8]:
        print("   !", w[:200])
