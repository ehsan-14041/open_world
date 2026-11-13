"""
Test half of PROTOCOL_V2.md. Run once.

    python test_half.py     # writes test_half.json and test_half.md
"""
import json
import random
import sys
from collections import defaultdict
from types import SimpleNamespace

import pandas as pd

import ib
import policies
import policies2

sys.stdout.reconfigure(encoding="utf-8")
TEST = json.loads((ib.HERE / "split.json").read_text("utf-8"))["test"]
insts = {r: ib.load(r) for r in TEST}
SEED, REPS = 20261117, 10000
NEW, OLD = "Cusum+Supply2", "Cusum+Supply"

S = {}
for cls in (policies.OR, policies.CusumSupply, policies2.FROZEN):
    S[cls.name] = {r: ib.score(ib.simulate(cls(SimpleNamespace(train=i.train, promised=i.promised)), i), i) for r, i in insts.items()}
PUB = sorted(p.name for p in (ib.VENDOR / "results").iterdir() if p.is_dir() and not p.name.startswith("OR"))
for name in PUB:
    S[name] = {r: ib.score([int(x) for x in pd.read_csv(ib.VENDOR / "results" / name / "results" / r / "results.csv")["order_quantity"]], i)
               for r, i in insts.items()}

M = {"norm": lambda a, r: S[a][r]["norm"], "unclipped": lambda a, r: S[a][r]["reward"] / S[a][r]["ub"] if S[a][r]["ub"] else 0.0,
     "norm_clair": lambda a, r: S[a][r]["norm_clair"]}
clusters = defaultdict(list)
for r, i in insts.items():
    clusters[i.cluster].append(r)
CL = sorted(clusters)
STO = [r for r in TEST if insts[r].lead_setting == "lead_time_stochastic"]
SCOPES = {"all": TEST, "stochastic": STO, "fixed": [r for r in TEST if r not in set(STO)],
          "stochastic/synthetic": [r for r in STO if insts[r].kind == "synthetic"], "stochastic/real": [r for r in STO if insts[r].kind == "real"]}


def mean(a, rels, m="norm"):
    return round(sum(M[m](a, r) for r in rels) / len(rels), 4)


def paired(a, b, rels, m="norm"):
    keep = set(rels)
    per = [(sum(M[m](a, r) - M[m](b, r) for r in clusters[c] if r in keep), sum(1 for r in clusters[c] if r in keep)) for c in CL]
    per = [x for x in per if x[1]]
    tot = sum(x[0] for x in per) / sum(x[1] for x in per)
    rng = random.Random(SEED)
    boots = []
    for _ in range(REPS):
        s = n = 0.0
        for _ in per:
            x = per[rng.randrange(len(per))]
            s += x[0]
            n += x[1]
        boots.append(s / n)
    boots.sort()
    return {"diff": round(tot, 4), "ci95": [round(boots[int(0.025 * REPS)], 4), round(boots[int(0.975 * REPS)], 4)]}


ARMS = ["OR", OLD, NEW] + PUB
out = {"n_test": len(TEST), "clusters": len(CL), "n_stochastic": len(STO),
       "levels": {sc: {a: {m: mean(a, rels, m) for m in M} for a in ARMS} for sc, rels in SCOPES.items()},
       "old_minus": {c: {sc: paired(OLD, c, SCOPES[sc]) for sc in ("all", "stochastic")} for c in ["OR"] + PUB},
       "new_minus": {c: {sc: {m: paired(NEW, c, SCOPES[sc], m) for m in M} for sc in SCOPES} for c in ["OR", OLD] + PUB}}

G_LLM, G_HYB = "Gemini 3 Flash (LLM)", "Gemini 3 Flash (OR→LLM)"
q1a, q1b = out["old_minus"][G_LLM]["all"], out["old_minus"]["OR"]["all"]
q2 = out["new_minus"][G_HYB]["stochastic"]["norm"]
out["verdict"] = {
    "Q1_first_step_holds_on_test_half": q1a["ci95"][0] > 0 and q1b["ci95"][0] > 0,
    "Q2_stochastic_new_minus_gemini_hybrid": q2,
    "Q2": "gap closed" if q2["ci95"][0] > -0.01 else ("the hybrid keeps an advantage" if q2["ci95"][1] < 0 else "undecided"),
    "Q2_sensitivity": {m: out["new_minus"][G_HYB]["stochastic"][m] for m in ("unclipped", "norm_clair")},
    "Q2_all_instances": {m: out["new_minus"][G_HYB]["all"][m] for m in M}}
(ib.HERE / "test_half.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

f = lambda d: f'{d["diff"]:+.4f} [{d["ci95"][0]:+.4f}, {d["ci95"][1]:+.4f}]'  # noqa: E731
L = [f"Test half: {len(TEST)} instances, {len(CL)} trajectories, {len(STO)} stochastic-lead.", "",
     "### Levels (benchmark metric / unclipped / clairvoyant-normalised)", "", "| | " + " | ".join(SCOPES) + " |", "|---|" + "---|" * len(SCOPES)]
for a in ARMS:
    L.append(f"| {a} | " + " | ".join("{norm:.3f} / {unclipped:.3f} / {norm_clair:.3f}".format(**out["levels"][sc][a]) for sc in SCOPES) + " |")
L += ["", f"### {NEW} minus comparator, benchmark metric", "", "| | " + " | ".join(SCOPES) + " |", "|---|" + "---|" * len(SCOPES)]
for c in out["new_minus"]:
    L.append(f"| {c} | " + " | ".join(f(out["new_minus"][c][sc]["norm"]) for sc in SCOPES) + " |")
L += ["", f"### {NEW} minus comparator, sensitivity metrics", "", "| | all: unclipped | all: clairvoyant | stochastic: unclipped | stochastic: clairvoyant |", "|---|---|---|---|---|"]
for c in out["new_minus"]:
    x = out["new_minus"][c]
    L.append(f"| {c} | {f(x['all']['unclipped'])} | {f(x['all']['norm_clair'])} | {f(x['stochastic']['unclipped'])} | {f(x['stochastic']['norm_clair'])} |")
L += ["", f"### {OLD} (first step, unchanged) minus comparator, benchmark metric", "", "| | all | stochastic |", "|---|---|---|"]
for c in out["old_minus"]:
    L.append(f"| {c} | {f(out['old_minus'][c]['all'])} | {f(out['old_minus'][c]['stochastic'])} |")
L += ["", "### Verdict", "", "```", json.dumps(out["verdict"], indent=1, ensure_ascii=False), "```"]
(ib.HERE / "test_half.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
