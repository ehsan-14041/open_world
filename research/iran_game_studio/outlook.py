"""
One year ahead (Mehr 1405 -> Mehr 1406) under five scenarios, at the level of the industry's
domestic mobile studios. Conditional projections: "if this happens, the engine says this follows".
The engine cannot say how likely a scenario is, and nothing here does.

    python research/iran_game_studio/outlook.py

Uses the same model and the same verified fast step as study.py. Today = 100 for every index, so
the scenarios are stated as changes from today, whatever today's dollar rate is.
"""

from __future__ import annotations

import itertools
import json
import time

import study as S

H = 365
STEP = 15            # the dollar path is held in 15-day steps


def fx_events(path):
    """Hold the dollar on a path given as a function of the day (deviation from today, in %)."""
    out = []
    for d0 in range(1, H + 1, STEP):
        out.append(S.ev(f"fx{d0}", {"fx_rate": float(path(d0 + STEP / 2))}, d0, STEP))
    return out


def ramp(total, start=0, end=H):
    return lambda d: 0.0 if d < start else total * min(1.0, (d - start) / max(1, end - start))


SCENARIOS = {
    "trend": {"label": "ادامهٔ روند فعلی",
              "story": "دلار در طول سال آرام‌آرام ۴۰٪ بالا می‌رود؛ قطعی بزرگی رخ نمی‌دهد.",
              "events": fx_events(ramp(40))},
    "fx_jump": {"label": "جهش ارزی",
                "story": "دلار در ماه سوم ناگهان ۶۰٪ می‌پرد و تا آخر سال به دو برابر امروز می‌رسد؛ اینترنت عادی است.",
                "events": fx_events(lambda d: (10 * min(1, d / 75)) + (60 if d >= 75 else 0) + (30 * max(0, d - 75) / 290))},
    "shutdown": {"label": "قطعی دوباره",
                 "story": "روند فعلی دلار، به‌علاوهٔ دو هفته قطع کامل اینترنت در ماه چهارم و دو ماه اینترنت کند بعد از آن.",
                 "events": fx_events(ramp(40)) + [S.ev("cut", {"connectivity": -90.0}, 105, 14),
                                                   S.ev("thr", {"connectivity": -40.0}, 119, 60)]},
    "crisis": {"label": "بحران شدید (مثل ۱۴۰۴)",
               "story": "در ماه دوم سه هفته قطع کامل و سه ماه اینترنت کند؛ دلار هم‌زمان ۷۰٪ می‌پرد و تا آخر سال دو برابر می‌شود.",
               "events": fx_events(lambda d: (70 if d >= 45 else 0) + (30 * max(0, d - 45) / 320))
                         + [S.ev("cut", {"connectivity": -90.0}, 45, 21), S.ev("thr", {"connectivity": -40.0}, 66, 90)]},
    "easing": {"label": "گشایش نسبی",
               "story": "دلار در سه ماه اول ۱۵٪ ارزان می‌شود و بعد ثابت می‌ماند؛ اینترنت عادی است.",
               "events": fx_events(lambda d: -15 * min(1, d / 90))},
}

#: Three kinds of domestic studio, monthly, millions of tomans. Illustrative.
STUDIOS = {
    "fragile": {"label": "کوچک و شکننده", "iap_gross": 450.0, "commission": 0.30, "ads": 85.0,
                "wages": 300.0, "usd_costs": 80.0, "other": 40.0, "cash": 500.0},
    "typical": {"label": "متوسط", **S.STUDIO},
    "solid": {"label": "بزرگ و محکم", "iap_gross": 6000.0, "commission": 0.30, "ads": 1000.0,
              "wages": 3000.0, "usd_costs": 700.0, "other": 400.0, "cash": 25000.0},
}

AXES = S.CENSUS_AXES
COMBOS = list(itertools.product(*[next(a.settings for a in S.SLICE.axes if a.id == ax) for ax in AXES]))


def monthly(series, k=10):
    return [round(series[min(len(series) - 1, i)], 1) for i in range(0, H + 1, k)]


