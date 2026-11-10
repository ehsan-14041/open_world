"""
Forecast test 2 (PROTOCOL_DOSSIER.md): score the dossier-narrator arm D against the existing L and L2.

    python research/forecast_test/dossier_run.py check    # count usable dossiers / answers per batch
    python research/forecast_test/dossier_run.py score    # results_dossier.json
"""
import json
import sys
from pathlib import Path

import forecast_test as F
import types; A = types.SimpleNamespace(CUTOFF="2026-06-30", BATCH=30)

B = F.HERE / "batches"


def load(prefix, key):
    out = {}
    for f in sorted(B.glob(prefix + "_*.json")):
        try:
            t = f.read_text("utf-8-sig")
            out.update(json.loads(t[t.find("{"): t.rfind("}") + 1]).get(key, {}))
        except ValueError:
            print("unreadable:", f.name)
    return out


def main():
    sample, base, _ = F.select(A.CUTOFF)
    d1, d = load("D1", "dossiers"), load("D", "answers")
    if sys.argv[1] == "check":
        for i in range(0, len(sample), A.BATCH):
            ids = [q["id"] for q in sample[i:i + A.BATCH]]
            print(f"batch {i // A.BATCH:02d}: dossiers {sum(x in d1 for x in ids)}/{len(ids)}, "
                  f"answers {sum(F._prob(d.get(x)) is not None for x in ids if isinstance(d.get(x), dict))}/{len(ids)}")
        return
    l = load("L", "answers")
    eng = json.loads((B / "_engine.json").read_text("utf-8"))
    rows = []
    for q in sample:
        v = l.get(q["id"])
        pl = F._prob(v) if isinstance(v, dict) else F._prob({"probability": v})
        pd = F._prob(d.get(q["id"])) if isinstance(d.get(q["id"]), dict) else None
        if pl is None or pd is None or q["id"] not in eng:
            continue
        rows.append((q, pl, eng[q["id"]]["L2"], pd))
    ys = [r[0]["yes"] for r in rows]
    L, L2, D = [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows]
    prices = json.loads(F.PRICES.read_text("utf-8")) if F.PRICES.exists() else {}
    mk = [(prices.get(r[0]["id"]), r[0]["yes"]) for r in rows]
    mk = [(p, y) for p, y in mk if isinstance(p, (int, float))]
    dl, dl2 = F.paired(D, L, ys), F.paired(D, L2, ys)
    verdict = ("pass" if dl["ci95"][1] < 0 and dl2["ci95"][1] < 0 else
               "method hurts" if dl["ci95"][0] > 0 else "no detectable difference")
    extreme = lambda ps: round(sum(p <= 0.1 or p >= 0.9 for p in ps) / len(ps), 3)
    out = {"model": "Claude Opus 5.5 as sub-agents, batches of 30", "n_sampled": len(sample), "n_scored": len(rows),
           "share_yes": round(sum(ys) / len(ys), 3),
           "brier": {"half": 0.25, "market_on_priced": round(F.brier(*zip(*mk)), 4) if mk else None, "n_priced": len(mk),
                     "L": round(F.brier(L, ys), 4), "L2": round(F.brier(L2, ys), 4), "D": round(F.brier(D, ys), 4)},
           "D_minus_L": dl, "D_minus_L2": dl2,
           "mean_abs_change_L_to_D": round(sum(abs(a - b) for a, b in zip(D, L)) / len(rows), 4),
           "share_extreme_forecasts": {"L": extreme(L), "L2": extreme(L2), "D": extreme(D)},
           "verdict": verdict}
    (F.HERE / "results_dossier.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


main()
