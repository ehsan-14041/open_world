"""
The same test with sub-agents instead of an API (see the end of PROTOCOL.md).

    python research/forecast_test/agent_run.py export     # batches/q_NN.json for stages L and L2
    python research/forecast_test/agent_run.py engine     # after L2: run the census, write batches/e_NN.json
    python research/forecast_test/agent_run.py score      # after LE2: results_opus55_agents.json
"""
import json, sys
from pathlib import Path
import forecast_test as F

CUTOFF, BATCH = "2026-06-30", 30
B = F.HERE / "batches"


def export():
    B.mkdir(exist_ok=True)
    sample, base, n = F.select(CUTOFF)
    for i in range(0, len(sample), BATCH):
        rows = [{k: q[k] for k in ("id", "question", "rules", "start", "close")} for q in sample[i:i + BATCH]]
        (B / f"q_{i // BATCH:02d}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(n, "eligible;", len(sample), "sampled;", len(list(B.glob("q_*.json"))), "batches")


def _load(prefix):
    out = {}
    for f in sorted(B.glob(prefix + "_*.json")):
        try:
            d = json.loads(f.read_text("utf-8"))
        except ValueError:
            print("unreadable:", f.name); continue
        out.update(d.get("answers", d))
    return out


def engine():
    sample, _, _ = F.select(CUTOFF)
    byid = {q["id"]: q for q in sample}
    l2 = _load("L2")
    kept = {}
    for i in range(0, len(sample), BATCH):
        rows = []
        for q in sample[i:i + BATCH]:
            raw = l2.get(q["id"])
            cd = F.clean_drivers(raw) if isinstance(raw, dict) else None
            if cd is None or F._prob(raw) is None:
                continue
            tendency, drivers = cd
            c = F.census(tendency, drivers, F.weeks(q))
            kept[q["id"]] = {"L2": F._prob(raw), "LE1": max(0.02, min(0.98, c["share_yes"])), "census": c,
                             "tendency": tendency, "drivers": drivers}
            rows.append({**{k: q[k] for k in ("id", "question", "rules", "start", "close")},
                         "your_drivers": [{"name": d["name"], "toward": "yes" if d["sign"] > 0 else "no",
                                           "strength": d["strength"], "level": d["level"], "delay_weeks": d["lag"]} for d in drivers],
                         "simulation": {"combinations": c["n"], "share_ending_on_yes_side": round(c["share_yes"], 3),
                                        "side_with_drivers_as_stated": "yes" if c["centre_yes"] else "no",
                                        "drivers_whose_strength_alone_flips_it": c["flips"]}})
        (B / f"e_{i // BATCH:02d}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (B / "_engine.json").write_text(json.dumps(kept), encoding="utf-8")
    print(len(kept), "of", len(sample), "have usable drivers")


def score():
    sample, base, _ = F.select(CUTOFF)
    l, le2 = _load("L"), _load("LE2")
    eng = json.loads((B / "_engine.json").read_text("utf-8"))
    rows = []
    for q in sample:
        pl = F._prob({"probability": l.get(q["id"])}) if not isinstance(l.get(q["id"]), dict) else F._prob(l[q["id"]])
        ple = F._prob({"probability": le2.get(q["id"])}) if not isinstance(le2.get(q["id"]), dict) else F._prob(le2[q["id"]])
        if pl is None or ple is None or q["id"] not in eng:
            continue
        rows.append((q, pl, eng[q["id"]]["L2"], eng[q["id"]]["LE1"], ple))
    ys = [r[0]["yes"] for r in rows]
    arms = {"L": [r[1] for r in rows], "L2": [r[2] for r in rows], "LE1": [r[3] for r in rows], "LE2": [r[4] for r in rows]}
    rate = sum(q["yes"] for q in base) / len(base)
    prices = json.loads(F.PRICES.read_text("utf-8")) if F.PRICES.exists() else {}
    for r in rows:
        F.market_price(r[0], prices)
    F.PRICES.write_text(json.dumps(prices), encoding="utf-8")
    priced = [(prices[r[0]["id"]], r[0]["yes"]) for r in rows if prices.get(r[0]["id"]) is not None]
    out = {"model": "Claude Opus 5.5 as sub-agents, batches of 30", "cutoff": CUTOFF, "n_sampled": len(sample),
           "n_scored": len(rows), "n_dropped": len(sample) - len(rows), "share_yes": round(sum(ys) / len(ys), 3),
           "brier": {"half": 0.25, "base_rate": round(F.brier([rate] * len(ys), ys), 4),
                     "market": round(F.brier([p for p, _ in priced], [y for _, y in priced]), 4),
                     **{a: round(F.brier(p, ys), 4) for a, p in arms.items()}},
           "LE2_minus_L2": F.paired(arms["LE2"], arms["L2"], ys), "LE2_minus_L": F.paired(arms["LE2"], arms["L"], ys),
           "L2_minus_L": F.paired(arms["L2"], arms["L"], ys),
           "mean_abs_change_L2_to_LE2": round(sum(abs(a - b) for a, b in zip(arms["LE2"], arms["L2"])) / len(ys), 4)}
    out["pass"] = out["LE2_minus_L2"]["ci95"][1] < 0 and out["LE2_minus_L"]["ci95"][1] < 0
    (F.HERE / "results_opus55_agents.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"export": export, "engine": engine, "score": score}[sys.argv[1]]()
