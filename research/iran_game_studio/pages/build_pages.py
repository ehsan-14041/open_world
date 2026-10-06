"""
Build the two visual reports into reports/iran_game_studio/, as pages that open on their own.

    python research/iran_game_studio/study.py      # results.json (census, parity)  ~25 min
    python research/iran_game_studio/outlook.py    # outlook.json                    ~2 min
    python research/iran_game_studio/pages/build_pages.py

    engine_game_report.html             what a studio should do, in plain language
    engine_game_report_technical.html   the first, technical version of the same report
    game_outlook.html                   one year ahead under five scenarios

Every figure on both pages comes from the engine runs above; nothing is typed in by hand except
the historical benchmark sources, which REPORT.md lists.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import study as S  # noqa: E402

OUT = S.REPORTS
SHELL = ('<!doctype html>\n<html lang="fa" dir="rtl">\n<head>\n<meta charset="utf-8">\n'
         '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
         '<style>body{margin:0}[hidden]{display:none!important}</style>\n</head>\n<body>\n{page}\n</body>\n</html>\n')


def _embed(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<" + chr(92) + "/")


def engine_report_data() -> dict:
    """The data behind engine_game_report.html: central runs, census, decider grid, ad sweep, benchmark."""
    results = json.loads((OUT / "results.json").read_text("utf-8"))
    out = {"scen": [], "census": results["census"], "parity": results["parity_worst_abs_diff"],
           "sha": results["module_sha256_12"]}
    for sid, sc in S.SCENARIOS.items():
        row = {"id": sid, "cash": {}, "floor": None, "end": {}, "neg": {}}
        for o, op in S.OPTIONS.items():
            L = S.ledger(S.fast_run(sc["events"], op, {}), op, sc.get("commission"))
            m = S.metrics(L)
            row["cash"][o] = [round(c) for c in L["cash"][::3]]
            row["end"][o] = round(m["cash_end"])
            row["neg"][o] = m["first_negative_day"]
            if o == "A":
                row["floor"] = round(m["rev_min_pct"], 1)
        out["scen"].append(row)

    war = S.SCENARIOS["S5_war_combo"]
    ser = S.fast_run(war["events"], S.OPTIONS["A"], {})
    out["mech"] = {k: [round(v, 1) for v in ser[k][::2]] for k in ("connectivity", "active_players", "payer_conversion",
                                                                  "play_habit", "price_level", "studio_wage")}
    L = S.ledger(S.fast_run(war["events"], S.OPTIONS["A"], {}), S.OPTIONS["A"])
    out["war_rev"] = [round(100 * r / L["rev"][0], 1) for r in L["rev"][::2]]
    out["war_cost"] = [round(100 * c / L["cost"][0], 1) for c in L["cost"][::2]]
    out["war_players"] = [round(100 * p, 1) for p in L["players"][::2]]

    grid: dict[str, dict[str, int]] = {}
    settings = [next(a.settings for a in S.SLICE.axes if a.id == ax) for ax in S.CENSUS_AXES]
    for combo in itertools.product(*settings):
        axes = dict(zip(S.CENSUS_AXES, combo))
        res = {o: S.metrics(S.ledger(S.fast_run(war["events"], op, axes), op))["cash_end"]
               for o, op in S.OPTIONS.items()}
        cell = grid.setdefault(axes["content_dependence"] + "|" + axes["price_sensitivity"], {})
        w = max(res, key=res.get)
        cell[w] = cell.get(w, 0) + 1
    out["grid"] = grid

    out["ann"] = {}
    for sid in ("S2_fx100", "S5_war_combo", "S0_calm"):
        sc = S.SCENARIOS[sid]
        best = max((S.metrics(S.ledger(S.fast_run(sc["events"], S.OPTIONS[o], {}), S.OPTIONS[o]))["cash_end"], o)
                   for o in "ABC")
        pts = []
        for k in (0.1, 0.2, 0.3, 0.4, 0.5):
            op = dict(S.OPTIONS["D"], effects={"more_ads": {"play_habit": -k}})
            pts.append(round(S.metrics(S.ledger(S.fast_run(sc["events"], op, {}), op))["cash_end"]))
        out["ann"][sid] = {"d": pts, "best": round(best[0]), "best_opt": best[1]}
    out["bench"] = S.benchmark()
    return out


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    viz = engine_report_data()
    (OUT / "engine_game_report_data.json").write_text(json.dumps(viz, indent=1), encoding="utf-8")
    page = (HERE / "engine_report_template.html").read_text("utf-8").replace("__VIZ__", _embed(viz))
    (OUT / "engine_game_report.html").write_text(SHELL.replace("{page}", page), encoding="utf-8")
    page = (HERE / "engine_report_technical_template.html").read_text("utf-8").replace("__VIZ__", _embed(viz))
    (OUT / "engine_game_report_technical.html").write_text(SHELL.replace("{page}", page), encoding="utf-8")

    outlook = json.loads((OUT / "outlook.json").read_text("utf-8"))
    page = (HERE / "outlook_template.html").read_text("utf-8").replace("__DATA__", _embed(outlook))
    (OUT / "game_outlook.html").write_text(SHELL.replace("{page}", page), encoding="utf-8")
    for f in ("engine_game_report.html", "engine_game_report_technical.html", "game_outlook.html"):
        print(OUT / f)


if __name__ == "__main__":
    build()
