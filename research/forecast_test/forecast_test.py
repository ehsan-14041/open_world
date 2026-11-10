"""
Political forecasting test, as PROTOCOL.md states it.

    python research/forecast_test/forecast_test.py collect              # download eligible questions
    python research/forecast_test/forecast_test.py baselines --cutoff 2025-06-01
    python research/forecast_test/forecast_test.py run --cutoff YYYY-MM-DD   # needs a model

`run` reads an OpenAI-compatible endpoint from the environment:

    FORECAST_API_KEY   FORECAST_BASE_URL (default https://api.openai.com/v1)   FORECAST_MODEL

`--cutoff` is the model's training cutoff as its provider states it. `--dry-run` replaces the
model with a fixed stub to exercise the pipeline; its numbers mean nothing and are labelled so.
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
DATA = HERE / "data"
QUESTIONS = DATA / "questions.json"
PRICES = DATA / "prices.json"
SEED = 20261110
SAMPLE = 300
UA = {"User-Agent": "owe-forecast-test"}


def _get(url: str, tries: int = 4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(2 + 3 * i)


def _date(s: str | None):
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


# ---- questions ------------------------------------------------------------------------------------

def collect(since: str = "2024-01-01") -> None:
    """Every eligible market except rule 4 (the cutoff), which depends on the model.

    The API refuses large offsets, so events are fetched in half-month windows of start date.
    """
    floor, today = _date(since), dt.date.today()
    out, seen = [], set()
    lo = floor
    while lo <= today:
        hi = lo + dt.timedelta(days=15)
        offset = 0
        while True:
            try:
                page = _get("https://gamma-api.polymarket.com/events?closed=true&tag_slug=politics&limit=100"
                            f"&start_date_min={lo}T00:00:00Z&start_date_max={hi}T00:00:00Z&offset={offset}", tries=2)
            except Exception as exc:  # noqa: BLE001
                print(f"window {lo}: stopped at offset {offset} ({exc})", flush=True)
                break
            for ev in page or []:
                if ev["id"] in seen:
                    continue
                seen.add(ev["id"])
                best = None
                for m in ev.get("markets") or []:
                    try:
                        outcomes = json.loads(m.get("outcomes") or "[]")
                        prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
                        vol = float(m.get("volumeNum") or 0)
                    except (ValueError, TypeError):
                        continue
                    start, close = _date(m.get("startDate")), _date(m.get("closedTime") or m.get("endDate"))
                    if outcomes != ["Yes", "No"] or sorted(prices) != [0.0, 1.0] or vol < 10000:
                        continue
                    if not start or not close or (close - start).days < 14:
                        continue
                    row = {"id": str(m["id"]), "event": str(ev["id"]), "question": m.get("question") or "",
                           "rules": (m.get("description") or "")[:3000], "start": start.isoformat(),
                           "close": close.isoformat(), "yes": int(prices[0] == 1.0), "volume": round(vol),
                           "token": (json.loads(m.get("clobTokenIds") or "[null]") or [None])[0]}
                    if best is None or row["volume"] > best["volume"]:
                        best = row
                if best:
                    out.append(best)
            if not page or len(page) < 100:
                break
            offset += 100
        print(f"{lo}: {len(seen)} events seen, {len(out)} eligible", flush=True)
        lo = hi
    out = [q for q in out if _date(q["start"]) >= floor]
    out.sort(key=lambda q: (q["start"], q["id"]))
    DATA.mkdir(exist_ok=True)
    QUESTIONS.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(out)} questions -> {QUESTIONS}")


def select(cutoff: str):
    """(sample, base-rate questions) for a model with this training cutoff."""
    qs = json.loads(QUESTIONS.read_text("utf-8"))
    first = _date(cutoff) + dt.timedelta(days=30)
    eligible = [q for q in qs if _date(q["start"]) >= first]
    rng = random.Random(SEED)
    sample = eligible if len(eligible) <= SAMPLE else rng.sample(eligible, SAMPLE)
    ids = {q["id"] for q in sample}
    rest = [q for q in qs if q["id"] not in ids]        # includes questions before the cutoff
    return sorted(sample, key=lambda q: (q["start"], q["id"])), rest[:300], len(eligible)


def market_price(q: dict, cache: dict) -> float | None:
    """The market's own price about a week after it opened."""
    if q["id"] in cache:
        return cache[q["id"]]
    p = None
    if q.get("token"):
        try:
            h = _get(f"https://clob.polymarket.com/prices-history?market={q['token']}&interval=max&fidelity=1440").get("history") or []
            target = time.mktime((_date(q["start"]) + dt.timedelta(days=7)).timetuple())
            if h:
                p = float(min(h, key=lambda x: abs(x["t"] - target))["p"])
        except Exception:  # noqa: BLE001
            p = None
    cache[q["id"]] = p
    return p


