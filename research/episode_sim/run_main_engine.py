"""
Run the repository's ORIGINAL simulation loop (simulation/loop.py) on a scenario, with the agents'
decisions supplied from files instead of a language-model API.

    python research/episode_sim/run_main_engine.py <folder>

<folder>/scenario.json is a scenario in the repository's own format. <folder>/turn_K.json holds, for
turn K, each agent's reply to the strategic prompt of the engine: {agent_name: {chosen_action, ...}}.
The loop is replayed from the start for as many turns as have a file. Everything else (parsing,
validation, governance, causal propagation, provenance) is the original code path of the engine.
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

folder = Path(sys.argv[1])
scenario = json.loads((folder / "scenario.json").read_text("utf-8"))
turns = []
while (folder / f"turn_{len(turns) + 1}.json").exists():
    turns.append(json.loads((folder / f"turn_{len(turns) + 1}.json").read_text("utf-8")))

L.DRY_RUN = False                 # the settings default is dry-run when no API key is configured
L.MAX_DELTA = float(scenario.get("max_delta", L.MAX_DELTA))   # the default cap of 10 per action cannot express a large shock
asked = []
loop = None


def responder(prompt, system="", schema=None, **kw):
    m = re.search(r"\(name: ([a-z_]+)\)", prompt) or re.search(r'You are the agent "([a-z_]+)"', system or "")
    turn = loop.world.turn + 1 if loop is not None else 0
    asked.append([turn, m.group(1) if m else None, schema is not None])
    if schema is not None or not m or not (1 <= turn <= len(turns)):
        return {} if schema is not None else ""
    d = turns[turn - 1].get(m.group(1))
    if not d:
        return ""
    return "### ACTION_JSON\n" + json.dumps(dict({"relation_updates": []}, **d), ensure_ascii=False)


L.llm_service_call = responder
log = io.StringIO()
states = []
with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    loop = L.SimulationLoop(scenario_data=scenario, dry_run=False)
    states.append(dict(loop.world.global_state))
    for _ in range(len(turns)):
        loop.step()
        states.append(dict(loop.world.global_state))

(folder / "engine_log.txt").write_text(log.getvalue(), encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
flags = ("WARNING", "fallback", "rejected", "degraded", "invalid")
warn = [ln for ln in log.getvalue().splitlines() if any(f.lower() in ln.lower() for f in flags)]
names = list(scenario["initial_state"])
print("| variable | start | " + " | ".join(f"turn {i}" for i in range(1, len(states))) + " |")
print("|" + "---|" * (len(states) + 1))
for v in names:
    print(f"| {v} | " + " | ".join(f"{float(s.get(v, float('nan'))):.0f}" for s in states) + " |")
print("\nprompts answered:", len(asked), "| flagged engine log lines:", len(warn))
for w in warn[:14]:
    print("  ", w[:240])
(folder / "run.json").write_text(json.dumps({"states": states, "asked": asked}, ensure_ascii=False, indent=1, default=str),
                                 encoding="utf-8")
