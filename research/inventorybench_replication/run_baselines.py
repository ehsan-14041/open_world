"""
Phase 2 of PROTOCOL.md: run every baseline on every instance and score it.

    python run_baselines.py     # writes scores.json (per instance, per arm) and baseline_orders.json

The published arms (OR and the nine LLM arms) are scored here too, from the order sequences in
vendor/InventoryBench/results/, so that every number in the analysis comes from one scorer.
The new baselines are additionally re-scored with the repository's own evaluator as a cross-check.
"""
import json
import sys
from types import SimpleNamespace

import pandas as pd

import ib
import policies

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(ib.VENDOR / "eval"))
from evaluate_results import simulate_and_score  # noqa: E402

rels = ib.rels()
insts = {r: ib.load(r) for r in rels}
KEEP = ("reward", "profit", "holding", "service", "norm", "norm_clair", "ub", "clair", "ordered")

scores, orders_out, worst = {}, {}, 0.0
for sub in sorted(p for p in (ib.VENDOR / "results").iterdir() if p.is_dir()):
    name = "pub:" + sub.name
    scores[name] = {}
    for r in rels:
        o = [int(x) for x in pd.read_csv(sub / "results" / r / "results.csv")["order_quantity"]]
        scores[name][r] = {k: ib.score(o, insts[r])[k] for k in KEEP}
    print(name, round(sum(v["norm"] for v in scores[name].values()) / len(rels), 4), flush=True)

for cls in [policies.OR] + policies.BASELINES + policies.SENSITIVITY:
    scores[cls.name], orders_out[cls.name] = {}, {}
    for r in rels:
        inst = insts[r]
        # the policy is built from the training samples and the promised lead time only: it cannot read test.csv
        o = ib.simulate(cls(SimpleNamespace(train=inst.train, promised=inst.promised)), inst)
        s = ib.score(o, inst)
        scores[cls.name][r] = {k: s[k] for k in KEEP}
        orders_out[cls.name][r] = o
        if cls in policies.BASELINES:
            t = simulate_and_score(pd.DataFrame({"period": range(1, inst.T + 1), "order_quantity": o}),
                                   pd.read_csv(ib.BENCH / r / "test.csv"), inst.item)
            worst = max(worst, abs(t["total_reward"] - s["reward"]), abs(t["normalized_reward"] - s["norm"]))
    print(cls.name, round(sum(v["norm"] for v in scores[cls.name].values()) / len(rels), 4), flush=True)

meta = {r: {"kind": i.kind, "lead_setting": i.lead_setting, "family": i.family, "cluster": i.cluster,
            "rho": round(i.p[0] / (i.p[0] + i.h[0]), 2)} for r, i in insts.items()}
(ib.HERE / "scores.json").write_text(json.dumps({"meta": meta, "scores": scores}), encoding="utf-8")
(ib.HERE / "baseline_orders.json").write_text(json.dumps(orders_out), encoding="utf-8")
print("max difference between ib.score and the repository evaluator on the new baselines:", worst)