# ---- the engine arm -------------------------------------------------------------------------------

STRENGTH = {"weak": 0.2, "medium": 0.5, "strong": 0.8}
MULT = (0.5, 1.0, 1.5)
RESPONSE = 0.3


def weeks(q: dict) -> int:
    return max(2, min(26, round((_date(q["close"]) - _date(q["start"])).days / 7)))


def clean_drivers(raw) -> tuple[float, list[dict]] | None:
    try:
        tendency = max(-1.0, min(1.0, float(raw["tendency"])))
        drivers = []
        for d in raw["drivers"][:6]:
            drivers.append({"name": str(d["name"])[:80],
                            "sign": 1.0 if str(d["toward"]).lower().startswith("y") else -1.0,
                            "strength": STRENGTH[str(d["strength"]).lower()],
                            "level": max(0.0, min(1.0, float(d["level"]))),
                            "lag": max(0, min(8, int(d["delay_weeks"])))})
        return (tendency, drivers) if len(drivers) >= 3 else None
    except (KeyError, ValueError, TypeError):
        return None


def outcome_fast(tendency, drivers, mults, turns) -> float:
    # As in the engine: the tendency is the outcome's baseline, and the drivers move it from there.
    dev = 0.0
    for t in range(turns):
        pressure = sum(d["sign"] * d["strength"] * m * (d["level"] if t - d["lag"] >= 1 else 0.0)
                       for d, m in zip(drivers, mults))
        dev = dev + RESPONSE * (pressure - dev)
    return tendency + dev


def outcome_engine(tendency, drivers, mults, turns) -> float:
    """The same world on the repository's engine. Used to hold outcome_fast to it."""
    from event_sim.engine import SimulationConfig, build_simulation
    from event_sim.evidence import validate_module
    from event_sim.registry import _registry
    from event_sim.schemas import EventDefinition, WorldModule
    from event_sim.world_builder import build_slice

    def var(vid, resp, base=0.0):
        return {"id": vid, "unit": "index", "baseline": base, "scale": 1.0, "range": {"min": -50.0, "max": 50.0},
                "dynamics": {"response": resp}, "observability": "derived", "observability_class": "latent",
                "observability_note": "Authored by a language model for one question; no series exists.",
                "status": "ai_hypothesis"}
    mid = f"q_{abs(hash((tendency, json.dumps(drivers), mults, turns)))}"
    module = WorldModule.from_dict({
        "id": mid, "domain": "exploratory", "time_unit": "weeks", "title": mid,
        "variables": [var(f"d{i}", 1.0) for i in range(len(drivers))] + [var("outcome", RESPONSE, tendency)],
        "edges": [{"source": f"d{i}", "target": "outcome", "polarity": "positive" if d["sign"] > 0 else "negative",
                   "effect": {"low": d["strength"] * m, "central": d["strength"] * m, "high": d["strength"] * m},
                   "lag": {"min": d["lag"], "max": d["lag"], "unit": "weeks"}, "evidence": [],
                   "status": "ai_hypothesis", "confidence": "low"} for i, (d, m) in enumerate(zip(drivers, mults))],
        "axes": [], "interventions": []})
    validate_module(module)
    _registry()[mid] = module
    evs = [EventDefinition(id=f"hold{i}", targets={f"d{i}": d["level"]}, start_turn=1, duration=turns, shape="step")
           for i, d in enumerate(drivers)]
    sim = build_simulation(build_slice([mid]), config=SimulationConfig(turns=turns), events=evs)
    sim.run()
    return sim.series("outcome")[-1]


def census(tendency, drivers, turns) -> dict:
    yes, n, flips = 0, 0, []
    results = {}
    for mults in itertools.product(MULT, repeat=len(drivers)):
        v = outcome_fast(tendency, drivers, mults, turns)
        results[mults] = v > 0
        yes += v > 0
        n += 1
    centre = tuple(1.0 for _ in drivers)
    for i, d in enumerate(drivers):
        tops = {results[tuple(m if j == i else 1.0 for j in range(len(drivers)))] for m in MULT}
        if len(tops) > 1:
            flips.append(d["name"])
    return {"share_yes": yes / n, "n": n, "centre_yes": results[centre], "flips": flips,
            "centre_value": round(outcome_fast(tendency, drivers, centre, turns), 3)}


