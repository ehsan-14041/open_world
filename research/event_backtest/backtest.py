"""
Run the event backtest exactly as PROTOCOL.md states it.

    python research/event_backtest/backtest.py

Reads the two BIS bulk files in research/event_backtest/data/, writes results.json beside this file.
"""

from __future__ import annotations

import csv
import io
import json
import statistics
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from event_sim.engine import SimulationConfig, build_simulation  # noqa: E402
from event_sim.registry import _registry  # noqa: E402
from event_sim.schemas import EventDefinition, WorldModule  # noqa: E402
from event_sim.evidence import validate_module  # noqa: E402
from event_sim.world_builder import build_slice  # noqa: E402

DATA = HERE / "data"
K = 13                     # months t .. t+12
THRESHOLD = 0.15
QUIET = 24
MAX_PRIOR_INFLATION = 1.0


# ---- data ---------------------------------------------------------------------------------------

def _read(zip_name: str, keep) -> dict[str, dict[int, float]]:
    """country code -> {month index: value}, for the rows `keep` accepts."""
    out: dict[str, dict[int, float]] = {}
    z = zipfile.ZipFile(DATA / zip_name)
    with z.open(z.namelist()[0]) as fh:
        r = csv.reader(io.TextIOWrapper(fh, "utf-8"))
        h = [c.split(":")[0] for c in next(r)]
        for row in r:
            d = dict(zip(h, row))
            if not keep(d):
                continue
            tp, val = d["TIME_PERIOD"], d["OBS_VALUE"]
            if len(tp) != 7 or tp[4] != "-" or val in ("", "NaN"):
                continue
            try:
                v = float(val)
            except ValueError:
                continue
            if v <= 0:
                continue
            area = d["REF_AREA"].split(":")[0]
            out.setdefault(area, {})[int(tp[:4]) * 12 + int(tp[5:]) - 1] = v
    return out


def load():
    fx = _read("WS_XRU_csv_flat.zip", lambda d: d["FREQ"].startswith("M") and d["COLLECTION"].startswith("A"))
    cpi = _read("WS_LONG_CPI_csv_flat.zip", lambda d: d["FREQ"].startswith("M") and d["UNIT_MEASURE"].startswith("628"))
    return fx, cpi


def find_events(fx, cpi) -> list[dict]:
    events = []
    for area in sorted(set(fx) & set(cpi)):
        if area == "US":
            continue
        f, c = fx[area], cpi[area]
        months = sorted(f)
        jumps = {m for m in months if m - 1 in f and f[m] / f[m - 1] - 1 >= THRESHOLD}
        for t in sorted(jumps):
            if any(m in jumps for m in range(t - QUIET, t)):
                continue
            window = range(t - 13, t + K)
            if not all(m in f and m in c for m in window):
                continue
            prior = c[t - 1] / c[t - 13] - 1
            if prior > MAX_PRIOR_INFLATION:
                continue
            g = (c[t - 1] / c[t - 13]) ** (1 / 12) - 1
            d = (f[t - 1] / f[t - 13]) ** (1 / 12) - 1
            events.append({
                "country": area, "month": f"{t // 12}-{t % 12 + 1:02d}", "t": t,
                "jump_pct": round(100 * (f[t] / f[t - 1] - 1), 1),
                "prior_inflation_pct": round(100 * prior, 1),
                "dev_fx": [f[t + k] / (f[t - 1] * (1 + d) ** (k + 1)) - 1 for k in range(K)],
                "dev_cpi": [c[t + k] / (c[t - 1] * (1 + g) ** (k + 1)) - 1 for k in range(K)],
            })
    events.sort(key=lambda e: (e["t"], e["country"]))
    return events


# ---- the engine -----------------------------------------------------------------------------------

