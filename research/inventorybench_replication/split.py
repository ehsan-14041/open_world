"""Draw the design/test split of PROTOCOL_V2.md.   python split.py   -> split.json"""
import json
import random

import ib

clusters = {}
for r in ib.rels():
    parts = r.split("/")
    kind = "real" if parts[0].startswith("real") else "synthetic"
    c = ("real/" + parts[2]) if kind == "real" else "/".join(parts[2:4]) + "/" + parts[4].split("_")[0]
    clusters.setdefault(c, {"kind": kind, "rels": []})["rels"].append(r)

rng = random.Random(20261117)
half = {}
for kind in ("synthetic", "real"):
    cs = sorted(c for c, v in clusters.items() if v["kind"] == kind)
    rng.shuffle(cs)
    for i, c in enumerate(cs):
        half[c] = "design" if i < len(cs) // 2 else "test"

out = {"seed": 20261117,
       "design": sorted(r for c, v in clusters.items() if half[c] == "design" for r in v["rels"]),
       "test": sorted(r for c, v in clusters.items() if half[c] == "test" for r in v["rels"]),
       "clusters": {h: sum(1 for c in half if half[c] == h) for h in ("design", "test")}}
(ib.HERE / "split.json").write_text(json.dumps(out, indent=0), encoding="utf-8")
print(out["clusters"], len(out["design"]), len(out["test"]))