# ---- the model --------------------------------------------------------------------------------------

def chat(prompt: str) -> str:
    key = os.environ["FORECAST_API_KEY"]
    base = os.environ.get("FORECAST_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    body = json.dumps({"model": os.environ["FORECAST_MODEL"], "temperature": 0,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", **UA})
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["choices"][0]["message"]["content"]
        except Exception:  # noqa: BLE001
            if i == 3:
                raise
            time.sleep(4 + 6 * i)
    return ""


def stub(prompt: str) -> str:
    """A fixed, question-blind reply for --dry-run. Not a forecast."""
    if '"drivers"' in prompt and "census" not in prompt:
        return json.dumps({"tendency": -0.2, "drivers": [
            {"name": "status quo holds", "toward": "no", "strength": "medium", "level": 0.7, "delay_weeks": 0},
            {"name": "stated intent", "toward": "yes", "strength": "medium", "level": 0.5, "delay_weeks": 2},
            {"name": "time left", "toward": "yes", "strength": "weak", "level": 0.4, "delay_weeks": 4}],
            "probability": 0.3})
    return json.dumps({"probability": 0.3})


def _json(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None


def _prob(obj) -> float | None:
    try:
        p = float(obj["probability"])
        return max(0.01, min(0.99, p)) if 0 <= p <= 1 else None
    except (KeyError, ValueError, TypeError):
        return None


FRAME = ("You are forecasting a yes/no question. Today is {start}. You have no information after "
         "your training data and must not assume any.\n\nQuestion: {question}\n\nResolution rules:\n{rules}\n\n"
         "The question closes on {close}.\n\n")
ASK_L = FRAME + 'Reply with JSON only: {{"probability": <number between 0 and 1 that it resolves Yes>}}'
ASK_L2 = FRAME + (
    "First list the 3 to 6 drivers that matter most. Reply with JSON only:\n"
    '{{"tendency": <-1..1, where things stand today; negative leans No>,\n'
    ' "drivers": [{{"name": "...", "toward": "yes" or "no", "strength": "weak" | "medium" | "strong",\n'
    '              "level": <0..1, how present it is now>, "delay_weeks": <0..8>}}],\n'
    ' "probability": <number between 0 and 1 that it resolves Yes>}}')
ASK_LE2 = FRAME + (
    "You listed these drivers:\n{drivers}\n\nA simulation ran them forward to the close date under "
    "{n} combinations of driver strengths (each at half, as stated, and one and a half times). "
    "This is a census of your own assumptions, not a probability.\n"
    "- The outcome ended on the Yes side in {share:.0%} of combinations.\n"
    "- With every driver as you stated it, it ended on the {centre} side.\n"
    "- Drivers whose strength alone flips the result: {flips}.\n\n"
    'Taking this into account, reply with JSON only: {{"probability": <number between 0 and 1>}}')


def forecast(q: dict, ask) -> dict | None:
    f = dict(start=q["start"], close=q["close"], question=q["question"], rules=q["rules"])
    for _ in range(2):
        pl = _prob(_json(ask(ASK_L.format(**f))) or {})
        raw = _json(ask(ASK_L2.format(**f))) or {}
        pl2, cd = _prob(raw), clean_drivers(raw)
        if pl is None or pl2 is None or cd is None:
            continue
        tendency, drivers = cd
        c = census(tendency, drivers, weeks(q))
        shown = "\n".join(f"- {d['name']}: toward {'Yes' if d['sign'] > 0 else 'No'}, strength {d['strength']}, "
                          f"level {d['level']}, delay {d['lag']} weeks" for d in drivers)
        ple2 = _prob(_json(ask(ASK_LE2.format(**f, drivers=shown, n=c["n"], share=c["share_yes"],
                                              centre="Yes" if c["centre_yes"] else "No",
                                              flips=", ".join(c["flips"]) or "none"))) or {})
        if ple2 is None:
            continue
        return {"L": pl, "L2": pl2, "LE1": max(0.02, min(0.98, c["share_yes"])), "LE2": ple2,
                "census": c, "tendency": tendency, "drivers": drivers}
    return None


# ---- scoring --------------------------------------------------------------------------------------

def brier(ps, ys) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def paired(a, b, ys, reps=10000) -> dict:
    """Brier(a) - Brier(b) with a bootstrap 95% interval. Negative means a is better."""
    d = [(x - y) ** 2 - (z - y) ** 2 for x, z, y in zip(a, b, ys)]
    rng = random.Random(SEED)
    n = len(d)
    means = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return {"difference": round(sum(d) / n, 4), "ci95": [round(means[int(0.025 * reps)], 4), round(means[int(0.975 * reps)], 4)]}


def baselines(cutoff: str) -> dict:
    sample, base, n_eligible = select(cutoff)
    cache = json.loads(PRICES.read_text("utf-8")) if PRICES.exists() else {}
    for i, q in enumerate(sample):
        market_price(q, cache)
        if i % 25 == 24:
            PRICES.write_text(json.dumps(cache), encoding="utf-8")
    PRICES.write_text(json.dumps(cache), encoding="utf-8")
    ys = [q["yes"] for q in sample]
    rate = sum(q["yes"] for q in base) / len(base)
    priced = [(cache[q["id"]], q["yes"]) for q in sample if cache.get(q["id"]) is not None]
    return {"cutoff": cutoff, "eligible": n_eligible, "n": len(sample), "share_yes_in_sample": round(sum(ys) / len(ys), 3),
            "span": [sample[0]["start"], sample[-1]["start"]],
            "brier": {"half": 0.25, "base_rate": round(brier([rate] * len(ys), ys), 4),
                      "market": round(brier([p for p, _ in priced], [y for _, y in priced]), 4)},
            "base_rate": round(rate, 3), "n_with_market_price": len(priced)}


def run(cutoff: str, dry: bool, limit: int | None) -> None:
    sample, base, _ = select(cutoff)
    if limit:
        sample = sample[:limit]
    ask = stub if dry else chat
    tag = "dryrun" if dry else re.sub(r"[^A-Za-z0-9_.-]", "_", os.environ["FORECAST_MODEL"])
    path = HERE / f"forecasts_{tag}.json"
    done = json.loads(path.read_text("utf-8")) if path.exists() else {}
    for i, q in enumerate(sample):
        if q["id"] not in done:
            done[q["id"]] = forecast(q, ask)
            if i % 10 == 9:
                path.write_text(json.dumps(done), encoding="utf-8")
                print(f"{i + 1}/{len(sample)}", flush=True)
    path.write_text(json.dumps(done), encoding="utf-8")

    kept = [q for q in sample if done.get(q["id"])]
    ys = [q["yes"] for q in kept]
    arms = {a: [done[q["id"]][a] for q in kept] for a in ("L", "L2", "LE1", "LE2")}
    rate = sum(q["yes"] for q in base) / len(base)
    out = {"model": "STUB (dry run; numbers are meaningless)" if dry else os.environ["FORECAST_MODEL"], "cutoff": cutoff,
           "n_sampled": len(sample), "n_scored": len(kept), "n_dropped": len(sample) - len(kept),
           "brier": {"half": 0.25, "base_rate": round(brier([rate] * len(ys), ys), 4),
                     **{a: round(brier(p, ys), 4) for a, p in arms.items()}},
           "LE2_minus_L2": paired(arms["LE2"], arms["L2"], ys), "LE2_minus_L": paired(arms["LE2"], arms["L"], ys)}
    out["pass"] = out["LE2_minus_L2"]["ci95"][1] < 0 and out["LE2_minus_L"]["ci95"][1] < 0
    (HERE / f"results_{tag}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


def parity() -> float:
    drivers = [{"name": "a", "sign": 1.0, "strength": 0.5, "level": 0.6, "lag": 2},
               {"name": "b", "sign": -1.0, "strength": 0.8, "level": 0.4, "lag": 0},
               {"name": "c", "sign": 1.0, "strength": 0.2, "level": 1.0, "lag": 5}]
    worst = 0.0
    for mults in ((1.0, 1.0, 1.0), (0.5, 1.5, 1.0), (1.5, 0.5, 1.5)):
        for turns in (4, 13, 26):
            worst = max(worst, abs(outcome_fast(-0.3, drivers, mults, turns) - outcome_engine(-0.3, drivers, mults, turns)))
    return worst


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["collect", "baselines", "run", "parity"])
    ap.add_argument("--cutoff")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    if a.cmd == "collect":
        collect()
    elif a.cmd == "parity":
        print("worst difference from the engine:", parity())
    elif a.cmd == "baselines":
        print(json.dumps(baselines(a.cutoff), indent=1))
    else:
        run(a.cutoff, a.dry_run, a.limit)
