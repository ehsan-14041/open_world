"""
Phase 3 of PROTOCOL.md: tables, paired differences with cluster-bootstrap intervals, decision rules.

    python analyze.py           # reads scores.json, writes analysis.json and analysis.md
"""
import json
import random
import sys
from collections import defaultdict

import ib
import policies

sys.stdout.reconfigure(encoding="utf-8")
D = json.loads((ib.HERE / "scores.json").read_text("utf-8"))
META, S = D["meta"], D["scores"]
RELS = sorted(META)
SEED, REPS = 20261116, 10000
PRIMARY = policies.PRIMARY
PUB_OR = "pub:OR (capped base stock)"
LLM_ARMS = [a for a in S if a.startswith("pub:") and a != PUB_OR]
MAIN = ["OR", "Rolling", "Cusum", "SupplyAware", "Rolling+Supply", "Cusum+Supply"]
LEADS = ["lead_time_0", "lead_time_4", "lead_time_stochastic"]

clusters = defaultdict(list)
for r in RELS:
    clusters[META[r]["cluster"]].append(r)
CL = sorted(clusters)


def unclipped(arm, r):
    s = S[arm][r]
    return s["reward"] / s["ub"] if s["ub"] else 0.0


METRIC = {"norm": lambda a, r: S[a][r]["norm"], "norm_clair": lambda a, r: S[a][r]["norm_clair"],
          "unclipped": unclipped, "reward": lambda a, r: S[a][r]["reward"],
          "service": lambda a, r: S[a][r]["service"], "holding": lambda a, r: S[a][r]["holding"]}


def mean(arm, rels, metric="norm"):
    return sum(METRIC[metric](arm, r) for r in rels) / len(rels)


def paired(a, b, rels, metric="norm"):
    """Mean of (a - b) over rels with a 95% interval from resampling demand trajectories."""
    keep = set(rels)
    per = {}
    for c in CL:
        ds = [METRIC[metric](a, r) - METRIC[metric](b, r) for r in clusters[c] if r in keep]
        if ds:
            per[c] = (sum(ds), len(ds))
    keys = sorted(per)
    tot = sum(v[0] for v in per.values()) / sum(v[1] for v in per.values())
    rng = random.Random(SEED)
    boots = []
    for _ in range(REPS):
        s = n = 0.0
        for _ in keys:
            x = per[keys[rng.randrange(len(keys))]]
            s += x[0]
            n += x[1]
        boots.append(s / n)
    boots.sort()
    return {"diff": round(tot, 4), "ci95": [round(boots[int(0.025 * REPS)], 4), round(boots[int(0.975 * REPS)], 4)],
            "n": len(rels), "clusters": len(keys)}


def sel(**kw):
    return [r for r in RELS if all(META[r][k] == v for k, v in kw.items())]


out = {"n": len(RELS), "clusters": len(CL), "primary": PRIMARY}
ARMS = MAIN + LLM_ARMS

# ---- level tables ---------------------------------------------------------------------------------------------
out["overall"] = {a: {m: round(mean(a, RELS, m), 4) for m in ("norm", "unclipped", "norm_clair", "service")}
                  | {"reward": round(mean(a, RELS, "reward"), 1), "holding": round(mean(a, RELS, "holding"), 1)} for a in ARMS}
out["by_cell"] = {f"{k}/{ls}": {a: round(mean(a, sel(kind=k, lead_setting=ls)), 4) for a in ARMS}
                  for k in ("synthetic", "real") for ls in LEADS}
out["by_lead"] = {ls: {a: round(mean(a, sel(lead_setting=ls)), 4) for a in ARMS} for ls in LEADS}
fams = sorted({META[r]["family"] for r in RELS if META[r]["kind"] == "synthetic"})
out["by_family"] = {f: {a: round(mean(a, sel(family=f)), 4) for a in ARMS} for f in fams}
out["by_family_fixed_lead"] = {f: {a: round(mean(a, [r for r in sel(family=f) if META[r]["lead_setting"] != "lead_time_stochastic"]), 4)
                                   for a in ARMS} for f in fams}
out["by_rho"] = {str(rho): {a: round(mean(a, sel(rho=rho)), 4) for a in ARMS} for rho in (0.5, 0.8, 0.95)}

# ---- the pre-declared comparisons -------------------------------------------------------------------------------
out["primary_vs"] = {}
for comp in ["OR"] + LLM_ARMS:
    d = paired(PRIMARY, comp, RELS)
    cells = {f"{k}/{ls}": paired(PRIMARY, comp, sel(kind=k, lead_setting=ls)) for k in ("synthetic", "real") for ls in LEADS}
    fam = {f: paired(PRIMARY, comp, sel(family=f)) for f in fams}
    signs = [c["diff"] > 0 for c in cells.values()]
    fam_same = sum((v["diff"] > 0) == (d["diff"] > 0) for v in fam.values())
    out["primary_vs"][comp] = {
        "all": d, "matches(>-0.01)": d["ci95"][0] > -0.01, "exceeds(>0)": d["ci95"][0] > 0,
        "cells": cells, "families": fam,
        "robust": (all(signs) or not any(signs)) and fam_same >= 8,
        "cells_same_sign": all(signs) or not any(signs), "families_same_sign_as_overall": fam_same,
        "sens_unclipped": paired(PRIMARY, comp, RELS, "unclipped"), "sens_clairvoyant": paired(PRIMARY, comp, RELS, "norm_clair"),
        "raw_reward": paired(PRIMARY, comp, RELS, "reward")}
