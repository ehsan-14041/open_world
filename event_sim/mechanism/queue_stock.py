"""
H1 falsification test: does a real port queue behave like a STOCK or like a RELAXATION
variable?

This is the structural question behind the model's measured "recovers too early" defect.
The current engine evolves every variable by relaxation toward causal pressure:

    RELAXATION   q(t+1) = q(t) + r * (P(t) - q(t))          r in (0, 1]

H1 proposes that a queue instead integrates an imbalance between arrivals and the rate at
which they can be cleared:

    STOCK        q(t+1) = q(t) + (A(t) - C)                 clipped at zero

The two are distinguishable **from the shape of the queue alone**, without any simulation
and without knowing the driver, because they make incompatible predictions about increments:

    under a CONSTANT driver, relaxation increments must DECAY geometrically
    (each step closes a fixed fraction of a shrinking gap);
    stock increments stay CONSTANT (a fixed imbalance integrates linearly).

So a queue whose increments hold steady or grow over many periods cannot be relaxation
toward a steady driver. The decisive question then becomes: *what would the driver have had
to do* for each model to produce the observed queue? That is `implied_driver_growth`, and it
is checkable against the public record without fitting anything.

No LLM, no RNG, no simulator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MECHANISM_DATA_DIR = _PROJECT_ROOT / "event_sim" / "mechanism_data"

#: The two competing forms. Named so a report can refer to them unambiguously.
CANDIDATES = {
    "relaxation": "q(t+1) = q(t) + r*(P(t) - q(t))  — the current engine's form",
    "stock": "q(t+1) = q(t) + (A(t) - C), clipped at 0  — H1, queue as an integrating stock",
}


@dataclass
class QueueObservation:
    """One observed queue count, with the provenance and definition it was measured under."""

    period: str
    index: int
    value: float
    unit: str = "vessels"
    definition: str = ""
    source: str = ""
    status: str = "observed"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period, "index": self.index, "value": self.value,
            "unit": self.unit, "definition": self.definition, "source": self.source,
            "status": self.status, "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QueueObservation:
        return cls(
            period=str(d["period"]),
            index=int(d["index"]),
            value=float(d["value"]),
            unit=str(d.get("unit") or "vessels"),
            definition=str(d.get("definition") or ""),
            source=str(d.get("source_id") or d.get("source") or ""),
            status=str(d.get("status") or "observed"),
            note=str(d.get("note") or ""),
        )


@dataclass
class SeriesBundle:
    """A queue series plus everything needed to interpret it."""

    id: str
    title: str
    observations: list[QueueObservation] = field(default_factory=list)
    definition: str = ""
    driver_context: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)

    def values(self) -> list[float]:
        return [o.value for o in sorted(self.observations, key=lambda o: o.index)]


def load_queue_series(series_id: str) -> SeriesBundle:
    """Load a sourced queue series from event_sim/mechanism_data/."""
    path = MECHANISM_DATA_DIR / f"{series_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"No mechanism series {series_id!r} in {MECHANISM_DATA_DIR}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return SeriesBundle(
        id=str(data["id"]),
        title=str(data.get("title") or data["id"]),
        observations=[QueueObservation.from_dict(o) for o in data.get("observations", [])],
        definition=str(data.get("definition") or ""),
        driver_context=dict(data.get("driver_context") or {}),
        limitations=[str(x) for x in (data.get("limitations") or [])],
        excluded=[dict(x) for x in (data.get("excluded") or [])],
    )


# --------------------------------------------------------------------------------------
# Shape diagnostics — the part that needs no fitting at all
# --------------------------------------------------------------------------------------


def shape_diagnostics(values: Sequence[float]) -> dict[str, Any]:
    """
    Increment analysis. The single most discriminating statistic between the two forms,
    and it requires no parameters, no driver and no fit.

    Under relaxation toward a steady driver, increments must decay. Under a stock with a
    steady imbalance, they stay flat. Growing increments are consistent with neither a
    steady driver under relaxation nor a steady imbalance — but only relaxation is
    *structurally* barred from producing them without the driver itself accelerating.
    """
    if len(values) < 3:
        return {"n": len(values), "verdict": "too few points"}
    increments = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    decaying = all(b < a for a, b in zip(increments, increments[1:]))
    non_decreasing = all(b >= a for a, b in zip(increments, increments[1:]))
    ratios = [
        (b / a) if abs(a) > 1e-9 else None
        for a, b in zip(increments, increments[1:])
    ]
    return {
        "n": len(values),
        "values": list(values),
        "increments": increments,
        "increment_ratios": ratios,
        "monotonic_rise": all(b > a for a, b in zip(values, values[1:])),
        "increments_decaying": decaying,
        "increments_non_decreasing": non_decreasing,
        "verdict": (
            "increments decay — consistent with relaxation toward a steady driver"
            if decaying else
            "increments do not decay — INCONSISTENT with relaxation toward a steady driver"
        ),
        "reasoning": (
            "Relaxation closes a fixed fraction of the remaining gap each period, so with a "
            "steady driver its increments must shrink geometrically. Increments that hold "
            "or grow require the driver itself to be rising."
        ),
    }


# --------------------------------------------------------------------------------------
# Fitting the two candidates
# --------------------------------------------------------------------------------------


def _sse(observed: Sequence[float], predicted: Sequence[float]) -> float:
    return sum((o - p) ** 2 for o, p in zip(observed, predicted))


def fit_relaxation(
    values: Sequence[float],
    *,
    driver: Sequence[float] | None = None,
    grid: Sequence[float] = tuple(i / 100 for i in range(5, 101, 5)),
) -> dict[str, Any]:
    """
    Fit q(t+1) = q(t) + r*(P - q(t)) by grid search over r and a constant driver P.

    A constant P is the honest null for the second half of 2021: the hypothesis that demand
    was elevated but not accelerating. Passing an explicit `driver` overrides it.
    """
    best: dict[str, Any] | None = None
    observed = list(values)
    p_grid = [max(observed) * m for m in (1.0, 1.25, 1.5, 2.0, 3.0, 5.0, 10.0)]

    for r in grid:
        for p_const in p_grid:
            pred = [observed[0]]
            for t in range(len(observed) - 1):
                pressure = float(driver[t]) if driver is not None else p_const
                pred.append(pred[-1] + r * (pressure - pred[-1]))
            sse = _sse(observed, pred)
            if best is None or sse < best["sse"]:
                best = {"model": "relaxation", "r": r, "driver_constant": p_const,
                        "predicted": pred, "sse": sse}
            if driver is not None:
                break
    assert best is not None
    best["rmse"] = (best["sse"] / len(observed)) ** 0.5
    return best


def fit_stock(
    values: Sequence[float],
    *,
    imbalance: Sequence[float] | None = None,
) -> dict[str, Any]:
    """
    Fit q(t+1) = q(t) + k by least squares on a constant net imbalance k.

    One free parameter, closed form: the mean increment. Deliberately the simplest possible
    version of H1 — if even this beats relaxation, the advantage is structural rather than
    the result of extra flexibility.
    """
    observed = list(values)
    if imbalance is None:
        k = (observed[-1] - observed[0]) / max(1, len(observed) - 1)
        flows: list[float] = [k] * (len(observed) - 1)
    else:
        flows = [float(x) for x in imbalance]
    pred = [observed[0]]
    for t in range(len(observed) - 1):
        pred.append(max(0.0, pred[-1] + flows[t]))
    sse = _sse(observed, pred)
    return {
        "model": "stock",
        "net_imbalance_per_period": (flows[0] if flows else 0.0),
        "predicted": pred,
        "sse": sse,
        "rmse": (sse / len(observed)) ** 0.5,
        "free_parameters": 1,
    }


def implied_driver_growth(values: Sequence[float], *, r: float) -> dict[str, Any]:
    """
    What the driver would have had to do for RELAXATION to produce the observed queue.

    Inverting the relaxation law gives P(t) = q(t) + increment(t)/r. Reporting the implied
    driver turns an unfalsifiable model-fit argument into a checkable factual claim: either
    the real driver moved that much, or relaxation is the wrong form. This is the strongest
    part of the test, because it needs no fit — only arithmetic and the public record.
    """
    observed = list(values)
    increments = [observed[i + 1] - observed[i] for i in range(len(observed) - 1)]
    implied = [observed[i] + increments[i] / r for i in range(len(increments))]
    growth = (max(implied) / min(implied)) if min(implied) > 1e-9 else None
    return {
        "response_rate_assumed": r,
        "implied_driver": implied,
        "implied_driver_growth_factor": growth,
        "claim": (
            f"For relaxation with r={r} to produce this queue, the driver must have risen "
            f"by a factor of about {growth:.1f} across the observed window."
            if growth else "implied driver is degenerate"
        ),
        "how_to_falsify": (
            "Compare that growth factor with the actual driver over the same window. If the "
            "real driver was flat, relaxation cannot be the right form regardless of r."
        ),
    }


def compare_candidates(
    bundle: SeriesBundle,
    *,
    relaxation_rates_to_report: Sequence[float] = (0.2, 0.5),
) -> dict[str, Any]:
    """
    Run the whole H1 test on one sourced series and return a verdict.

    The verdict is deliberately conservative: `supported` requires BOTH that the stock form
    fits better AND that the shape is structurally incompatible with relaxation. A better
    fit alone is not enough — one extra parameter can always buy some fit.
    """
    values = bundle.values()
    shape = shape_diagnostics(values)
    relaxation = fit_relaxation(values)
    stock = fit_stock(values)
    implied = {f"r={r}": implied_driver_growth(values, r=r) for r in relaxation_rates_to_report}

    stock_better = stock["sse"] < relaxation["sse"]
    structurally_incompatible = not shape.get("increments_decaying", True)

    if stock_better and structurally_incompatible:
        verdict = "H1 SUPPORTED"
        reason = (
            "the observed queue rises with non-decaying increments, which relaxation toward "
            "a steady driver cannot produce, and the one-parameter stock form fits better"
        )
    elif stock_better:
        verdict = "H1 weakly supported"
        reason = "the stock form fits better, but the shape does not rule out relaxation"
    elif structurally_incompatible:
        verdict = "inconclusive"
        reason = "the shape is inconsistent with steady-driver relaxation, but the stock form does not fit better"
    else:
        verdict = "H1 NOT SUPPORTED"
        reason = "the observed queue is consistent with relaxation toward a driver"

    return {
        "series": bundle.id,
        "title": bundle.title,
        "definition": bundle.definition,
        "n_observations": len(values),
        "candidates": dict(CANDIDATES),
        "shape": shape,
        "relaxation_fit": relaxation,
        "stock_fit": stock,
        "sse_ratio_relaxation_over_stock": (
            relaxation["sse"] / stock["sse"] if stock["sse"] > 1e-9 else None
        ),
        "implied_driver": implied,
        "driver_context": dict(bundle.driver_context),
        "verdict": verdict,
        "reason": reason,
        "limitations": list(bundle.limitations),
        "excluded_observations": list(bundle.excluded),
        "framing": (
            "This is a mechanism test on independent data, not a simulation result. It says "
            "whether a real queue integrates an imbalance; it does not by itself show that "
            "adding a queue stock will fix the model's timing bias. That still requires a "
            "held-out historical event."
        ),
    }
