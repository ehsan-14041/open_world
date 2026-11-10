"""
Step-by-step scenario runner: a language model writes the world and the actors' moves, the
repository's engine keeps the state and carries each move forward through the links.

    python research/episode_sim/episode_sim.py run <folder>

<folder> holds scenario.json and stage_1.json .. stage_N.json (whichever exist so far). The run
is replayed from the start every time, so it is deterministic and a stage file can be rewritten.
Output: the state after every stage, and what moved each variable.

This explores what COULD follow from stated assumptions. It is not a forecast: every link and
every effect size is the model's own judgement, and the engine only does the bookkeeping.

scenario.json
  {"title": "...", "stage_label": "هر مرحله = دو هفته",
   "variables": [{"id": "x", "label": "...", "initial": 0..100, "meaning": "100 یعنی ..."}],
   "links": [{"from": "x", "to": "y", "direction": "+" | "-", "strength": "weak|medium|strong", "delay": 0..2, "why": "..."}],
   "actors": [{"id": "a", "label": "...", "goal": "..."}],
   "shock": {"label": "...", "targets": {"x": -60}, "stages": 2}}

stage_k.json
  {"moves": [{"actor": "a", "move": "...", "why": "...", "stages": 1..N,
              "effects": [{"variable": "y", "direction": "+" | "-", "size": "small|medium|large"}]}]}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from event_sim.engine import Intervention, SimulationConfig, build_simulation  # noqa: E402
from event_sim.evidence import validate_module  # noqa: E402
from event_sim.registry import _registry  # noqa: E402
from event_sim.schemas import EventDefinition, WorldModule  # noqa: E402
from event_sim.world_builder import build_slice  # noqa: E402

STRENGTH = {"weak": 0.2, "medium": 0.5, "strong": 0.8}
SIZE = {"small": 5.0, "medium": 12.0, "large": 25.0}
RESPONSE = 0.6            # share of the gap to the pressure closed in one stage


def build(scn: dict):
    mid = "episode_" + str(abs(hash(json.dumps(scn, sort_keys=True))))
    module = WorldModule.from_dict({
        "id": mid, "domain": "exploratory", "time_unit": "stages", "title": scn["title"],
        "variables": [{
            "id": v["id"], "label": v["label"], "unit": "0..100", "baseline": float(v["initial"]), "scale": 100.0,
            "range": {"min": 0.0, "max": 100.0}, "dynamics": {"response": RESPONSE},
            "observability": "derived", "observability_class": "latent",
            "observability_note": "Written by a language model for one scenario; no series exists.",
            "status": "ai_hypothesis"} for v in scn["variables"]],
        "edges": [{
            "source": e["from"], "target": e["to"], "polarity": "positive" if e["direction"] == "+" else "negative",
            "effect": {k: STRENGTH[e["strength"]] for k in ("low", "central", "high")},
            "lag": {"min": int(e.get("delay", 0)), "max": int(e.get("delay", 0)), "unit": "stages"},
            "evidence": [], "status": "ai_hypothesis", "confidence": "low", "mechanism": e.get("why", "")}
            for e in scn["links"]],
        "axes": [], "interventions": []})
    validate_module(module)
    _registry()[mid] = module
    return build_slice([mid], question=scn["title"])


def run(folder: Path) -> dict:
    scn = json.loads((folder / "scenario.json").read_text("utf-8"))
    ids = {v["id"] for v in scn["variables"]}
    actors = {a["id"]: a["label"] for a in scn["actors"]}
    stages = []
    k = 1
    while (folder / f"stage_{k}.json").exists():
        stages.append(json.loads((folder / f"stage_{k}.json").read_text("utf-8")))
        k += 1
    n = max(len(stages), 1)
    shock = scn["shock"]
    events = [EventDefinition(id="shock", label=shock["label"], targets={k: float(v) for k, v in shock["targets"].items()},
                              start_turn=1, duration=int(shock["stages"]), shape="step", status="user_assumption")]
    sim = build_simulation(build_slice_cached(scn), config=SimulationConfig(turns=n), events=events)
    label = {v["id"]: v["label"] for v in scn["variables"]}
    out = {"title": scn["title"], "stage_label": scn.get("stage_label", ""),
           "initial": {v["id"]: float(v["initial"]) for v in scn["variables"]}, "stages": []}
    for t in range(1, len(stages) + 1):
        moves = stages[t - 1].get("moves", [])
        for i, m in enumerate(moves):
            eff = {}
            for e in m.get("effects", []):
                if e["variable"] not in ids:
                    raise SystemExit(f"stage {t}: unknown variable {e['variable']!r}")
                eff[e["variable"]] = eff.get(e["variable"], 0.0) + (1 if e["direction"] == "+" else -1) * SIZE[e["size"]]
            sim.interventions.append(Intervention(id=f"s{t}m{i}", magnitude=1.0, start_turn=t,
                                                  duration=int(m.get("stages", 1)), effects_per_unit=eff,
                                                  label=m["move"], status="ai_hypothesis"))
        rec = sim.step()
        state = {vid: round(val, 1) for vid, val in sim.state().items()}
        why = {}
        for row in rec.get("variables", []):
            parts = []
            for c in row.get("contributions", []) or []:
                if not c.get("negligible"):
                    parts.append(f"{label[c['source']]} ({'+' if c['contribution'] > 0 else '−'})")
            if parts:
                why[row["variable"]] = parts
        out["stages"].append({"stage": t, "shock_active": t <= int(shock["stages"]),
                              "moves": [{"actor": actors.get(m["actor"], m["actor"]), "move": m["move"], "why": m.get("why", "")}
                                        for m in moves], "state": state, "pushed_by": why})
    out["labels"] = label
    return out


_SLICES: dict[str, object] = {}


def build_slice_cached(scn):
    key = json.dumps(scn, sort_keys=True)
    if key not in _SLICES:
        _SLICES[key] = build(scn)
    return _SLICES[key]


def show(res: dict) -> str:
    L = res["labels"]
    lines = [f"# {res['title']}", "", res["stage_label"], ""]
    head = "| متغیر | شروع | " + " | ".join(f"مرحله {s['stage']}" for s in res["stages"]) + " | تغییر کل |"
    lines += [head, "|" + "---|" * (len(res["stages"]) + 3)]
    for vid, lab in L.items():
        vals = [s["state"][vid] for s in res["stages"]]
        last = vals[-1] if vals else res["initial"][vid]
        lines.append(f"| {lab} | {res['initial'][vid]:g} | " + " | ".join(f"{v:g}" for v in vals)
                     + f" | {last - res['initial'][vid]:+.0f} |")
    for s in res["stages"]:
        lines += ["", f"## مرحله {s['stage']}" + (" (شوک هنوز برقرار است)" if s["shock_active"] else "")]
        for m in s["moves"]:
            lines.append(f"- **{m['actor']}:** {m['move']}" + (f" — {m['why']}" if m["why"] else ""))
        if s["pushed_by"]:
            lines.append("")
            lines.append("از راه رابطه‌ها: " + "؛ ".join(f"{L[v]} ← {'، '.join(p)}" for v, p in s["pushed_by"].items()))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    folder = Path(sys.argv[2])
    res = run(folder)
    (folder / "run.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    text = show(res)
    (folder / "run.md").write_text(text, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
