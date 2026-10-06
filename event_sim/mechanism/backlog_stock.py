"""
H2 falsification test: does a real order backlog behave like a STOCK?

H2 says `order_backlog` should integrate a flow imbalance rather than relax toward causal
pressure — the same structural claim as H1, one layer downstream.

The H1 test could lean on the increment-shape argument, because that queue had a clean
build phase under a flat driver. A backlog does not give us that luxury: the driver moves
throughout, so shape alone is ambiguous. The distinctive signature of a stock is instead
**path dependence**:

    RELAXATION  backlog is a function of CURRENT pressure.
                Same pressure  ->  same backlog, whatever the history.
    STOCK       backlog is the INTEGRAL of past imbalances.
                Same pressure  ->  different backlog depending on the path taken.

So the decisive test is hysteresis: compare backlog at matched pressure on the way UP with
the way DOWN of one cycle. H2 predicts the down-leg sits HIGHER — a backlog has to be
worked off, it cannot relax away.

Two traps this module is built to avoid:

1. **Circularity.** US Census M3 derives New Orders as Shipments + change in Unfilled
   Orders. Testing "backlog = integral(new orders - shipments)" would therefore be an
   accounting identity, not a finding. The pressure variable used here is Federal Reserve
   capacity utilisation, measured independently.
2. **Trend masquerading as hysteresis.** Backlog cover trends upward over the window, so an
   uncontrolled matched-pressure comparison across years measures the trend. Cover is
   linearly detrended and the comparison is restricted to a single cycle.

No LLM, no RNG, no simulator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Sequence

from event_sim.mechanism.queue_stock import MECHANISM_DATA_DIR, shape_diagnostics

#: H2's prediction, stated before looking: on the way down from a cycle peak, backlog at
#: matched pressure should be HIGHER than on the way up.
H2_PREDICTION = (
    "positive hysteresis gap: detrended backlog cover on the down-leg exceeds the up-leg at "
    "matched capacity utilisation"
)


@dataclass
class BacklogSeries:
    """Monthly backlog, shipments and an independently measured pressure variable."""

    id: str
    title: str
    definition: str = ""
    months: list[str] = field(default_factory=list)
    backlog: list[float] = field(default_factory=list)
    shipments: list[float] = field(default_factory=list)
    pressure: list[float] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    circularity_warning: str = ""
    sources: list[str] = field(default_factory=list)

    def cover(self) -> list[float]:
        """Backlog expressed in months of shipments: scale-free and inflation-robust."""
        return [b / s for b, s in zip(self.backlog, self.shipments)]


def load_backlog_series(series_id: str) -> BacklogSeries:
    path = MECHANISM_DATA_DIR / f"{series_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"No backlog series {series_id!r} in {MECHANISM_DATA_DIR}")
    data = json.loads(path.read_text(encoding="utf-8"))
    obs = data.get("observations", [])
    return BacklogSeries(
        id=str(data["id"]),
        title=str(data.get("title") or data["id"]),
        definition=str(data.get("definition") or ""),
        months=[str(o["month"]) for o in obs],
        backlog=[float(o["unfilled_orders_musd"]) for o in obs],
        shipments=[float(o["shipments_musd"]) for o in obs],
        pressure=[float(o["capacity_utilisation_pct"]) for o in obs],
        limitations=[str(x) for x in (data.get("limitations") or [])],
        circularity_warning=str(data.get("circularity_warning") or ""),
        sources=[str(x) for x in (data.get("sources") or [])],
    )


def _linear_detrend(values: Sequence[float]) -> tuple[list[float], float]:
    """Remove a least-squares linear trend. Returns (residuals, slope per period)."""
    n = len(values)
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(values) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, values)) / denom
    intercept = my - slope * mx
    return [y - (intercept + slope * i) for i, y in enumerate(values)], slope


def hysteresis_test(
    series: BacklogSeries,
    *,
    bins: Sequence[tuple[float, float]] = ((76.5, 77.5), (77.5, 78.5)),
    min_per_leg: int = 3,
) -> dict[str, Any]:
    """
    Matched-pressure comparison between the up-leg and down-leg of one cycle, on detrended
    backlog cover.

    A positive gap supports H2 (backlog persists on the way down). A negative gap means
    backlog was actually *lower* at the same pressure on the way down, which is the opposite
    of what a stock predicts.
    """
    cover = series.cover()
    detrended, slope = _linear_detrend(cover)
    pressure, months = series.pressure, series.months

    trough = min(range(len(pressure)), key=lambda i: pressure[i])
    after = range(trough + 1, len(pressure))
    if not list(after):
        return {"error": "no cycle after the pressure trough"}
    peak = max(after, key=lambda i: pressure[i])

    up = list(range(trough, peak + 1))
    down = list(range(peak + 1, len(pressure)))

    rows: list[dict[str, Any]] = []
    for low, high in bins:
        up_vals = [detrended[i] for i in up if low <= pressure[i] < high]
        down_vals = [detrended[i] for i in down if low <= pressure[i] < high]
        if len(up_vals) < min_per_leg or len(down_vals) < min_per_leg:
            rows.append({"bin": [low, high], "n_up": len(up_vals), "n_down": len(down_vals),
                         "gap": None, "note": "too few matched observations"})
            continue
        up_mean = sum(up_vals) / len(up_vals)
        down_mean = sum(down_vals) / len(down_vals)
        rows.append({
            "bin": [low, high], "n_up": len(up_vals), "n_down": len(down_vals),
            "up_mean_detrended_cover": up_mean,
            "down_mean_detrended_cover": down_mean,
            "gap": down_mean - up_mean,
            "supports_h2": down_mean > up_mean,
        })

    scored = [r for r in rows if r.get("gap") is not None]
    mean_gap = (sum(r["gap"] for r in scored) / len(scored)) if scored else None
    return {
        "prediction": H2_PREDICTION,
        "cycle": {
            "pressure_trough": months[trough], "pressure_trough_value": pressure[trough],
            "pressure_peak": months[peak], "pressure_peak_value": pressure[peak],
            "up_leg_months": len(up), "down_leg_months": len(down),
        },
        "cover_trend_per_month": slope,
        "bins": rows,
        "mean_gap": mean_gap,
        "supports_h2": (mean_gap is not None and mean_gap > 0),
        "note": (
            "Cover was linearly detrended before comparison; without that step the raw "
            "matched-pressure spread measures the secular trend rather than hysteresis."
        ),
    }


def persistence_test(series: BacklogSeries, *, tolerance: float = 0.5) -> dict[str, Any]:
    """
    After pressure returns to its pre-shock level, does backlog return with it?

    Relaxation says yes, promptly. A stock says no — the accumulated backlog is still there
    and has to be worked off.
    """
    cover, pressure, months = series.cover(), series.pressure, series.months
    baseline_pressure = pressure[0]
    trough = min(range(len(pressure)), key=lambda i: pressure[i])
    peak = max(range(trough + 1, len(pressure)), key=lambda i: pressure[i])

    returned = next(
        (i for i in range(peak + 1, len(pressure)) if pressure[i] <= baseline_pressure + tolerance),
        None,
    )
    if returned is None:
        return {"returned_to_baseline_pressure": False,
                "note": "pressure did not return to its starting level within the window"}
    return {
        "returned_to_baseline_pressure": True,
        "baseline_month": months[0],
        "baseline_pressure": baseline_pressure,
        "baseline_cover": cover[0],
        "return_month": months[returned],
        "return_pressure": pressure[returned],
        "cover_at_return": cover[returned],
        "cover_gap_vs_baseline": cover[returned] - cover[0],
        "cover_ratio_vs_baseline": cover[returned] / cover[0] if cover[0] else None,
        "supports_h2": cover[returned] > cover[0],
        "note": (
            "A backlog still elevated when pressure has returned to its starting level is "
            "consistent with a stock that must be worked off. Note this comparison is NOT "
            "detrended, so a secular trend in cover will also produce a positive gap."
        ),
    }


def compare_h2(series: BacklogSeries) -> dict[str, Any]:
    """
    Run the H2 test and return a verdict.

    The verdict is deliberately harder to pass than H1's, because the decisive evidence here
    is a single controlled comparison rather than a structural impossibility argument:
    `H2 SUPPORTED` requires the detrended hysteresis gap to have the predicted sign.
    """
    cover = series.cover()
    shape = shape_diagnostics(cover)
    hysteresis = hysteresis_test(series)
    persistence = persistence_test(series)

    gap = hysteresis.get("mean_gap")
    if gap is None:
        verdict, reason = "inconclusive", "no bin had enough matched observations on both legs"
    elif gap > 0:
        verdict = "H2 SUPPORTED"
        reason = (
            "at matched capacity utilisation, detrended backlog cover is higher on the "
            "down-leg than the up-leg — the path dependence a stock predicts"
        )
    else:
        verdict = "H2 NOT SUPPORTED"
        reason = (
            "at matched capacity utilisation, detrended backlog cover is LOWER on the "
            "down-leg than the up-leg — the opposite of what a stock predicts. Note the "
            "test is underpowered: national aggregates average together industries that "
            "are accumulating and industries that are draining"
        )

    return {
        "series": series.id,
        "title": series.title,
        "definition": series.definition,
        "n_months": len(series.months),
        "prediction_stated_before_testing": H2_PREDICTION,
        "cover_shape": shape,
        "hysteresis": hysteresis,
        "persistence": persistence,
        "verdict": verdict,
        "reason": reason,
        "circularity_warning": series.circularity_warning,
        "limitations": list(series.limitations),
        "framing": (
            "A negative result here is NOT a refutation of H2 for a single disrupted node. "
            "It says the predicted signature is absent in national aggregate data, which is "
            "the wrong resolution for a node-level claim. H2 should be retested if a "
            "node-level backlog series can ever be sourced — not deleted on this evidence."
        ),
    }