def _module(c: float, r: float, lag: int) -> str:
    mid = f"fx_passthrough_c{c:.2f}_r{r:.2f}_l{lag}"
    if mid in _registry():
        return mid
    var = lambda vid, resp: {  # noqa: E731
        "id": vid, "unit": "index (100 = pre-shock trend)", "baseline": 100.0, "scale": 100.0,
        "range": {"min": 1.0, "max": 100000.0}, "dynamics": {"response": resp},
        "observability": "measured", "observability_class": "observable",
        "observability_note": "BIS monthly series.", "status": "expert_assumption"}
    module = WorldModule.from_dict({
        "id": mid, "domain": "exploratory", "time_unit": "months", "title": mid,
        "variables": [var("fx", 1.0), var("cpi", r)],
        "edges": [{"source": "fx", "target": "cpi", "polarity": "positive",
                   "effect": {"low": c, "central": c, "high": c},
                   "lag": {"min": lag, "max": lag, "unit": "months"}, "evidence": [],
                   "status": "expert_assumption", "confidence": "low"}],
        "axes": [], "interventions": []})
    validate_module(module)
    _registry()[mid] = module
    return mid


def engine_path(event: dict, c: float, r: float, lag: int) -> list[float]:
    """devCPI for k = 0..12 from the repository's engine, the currency path held as observed."""
    slice_ = build_slice([_module(c, r, lag)])
    evs = [EventDefinition(id=f"fx{k}", targets={"fx": 100.0 * event["dev_fx"][k]}, start_turn=k + 1,
                           duration=1, shape="step") for k in range(K)]
    sim = build_simulation(slice_, config=SimulationConfig(turns=K), events=evs)
    sim.run()
    return [v / 100.0 - 1 for v in sim.series("cpi")[1:]]


def fast_path(dev_fx: list[float], c: float, r: float, lag: int) -> list[float]:
    """The same recurrence without the engine's bookkeeping; held to it by check_parity()."""
    hist = [0.0] + dev_fx            # fx deviation at turn 0..13
    cpi, out = 0.0, []
    for t in range(K):               # computing turn t+1
        st = t - lag
        cpi = cpi + r * (c * (hist[st] if st >= 0 else 0.0) - cpi)
        out.append(cpi)
    return out


def check_parity(events) -> float:
    worst = 0.0
    for e in events[:6]:
        for (c, r, lag) in ((0.5, 0.6, 1), (0.25, 0.15, 0), (1.2, 1.0, 3)):
            a, b = engine_path(e, c, r, lag), fast_path(e["dev_fx"], c, r, lag)
            worst = max(worst, max(abs(x - y) for x, y in zip(a, b)))
    return worst


GRID = [(c / 20, r / 20, lag) for c in range(0, 31) for r in range(1, 21) for lag in (0, 1, 2, 3)]


def fit_engine(train) -> tuple[float, float, int]:
    best, best_sse = None, float("inf")
    for (c, r, lag) in GRID:
        sse = 0.0
        for e in train:
            p = fast_path(e["dev_fx"], c, r, lag)
            sse += sum((x - y) ** 2 for x, y in zip(p, e["dev_cpi"]))
        if sse < best_sse:
            best, best_sse = (c, r, lag), sse
    return best


# ---- baselines and scoring ----------------------------------------------------------------------

def fit_b1(train):
    return [statistics.fmean(e["dev_cpi"][k] for e in train) for k in range(K)]


def fit_b2(train):
    out = []
    for k in range(K):
        sxx = sum(e["dev_fx"][k] ** 2 for e in train)
        out.append(sum(e["dev_fx"][k] * e["dev_cpi"][k] for e in train) / sxx if sxx else 0.0)
    return out


PRIOR = (0.5, round(1 - 0.97 ** 30.4, 2), 1)


def predictions(train, test) -> dict[str, list[list[float]]]:
    params = fit_engine(train)
    b1, b2 = fit_b1(train), fit_b2(train)
    return {
        "_params": params,
        "B0 no effect": [[0.0] * K for _ in test],
        "B1 average of previous events": [list(b1) for _ in test],
        "B2 regression": [[b2[k] * e["dev_fx"][k] for k in range(K)] for e in test],
        "E-prior (guessed coefficients)": [fast_path(e["dev_fx"], *PRIOR) for e in test],
        "E-fit (fitted engine)": [fast_path(e["dev_fx"], *params) for e in test],
    }


