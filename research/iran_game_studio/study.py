"""
Exploratory scenario study: a domestic Iranian mobile game studio under currency and connectivity
shocks, run on the OWE engine. NOT a product wedge, and nothing here is validated.

    python research/iran_game_studio/study.py            # scenarios + census + benchmark
    python research/iran_game_studio/study.py --quick    # central setting only

Same discipline as the cafe: the engine carries behaviour in index space; money is arithmetic
on its trajectories, here. The studio's figures in STUDIO are illustrative placeholders, to be
replaced by a real studio's numbers; results are reported as rankings, months of runway and
percentage changes so that they do not lean on them more than they must.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from event_sim.engine import Intervention, SimulationConfig, build_simulation  # noqa: E402
from event_sim.registry import _registry, load_module_file  # noqa: E402
from event_sim.schemas import EventDefinition  # noqa: E402
from event_sim.world_builder import build_slice  # noqa: E402

MODULE_PATH = HERE / "iran_mobile_studio_v0.json"
#: Where the reports and their data are written.
REPORTS = ROOT / "reports" / "iran_game_studio"
MODULE = load_module_file(MODULE_PATH)
_registry()[MODULE.id] = MODULE          # this run only; the shipped library is untouched
SLICE = build_slice([MODULE.id], question="Iranian mobile studio under shocks")
MODULE_SHA = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()[:12]

DPM = 365 / 12
H = 365

#: Illustrative studio, monthly, in millions of tomans. ASSUMPTIONS, to be replaced.
STUDIO = {
    "iap_gross": 1600.0,      # in-app sales before the store's share
    "commission": 0.30,       # store's share of in-app sales
    "ads": 300.0,             # domestic ad revenue
    "wages": 900.0,           # 15 people
    "usd_costs": 250.0,       # servers, tools, assets, foreign services, at today's dollar
    "other": 150.0,           # rent and the rest, follows prices
    "cash": 4000.0,           # about three months of costs
}

OPTIONS = {
    "A": {"label": "Hold: keep prices, team and ads", "iv": []},
    "B": {"label": "Raise in-app prices 30%", "iv": [("raise_iap_prices", 30.0)]},
    "C": {"label": "Cut the team 25%", "iv": [("cut_team", 25.0)]},
    "D": {"label": "Show 50% more ads", "iv": [("more_ads", 50.0)], "ad_load": 1.5},
}


def ev(id_, targets, start, duration, label=""):
    return EventDefinition(id=id_, label=label or id_, targets=targets, start_turn=start,
                           duration=duration, shape="step", status="user_assumption")


SCENARIOS = {
    "S0_calm": {"label": "Nothing happens", "events": []},
    "S1_fx50": {"label": "Dollar +50%, stays", "events": [ev("fx", {"fx_rate": 50.0}, 1, H)]},
    "S2_fx100": {"label": "Dollar doubles, stays", "events": [ev("fx", {"fx_rate": 100.0}, 1, H)]},
    "S3_shutdown10": {"label": "Near-total shutdown, 10 days", "events": [ev("cut", {"connectivity": -90.0}, 1, 10)]},
    "S4_throttle88": {"label": "Heavy throttling, 88 days", "events": [ev("thr", {"connectivity": -40.0}, 1, 88)]},
    "S5_war_combo": {"label": "Shutdown 10d, then throttling 78d, dollar +60%",
                     "events": [ev("fx", {"fx_rate": 60.0}, 1, H), ev("cut", {"connectivity": -90.0}, 1, 10),
                                ev("thr", {"connectivity": -40.0}, 11, 78)]},
    "S6_brain_drain": {"label": "A fifth of the team leaves, not replaced",
                       "events": [ev("leave", {"staff": -20.0}, 30, H)]},
    "S7_commission15": {"label": "Store share falls from 30% to 15%", "events": [], "commission": 0.15},
}

CENSUS_AXES = ["price_sensitivity", "income_sensitivity", "fx_pass_through", "network_dependence",
               "habit_recovery", "content_dependence"]
CENTRAL = {a.id: a.default_setting() for a in SLICE.axes}


def run_world(events, option, axes, turns=H):
    ivs = [Intervention.from_slice(SLICE, iv_id, magnitude=m, start_turn=1, duration=turns)
           for iv_id, m in option["iv"]]
    cfg = SimulationConfig(turns=turns, axis_settings=dict(CENTRAL, **axes), lag_setting="central")
    sim = build_simulation(SLICE, config=cfg, events=events, interventions=ivs)
    sim.run()
    return {v.id: sim.series(v.id) for v in SLICE.variables}


def fast_run(events, option, axes, turns=H):
    """
    The same step rule as EventSimulation.step, without its provenance records (which make a
    year-long run take ~18 s). Coefficients, lags, response rates and intervention offsets are
    read from an engine object built for the same world, so nothing is restated by hand.
    check_parity() holds it to the engine exactly.
    """
    ivs = [Intervention.from_slice(SLICE, iv_id, magnitude=m, start_turn=1, duration=turns)
           for iv_id, m in option["iv"]]
    # A sensitivity run may restate an intervention's per-unit effect (the ad annoyance cost),
    # which the module fixes and the census does not sweep.
    for iv in ivs:
        iv.effects_per_unit.update(option.get("effects", {}).get(iv.id, {}))
    cfg = SimulationConfig(turns=turns, axis_settings=dict(CENTRAL, **axes), lag_setting="central")
    sim = build_simulation(SLICE, config=cfg, events=events, interventions=ivs)
    vars_ = SLICE.variables
    ids = [v.id for v in vars_]
    scale = {v.id: v.scale for v in vars_}
    base = {v.id: v.baseline for v in vars_}
    lo = {v.id: v.minimum for v in vars_}
    hi = {v.id: v.maximum for v in vars_}
    resp = {v: sim.response_for_variable(v) for v in ids}
    inc = {v: [] for v in ids}
    for e in SLICE.edges:
        inc[e.target].append((e.source, e.coefficient(sim.effect_setting_for_edge(e)),
                              e.lag.effective("central")))
    dev_hist = [{v: 0.0 for v in ids}]
    endo = {v: 0.0 for v in ids}
    for t in range(turns):
        nt = t + 1
        holds = {}
        for evd in events:
            for vid, mag in evd.magnitude_at(nt).items():
                holds[vid] = mag / scale[vid]
        offs = {}
        for iv in ivs:
            for vid, mag in iv.offsets_at(nt).items():
                offs[vid] = offs.get(vid, 0.0) + mag / scale[vid]
        new_dev, off_by = {}, {}
        for vid in ids:
            p = 0.0
            for src, coef, lag in inc[vid]:
                st = t - lag
                p += coef * (dev_hist[st][src] if 0 <= st < len(dev_hist) else 0.0)
            e0 = endo[vid]
            relaxed = e0 + resp[vid] * (p - e0)
            b = holds[vid] if vid in holds else relaxed
            o = offs.get(vid, 0.0)
            off_by[vid] = o
            new_dev[vid] = b + o
        final = {}
        for vid in ids:
            val = base[vid] + scale[vid] * new_dev[vid]
            if lo[vid] is not None and val < lo[vid]:
                val = lo[vid]
            if hi[vid] is not None and val > hi[vid]:
                val = hi[vid]
            final[vid] = (val - base[vid]) / scale[vid]
        dev_hist.append(final)
        endo = {vid: final[vid] - off_by[vid] for vid in ids}
    return {vid: [base[vid] + scale[vid] * d[vid] for d in dev_hist] for vid in ids}


def check_parity(cases):
    worst = 0.0
    for events, option, axes, turns in cases:
        a = run_world(events, option, axes, turns)
        b = fast_run(events, option, axes, turns)
        for vid in a:
            worst = max(worst, max(abs(x - y) for x, y in zip(a[vid], b[vid])))
    return worst


def ledger(series, option, commission=None, studio=STUDIO):
    s = studio
    com = s["commission"] if commission is None else commission
    load = option.get("ad_load", 1.0)
    cash, out = s["cash"], {"rev": [], "cost": [], "net": [], "cash": [], "players": [], "cpi": []}
    for d in range(len(series["fx_rate"])):
        f = {k: series[k][d] / 100.0 for k in series}
        iap = s["iap_gross"] / DPM * f["active_players"] * f["payer_conversion"] * f["iap_price"] * (1 - com)
        ads = s["ads"] / DPM * f["active_players"] * f["ad_rate"] * load
        cost = (s["wages"] / DPM * f["staff"] * f["studio_wage"] + s["usd_costs"] / DPM * f["fx_rate"]
                + s["other"] / DPM * f["price_level"])
        net = iap + ads - cost
        if d > 0:
            cash += net
        for k, v in (("rev", iap + ads), ("cost", cost), ("net", net), ("cash", cash),
                     ("players", f["active_players"]), ("cpi", f["price_level"])):
            out[k].append(v)
    return out


def metrics(L):
    neg = next((d for d, c in enumerate(L["cash"]) if c < 0), None)
    last = len(L["cash"]) - 1
    m30 = sum(L["net"][last - 29:last + 1])
    return {
        "cash_end": L["cash"][last],
        "real_cash_end": L["cash"][last] / L["cpi"][last],
        "first_negative_day": neg,
        "rev_change_pct": 100 * (L["rev"][last] / L["rev"][0] - 1),
        "cost_change_pct": 100 * (L["cost"][last] / L["cost"][0] - 1),
        "players_min_pct": 100 * (min(L["players"]) - 1),
        "rev_min_pct": 100 * (min(L["rev"]) / L["rev"][0] - 1),
        "players_end_pct": 100 * (L["players"][last] - 1),
        "last_month_net": m30,
    }


def scenario_table():
    rows = {}
    for sid, sc in SCENARIOS.items():
        rows[sid] = {}
        for oid, op in OPTIONS.items():
            ser = fast_run(sc["events"], op, {})
            rows[sid][oid] = metrics(ledger(ser, op, sc.get("commission")))
    return rows


def census(scenario_ids):
    out = {}
    combos = list(itertools.product(*[next(a.settings for a in SLICE.axes if a.id == ax) for ax in CENSUS_AXES]))
    for sid in scenario_ids:
        sc = SCENARIOS[sid]
        wins = {k: 0 for k in OPTIONS}
        runway = {k: 0 for k in OPTIONS}      # cases where cash never goes negative
        for combo in combos:
            axes = dict(zip(CENSUS_AXES, combo))
            res = {}
            for oid, op in OPTIONS.items():
                res[oid] = metrics(ledger(fast_run(sc["events"], op, axes), op, sc.get("commission")))
                if res[oid]["first_negative_day"] is None:
                    runway[oid] += 1
            wins[max(res, key=lambda k: res[k]["cash_end"])] += 1
        out[sid] = {"n": len(combos), "wins": wins, "never_negative": runway}
    return out


# ---- the historical benchmark ----------------------------------------------------------------
# 1400 -> 1402 (three Iranian years, 1,095 days). Observed, from public sources (see REPORT.md):
#   * CPI: annual inflation 40.2% (1400), 45.8% (1401), 40.7% (1402)
#   * connectivity: heavy mobile restrictions in autumn 1401 (from about Shahrivar 1401, ~90
#     days); the depth is NOT measured here and is an assumption (-30).
#   * native mobile game spending: 202 bn tomans (1400) -> 287 bn tomans (1402), +42% nominal
#   * gamers: 34 m (1400) -> 29.3 m (1402), -14% (survey headcount, not daily actives)
# The engine is NOT fitted to these. Its coefficients were fixed before this was run.

INFLATION = [40.2, 45.8, 40.7]


def cpi_events():
    """Monthly step events holding the price level on the observed annual path."""
    evs, level = [], 100.0
    for y, infl in enumerate(INFLATION):
        g = (1 + infl / 100) ** (1 / 12)
        for m in range(12):
            level *= g
            evs.append(ev(f"cpi{y}{m}", {"price_level": level - 100.0}, 1 + 365 * y // 1 + int(m * DPM), int(DPM) + 1))
    return evs


def benchmark():
    evs = cpi_events() + [ev("restrict1401", {"connectivity": -30.0}, 365 + 180, 90)]
    out = {}
    T = 3 * 365
    policies = {"hold prices": 0.0, "index half of inflation": None, "index fully": None}
    for name in policies:
        option = {"iv": []}
        ser = fast_run(evs, option, {}, turns=T)
        if name != "hold prices":
            share = 0.5 if name.startswith("index half") else 1.0
            # In-app prices follow the observed price level with a quarter's delay.
            lagged = [100.0] * 90 + ser["price_level"][:-90]
            ser = fast_run(evs + [ev(f"p{d}", {"iap_price": share * (lagged[d] - 100.0)}, d, 1)
                                   for d in range(1, T + 1)], option, {}, turns=T)
        L = ledger(ser, {"iv": []})
        y1 = sum(L["rev"][0:365]); y3 = sum(L["rev"][730:1095])
        p1 = sum(L["players"][0:365]) / 365; p3 = sum(L["players"][730:1095]) / 365
        out[name] = {"revenue_y1402_vs_y1400_pct": 100 * (y3 / y1 - 1),
                     "players_y1402_vs_y1400_pct": 100 * (p3 / p1 - 1),
                     "cpi_end": L["cpi"][-1] * 100}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    result = {"module": MODULE.id, "module_sha256_12": MODULE_SHA, "studio": STUDIO,
              "options": {k: v["label"] for k, v in OPTIONS.items()},
              "scenarios": {k: v["label"] for k, v in SCENARIOS.items()},
              "central": scenario_table()}
    print(f"central table {time.time() - t0:.1f}s", flush=True)
    if not args.quick:
        # Every central scenario x option, full year, against the real engine.
        cases = [(sc["events"], op, {}, H) for sc in SCENARIOS.values() for op in OPTIONS.values()]
        result["parity_worst_abs_diff"] = check_parity(cases)
        print(f"parity {result['parity_worst_abs_diff']} {time.time() - t0:.1f}s", flush=True)
    result["benchmark"] = benchmark()
    print(f"benchmark {time.time() - t0:.1f}s", flush=True)
    if not args.quick:
        result["census"] = census(list(SCENARIOS))
        print(f"census {time.time() - t0:.1f}s", flush=True)
    (REPORTS / "results.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("central", "benchmark")}, indent=1)[:6000])


if __name__ == "__main__":
    main()
