"""
Design half of PROTOCOL_V2.md: explore the Supply2 family. Loads design-half instances only.

    python design.py        # appends every candidate tried to design_log.json
"""
import itertools
import json
import sys
from types import SimpleNamespace

import ib
import policies
import policies2

sys.stdout.reconfigure(encoding="utf-8")
DESIGN = json.loads((ib.HERE / "split.json").read_text("utf-8"))["design"]
insts = {r: ib.load(r) for r in DESIGN}
STO = [r for r in DESIGN if insts[r].lead_setting == "lead_time_stochastic"]
FIX = [r for r in DESIGN if insts[r].lead_setting != "lead_time_stochastic"]


def run(cls, rels):
    tot = unc = 0.0
    for r in rels:
        i = insts[r]
        s = ib.score(ib.simulate(cls(SimpleNamespace(train=i.train, promised=i.promised)), i), i)
        tot += s["norm"]
        unc += s["reward"] / s["ub"] if s["ub"] else 0.0
    return round(tot / len(rels), 4), round(unc / len(rels), 4)


log_path = ib.HERE / "design_log.json"
log = json.loads(log_path.read_text("utf-8")) if log_path.exists() else []
done = {x["name"] for x in log}


def trial(cls, note=""):
    if cls.name in done:
        return next(x for x in log if x["name"] == cls.name)
    sto, sto_u = run(cls, STO)
    row = {"name": cls.name, "stochastic_norm": sto, "stochastic_unclipped": sto_u, "note": note}
    log.append(row)
    done.add(cls.name)
    log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
    return row


print("design half:", len(DESIGN), "instances;", len(STO), "stochastic-lead")
for ref in (policies.OR, policies.SupplyAware, policies.CusumSupply):
    print(trial(ref, "reference from the first step"))

grid = itertools.product(("hard", "expected"), ("mean", "max"), (True, False), (1.0, 1.5, 2.0, None), (0.0, 1.0, 2.0))
rows = [trial(policies2.member(PIPE=p, LEAD=ld, INFLATE=inf, CAPM=c, KAPPA=k), "grid 1") for p, ld, inf, c, k in grid]
rows.sort(key=lambda x: -x["stochastic_norm"])
for x in rows[:12]:
    print(x)
print("...")
for x in rows[-3:]:
    print(x)

print("--- grid 2: no inflation, hard pipeline ---")
grid2 = itertools.product(("mean", "max"), (0.8, 0.9, 1.0, 1.1), (-0.5, 0.0, 0.5), ("max", "mean"))
rows2 = [trial(policies2.member(PIPE="hard", LEAD=ld, INFLATE=False, CAPM=c, KAPPA=k, HORIZON=hz), "grid 2") for ld, c, k, hz in grid2]
rows2.sort(key=lambda x: -x["stochastic_norm"])
for x in rows2[:10]:
    print(x)

print("--- fixed-lead check on the design half (not the selection criterion) ---")
for cls in (policies.CusumSupply, policies2.member(PIPE="hard", LEAD="mean", INFLATE=False, CAPM=0.8, KAPPA=-0.5, HORIZON="mean"),
            policies2.member(PIPE="hard", LEAD="mean", INFLATE=False, CAPM=1.0, KAPPA=-0.5, HORIZON="mean")):
    print(cls.name, "fixed-lead norm, unclipped:", run(cls, FIX), "| all design:", run(cls, DESIGN))
