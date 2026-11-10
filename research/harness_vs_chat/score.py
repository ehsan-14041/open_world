"""Open the key and score the blind judgments.   python research/harness_vs_chat/score.py"""
import json
import sys
from pathlib import Path

V = sys.argv[1] if len(sys.argv) > 1 else ""          # "", "v2" or "v3"
V2 = bool(V)
P = Path(__file__).resolve().parent / (f"pairs_{V}" if V else "pairs")
sys.stdout.reconfigure(encoding="utf-8")
key = json.loads((P / "key.json").read_text("utf-8"))
judges = [json.loads(f.read_text("utf-8-sig")) for f in sorted(P.glob("judge_*.json"))]
dims = ["behaviour", "consistency", "insight", "usefulness"]
wins = {"harness": 0, "chat": 0, "tie": 0}
tot = {"harness": {d: [] for d in dims}, "chat": {d: [] for d in dims}}
rows = []
for sid, k in key.items():
    prefs = []
    for j in judges:
        p = j[sid]["prefer"]
        arm = k[p] if p in k else "tie"
        wins[arm] += 1
        prefs.append(arm)
        for letter in "XY":
            for d in dims:
                tot[k[letter]][d].append(j[sid][letter][d])
    rows.append({"scenario": sid, "preferences": prefs, "reasons": [j[sid]["why"] for j in judges]})
mean = {a: {d: round(sum(v) / len(v), 2) for d, v in tot[a].items()} for a in tot}
n = wins["harness"]
verdict = "build" if n >= 9 else ("no clear advantage" if n >= 4 else "plain chat is at least as good")
out = {"judgments": sum(wins.values()), "preferred": wins, "mean_scores": mean, "rule_outcome": verdict, "by_scenario": rows}
(P.parent / (f"results_{V}.json" if V else "results.json")).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