out["every_baseline_vs_or"] = {b: {"all": paired(b, "OR", RELS)} | {ls: paired(b, "OR", sel(lead_setting=ls)) for ls in LEADS} for b in MAIN[1:]}

# ---- share of the OR-to-LLM gap closed by one change ----------------------------------------------------------------
out["gap_closed"] = {}
for comp in LLM_ARMS:
    out["gap_closed"][comp] = {}
    for scope, rels in [("all", RELS)] + [(ls, sel(lead_setting=ls)) for ls in LEADS]:
        gap = mean(comp, rels) - mean("OR", rels)
        out["gap_closed"][comp][scope] = {"llm_minus_or": round(gap, 4)} | {
            b: (round((mean(b, rels) - mean("OR", rels)) / gap, 2) if abs(gap) > 0.01 else None) for b in MAIN[1:]}

# ---- sensitivity -----------------------------------------------------------------------------------------------------
out["sensitivity_overall_norm"] = {c.name: round(mean(c.name, RELS), 4) for c in policies.SENSITIVITY}
(ib.HERE / "analysis.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

# ---- a readable dump --------------------------------------------------------------------------------------------------
L = []
short = lambda a: a.replace("pub:", "")  # noqa: E731


def table(title, rows, cols, get):
    L.extend([f"### {title}", "", "| | " + " | ".join(short(c) for c in cols) + " |", "|---|" + "---|" * len(cols)])
    for r in rows:
        L.append(f"| {short(r)} | " + " | ".join(get(r, c) for c in cols) + " |")
    L.append("")


table("Overall (1,320 instances)", ARMS, ["norm", "unclipped", "norm_clair", "service", "reward", "holding"],
      lambda a, c: str(out["overall"][a][c]))
table("Normalised reward by data type and lead-time setting", ARMS, list(out["by_cell"]), lambda a, c: f'{out["by_cell"][c][a]:.3f}')
table("Synthetic demand patterns, fixed lead times only (L=0 and L=4)", ARMS, fams, lambda a, c: f'{out["by_family_fixed_lead"][c][a]:.3f}')
table("Synthetic demand patterns, all lead-time settings", ARMS, fams, lambda a, c: f'{out["by_family"][c][a]:.3f}')
table("By critical ratio", ARMS, list(out["by_rho"]), lambda a, c: f'{out["by_rho"][c][a]:.3f}')
f = lambda d: f'{d["diff"]:+.4f} [{d["ci95"][0]:+.4f}, {d["ci95"][1]:+.4f}]'  # noqa: E731
table(f"{PRIMARY} minus comparator, normalised reward, 95% cluster-bootstrap interval", ["OR"] + LLM_ARMS,
      ["all", "matches", "exceeds", "robust", "unclipped", "clairvoyant-normalised", "raw reward"],
      lambda a, c: {"all": f(out["primary_vs"][a]["all"]), "matches": str(out["primary_vs"][a]["matches(>-0.01)"]),
                    "exceeds": str(out["primary_vs"][a]["exceeds(>0)"]), "robust": str(out["primary_vs"][a]["robust"]),
                    "unclipped": f(out["primary_vs"][a]["sens_unclipped"]),
                    "clairvoyant-normalised": f(out["primary_vs"][a]["sens_clairvoyant"]),
                    "raw reward": f'{out["primary_vs"][a]["raw_reward"]["diff"]:+.0f}'}[c])
table(f"{PRIMARY} minus comparator by cell", ["OR"] + LLM_ARMS, list(out["by_cell"]), lambda a, c: f(out["primary_vs"][a]["cells"][c]))
table("Each baseline minus OR", MAIN[1:], ["all"] + LEADS, lambda a, c: f(out["every_baseline_vs_or"][a][c]))
for comp in LLM_ARMS:
    table(f"Share of the gap ({short(comp)} minus OR) closed by each baseline", MAIN[1:], ["all"] + LEADS,
          lambda a, c, comp=comp: f'{out["gap_closed"][comp][c][a]} (gap {out["gap_closed"][comp][c]["llm_minus_or"]:+.3f})')
table("Sensitivity runs, overall normalised reward", list(out["sensitivity_overall_norm"]), ["norm"],
      lambda a, c: str(out["sensitivity_overall_norm"][a]))
(ib.HERE / "analysis.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