def industry_paths(events, axes):
    """Indices for a typical studio that changes nothing: players, revenue, real revenue, costs."""
    ser = S.fast_run(events, S.OPTIONS["A"], axes)
    L = S.ledger(ser, S.OPTIONS["A"])
    rev = [100 * r / L["rev"][0] for r in L["rev"]]
    cost = [100 * c / L["cost"][0] for c in L["cost"]]
    real = [rv / (cpi) for rv, cpi in zip(rev, L["cpi"])]
    players = [100 * p for p in L["players"]]
    return {"players": players, "rev": rev, "real_rev": real, "cost": cost,
            "cpi": [100 * c for c in L["cpi"]], "fx": ser["fx_rate"]}


def run():
    t0 = time.time()
    out = {"scenarios": {}, "studios": {k: v["label"] for k, v in STUDIOS.items()}, "axes": AXES, "n": len(COMBOS)}
    for sid, sc in SCENARIOS.items():
        central = industry_paths(sc["events"], {})
        bands = {k: [[1e9, -1e9] for _ in range(0, H + 1, 10)] for k in ("players", "rev", "real_rev", "cost")}
        survive = {st: {"A": 0, "adapt": 0} for st in STUDIOS}
        best_choice = {o: 0 for o in "ABCD"}
        year_sums = {"rev": [], "real_rev": [], "players": []}
        for combo in COMBOS:
            axes = dict(zip(AXES, combo))
            series = {o: S.fast_run(sc["events"], op, axes) for o, op in S.OPTIONS.items()}
            # industry paths (typical studio, no change) for the uncertainty band
            L = S.ledger(series["A"], S.OPTIONS["A"])
            rev = [100 * r / L["rev"][0] for r in L["rev"]]
            cost = [100 * c / L["cost"][0] for c in L["cost"]]
            paths = {"players": [100 * p for p in L["players"]], "rev": rev,
                     "real_rev": [r / c for r, c in zip(rev, L["cpi"])], "cost": cost}
            for k, p in paths.items():
                for j, d in enumerate(range(0, H + 1, 10)):
                    v = p[min(d, H)]
                    bands[k][j][0] = min(bands[k][j][0], v); bands[k][j][1] = max(bands[k][j][1], v)
            year_sums["rev"].append(sum(rev[1:]) / H)
            year_sums["real_rev"].append(sum(paths["real_rev"][1:]) / H)
            year_sums["players"].append(sum(paths["players"][1:]) / H)
            for st, prof in STUDIOS.items():
                ends = {}
                for o, op in S.OPTIONS.items():
                    m = S.metrics(S.ledger(series[o], op, studio=prof))
                    ends[o] = m
                if ends["A"]["first_negative_day"] is None:
                    survive[st]["A"] += 1
                best = max(ends, key=lambda o: ends[o]["cash_end"])
                if ends[best]["first_negative_day"] is None:
                    survive[st]["adapt"] += 1
                if st == "typical":
                    best_choice[best] += 1
        def stats(xs):
            xs = sorted(xs); return {"min": round(xs[0], 1), "max": round(xs[-1], 1)}
        out["scenarios"][sid] = {
            "label": sc["label"], "story": sc["story"],
            "central": {k: monthly(v) for k, v in central.items()},
            "central_year": {"rev": round(sum(central["rev"][1:]) / H, 1), "real_rev": round(sum(central["real_rev"][1:]) / H, 1),
                             "players": round(sum(central["players"][1:]) / H, 1),
                             "players_min": round(min(central["players"]), 1), "rev_min": round(min(central["rev"]), 1),
                             "cost_end": round(central["cost"][-1], 1), "cpi_end": round(central["cpi"][-1], 1),
                             "fx_end": round(central["fx"][-1], 1)},
            "band": {k: [[round(a, 1), round(b, 1)] for a, b in v] for k, v in bands.items()},
            "year_range": {k: stats(v) for k, v in year_sums.items()},
            "survive": survive, "best_choice": best_choice,
        }
        print(f"{sid} {time.time() - t0:.0f}s", flush=True)
    (S.REPORTS / "outlook.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    o = run()
    for sid, s in o["scenarios"].items():
        print(sid, s["central_year"], s["year_range"], s["survive"], s["best_choice"])