def score(preds, test) -> dict[str, float]:
    e12 = [100 * (p[12] - e["dev_cpi"][12]) for p, e in zip(preds, test)]
    path = [100 * (p[k] - e["dev_cpi"][k]) for p, e in zip(preds, test) for k in range(K)]
    rmse = lambda xs: (sum(x * x for x in xs) / len(xs)) ** 0.5  # noqa: E731
    return {"rmse_12": round(rmse(e12), 2), "rmse_path": round(rmse(path), 2),
            "median_abs_12": round(statistics.median(abs(x) for x in e12), 2)}


def main() -> None:
    fx, cpi = load()
    events = find_events(fx, cpi)
    n = len(events)
    cut = int(round(0.8 * n))
    train, test = events[:cut], events[cut:]
    out = {"n_events": n, "n_train": len(train), "n_test": len(test),
           "countries": len({e["country"] for e in events}),
           "span": [events[0]["month"], events[-1]["month"]],
           "parity_worst_abs_diff": check_parity(events)}

    p = predictions(train, test)
    out["temporal"] = {"split_at": test[0]["month"], "fitted_params": dict(zip(("c", "r", "lag"), p.pop("_params"))),
                       "scores": {k: score(v, test) for k, v in p.items()}}
    # The fitted engine's test predictions come from the repository's engine itself, not the replica.
    prm = tuple(out["temporal"]["fitted_params"].values())
    real = [engine_path(e, *prm) for e in test]
    out["temporal"]["engine_itself_rmse_12"] = score(real, test)["rmse_12"]
    out["temporal"]["test_events"] = [
        {"country": e["country"], "month": e["month"], "fx_dev_12_pct": round(100 * e["dev_fx"][12], 1),
         "observed_cpi_dev_12_pct": round(100 * e["dev_cpi"][12], 1),
         "fitted_engine_pct": round(100 * q[12], 1)} for e, q in zip(test, real)]

    # 5 folds grouped by country
    countries = sorted({e["country"] for e in events})
    fold_of = {c: i % 5 for i, c in enumerate(countries)}
    pooled: dict[str, list] = {}
    pooled_test, params = [], []
    for f in range(5):
        tr = [e for e in events if fold_of[e["country"]] != f]
        te = [e for e in events if fold_of[e["country"]] == f]
        if not te:
            continue
        q = predictions(tr, te)
        params.append(q.pop("_params"))
        for k, v in q.items():
            pooled.setdefault(k, []).extend(v)
        pooled_test.extend(te)
    out["grouped_cv"] = {"fitted_params_per_fold": params,
                         "scores": {k: score(v, pooled_test) for k, v in pooled.items()}}

    def passes(s):
        return s["E-fit (fitted engine)"]["rmse_12"] < min(s["B0 no effect"]["rmse_12"],
                                                           s["B1 average of previous events"]["rmse_12"])
    out["verdict"] = {
        "beats_B0_and_B1_temporal": passes(out["temporal"]["scores"]),
        "beats_B0_and_B1_grouped_cv": passes(out["grouped_cv"]["scores"]),
        "beats_B2_temporal": out["temporal"]["scores"]["E-fit (fitted engine)"]["rmse_12"]
                             < out["temporal"]["scores"]["B2 regression"]["rmse_12"],
        "beats_B2_grouped_cv": out["grouped_cv"]["scores"]["E-fit (fitted engine)"]["rmse_12"]
                               < out["grouped_cv"]["scores"]["B2 regression"]["rmse_12"],
    }
    out["verdict"]["pass"] = out["verdict"]["beats_B0_and_B1_temporal"] and out["verdict"]["beats_B0_and_B1_grouped_cv"]
    out["events"] = [{k: e[k] for k in ("country", "month", "jump_pct", "prior_inflation_pct")} for e in events]
    (HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in out if k != "events"}, indent=1))


if __name__ == "__main__":
    main()
