"""
Phase 0 and 1 of PROTOCOL.md: verify the benchmark and reproduce its stored results.

    python phase0.py            # all checks; writes phase0_results.json
"""
import csv
import json
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

import ib
import policies

sys.stdout.reconfigure(encoding="utf-8")
V = ib.VENDOR
sys.path.insert(0, str(V / "eval"))
from evaluate_results import simulate_and_score  # noqa: E402  (the repository's own evaluator)

out = {"pinned_sha": ib.PINNED_SHA,
       "vendor_head": subprocess.run(["git", "-C", str(V), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
       "vendor_dirty": bool(subprocess.run(["git", "-C", str(V), "status", "--porcelain", "--untracked-files=no"],
                                           capture_output=True, text=True).stdout.strip())}
assert out["vendor_head"] == ib.PINNED_SHA, "vendor clone is not at the pinned commit"

rels = ib.rels()
insts = {r: ib.load(r) for r in rels}

# ---- the data ---------------------------------------------------------------------------------------
cells = defaultdict(lambda: {"n": 0, "T": Counter(), "train_len": Counter(), "lead": Counter(), "p_h_constant": True})
for r, i in insts.items():
    c = cells[f"{i.kind}/{i.lead_setting}"]
    c["n"] += 1
    c["T"][i.T] += 1
    c["train_len"][len(i.train)] += 1
    for v in i.lead:
        c["lead"][str(v)] += 1
    c["p_h_constant"] &= len(set(i.p)) == 1 and len(set(i.h)) == 1
out["data"] = {k: {**v, "T": dict(v["T"]), "train_len": dict(v["train_len"]), "lead": dict(v["lead"])} for k, v in sorted(cells.items())}
by_cluster = defaultdict(list)
for i in insts.values():
    by_cluster[i.cluster].append(i)
out["clusters"] = {"n": len(by_cluster), "sizes": dict(Counter(len(v) for v in by_cluster.values())),
                   "same_demand_within_cluster": sum(len({tuple(i.demand) for i in v}) == 1 for v in by_cluster.values())}
out["cost_ratios"] = dict(Counter(round(i.p[0] / (i.p[0] + i.h[0]), 2) for i in insts.values()))

# ---- P0-a: benchmark copies beside the model logs ------------------------------------------------------
copies = {}
for model in sorted(p.name for p in (V / "empirical_results").iterdir() if p.is_dir()):
    bad = missing = 0
    for r in rels:
        for f in ("train.csv", "test.csv"):
            q = V / "empirical_results" / model / r / f
            if not q.exists():
                missing += 1
            elif ib.sha(q) != ib.sha(ib.BENCH / r / f):
                bad += 1
    copies[model] = {"differing_files": bad, "missing_files": missing}
out["P0a_benchmark_copies"] = copies

# ---- P0-b / P0-c: published order sequences, three ways ---------------------------------------------------
ARM = {"LLM": "llm", "LLM→OR": "llm_to_or", "OR→LLM": "or_to_llm"}
MODEL_DIR = {"Gemini 3 Flash": "gemini-3-flash_bench", "GPT-5 Mini": "gpt-5-mini_bench", "Grok 4.1 Fast": "grok-4.1-fast_bench"}
published = {}
subs = {}
for sub in sorted(p for p in (V / "results").iterdir() if p.is_dir()):
    rows, worst_eval, worst_log, n_log, neg = {}, 0.0, 0.0, 0, 0
    m = re.match(r"(.+) \((.+)\)$", sub.name)
    model, arm = m.group(1), m.group(2)
    for r in rels:
        inst = insts[r]
        rdf = pd.read_csv(sub / "results" / r / "results.csv")
        orders = [int(x) for x in rdf["order_quantity"]]
        mine = ib.score(orders, inst)
        theirs = simulate_and_score(rdf, pd.read_csv(ib.BENCH / r / "test.csv"), inst.item)
        worst_eval = max(worst_eval, abs(mine["reward"] - theirs["total_reward"]), abs(mine["norm"] - theirs["normalized_reward"]))
        neg += mine["reward"] < 0
        rows[r] = mine
        log_dirs = [MODEL_DIR[model]] if model in MODEL_DIR else list(MODEL_DIR.values())
        for md in log_dirs:
            lg = json.loads((V / "empirical_results" / md / r / "benchmark_results.json").read_text("utf-8"))
            key = ARM.get(arm, "or")
            rw = (lg["results"].get(key) or {}).get("rewards") or []
            if rw:
                n_log += 1
                worst_log = max(worst_log, abs(rw[0] - mine["reward"]))
    sj = json.loads((sub / "scores.json").read_text("utf-8"))
    mean = sum(x["norm"] for x in rows.values()) / len(rows)
    subs[sub.name] = {"n": len(rows), "mean_norm_recomputed": round(mean, 6), "scores_json_overall": round(sj["overall_score"], 6),
                      "max_abs_diff_vs_repo_evaluator": worst_eval, "max_abs_reward_diff_vs_logs": worst_log,
                      "n_log_comparisons": n_log, "instances_with_negative_reward": int(neg)}
    published[sub.name] = {r: [int(x) for x in pd.read_csv(sub / "results" / r / "results.csv")["order_quantity"]] for r in rels}
out["P0bc_published_arms"] = subs

# ---- P1-b: the OR replica against the published OR orders, all instances -------------------------------------
or_pub = published["OR (capped base stock)"]
mism = [r for r in rels if ib.simulate(policies.OR(insts[r]), insts[r]) != or_pub[r]]
out["P1b_or_replica"] = {"instances": len(rels), "order_sequences_differing": len(mism), "examples": mism[:5]}

# ---- P1-a: the repository's own run_or.py on a stratified sample ---------------------------------------------
rng = random.Random(20261116)
sample = []
for kind in ("real", "synthetic"):
    for ls in ib.PROMISED:
        pool = [r for r in rels if insts[r].kind == kind and insts[r].lead_setting == ls]
        if kind == "synthetic":      # five stationary, five non-stationary
            stat = [r for r in pool if insts[r].family == "p01_stationary_iid"]
            sample += rng.sample(stat, 5) + rng.sample([r for r in pool if r not in stat], 5)
        else:
            sample += rng.sample(pool, 10)
runs = []
for r in sample:
    d = ib.BENCH / r
    res = subprocess.run([sys.executable, "scripts/run_or.py", "--demand-file", str(d / "test.csv"), "--real-instance-train",
                          str(d / "train.csv"), "--promised-lead-time", str(insts[r].promised)],
                         cwd=V, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         env={**__import__("os").environ, "PYTHONPATH": str(V), "PYTHONIOENCODING": "utf-8"})
    m = re.search(r"Total Reward \(OR Baseline\): \$(-?[\d.]+)", res.stdout)
    orig = float(m.group(1)) if m else None
    runs.append({"instance": r, "run_or_py": orig, "replica": ib.score(ib.simulate(policies.OR(insts[r]), insts[r]), insts[r])["reward"],
                 "published": ib.score(or_pub[r], insts[r])["reward"], "lost_orders_in_instance": sum(v == ib.INF for v in insts[r].lead)})
out["P1a_original_or_runs"] = {"n": len(runs), "failed_to_run": sum(x["run_or_py"] is None for x in runs),
                               "max_abs_diff_original_vs_published": max(abs(x["run_or_py"] - x["published"]) for x in runs if x["run_or_py"] is not None),
                               "max_abs_diff_original_vs_replica": max(abs(x["run_or_py"] - x["replica"]) for x in runs if x["run_or_py"] is not None),
                               "runs": runs}

# ---- the benchmark's normaliser against the feasible clairvoyant ------------------------------------------------
gap = defaultdict(list)
for i in insts.values():
    s = ib.score([0] * i.T, i)
    gap[f"{i.kind}/{i.lead_setting}"].append(s["clair"] / s["ub"] if s["ub"] else 1.0)
out["clairvoyant_over_normaliser"] = {k: {"mean": round(sum(v) / len(v), 4), "min": round(min(v), 4)} for k, v in sorted(gap.items())}

(ib.HERE / "phase0_results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
short = {k: v for k, v in out.items() if k != "P1a_original_or_runs"}
short["P1a_original_or_runs"] = {k: v for k, v in out["P1a_original_or_runs"].items() if k != "runs"}
print(json.dumps(short, indent=1, ensure_ascii=False))
