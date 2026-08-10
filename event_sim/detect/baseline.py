"""
Descriptive baseline statistics for a small-count occupancy series.

Everything here is descriptive. Nothing fits a distribution, estimates a parameter for
forecasting, or assigns a probability to a future observation. The question being answered
is narrow: *is ordinary variation small enough that a multi-day disruption would stand out
from it?* — and that question is answered with robust summaries and a dispersion diagnostic,
not with a model.

The Gaussian caveat is the reason for the care. Daily occupancy at Hampton Roads is a count
in the low single digits. At that scale a normal approximation is not merely imprecise, it
is the wrong shape: it puts mass below zero, and it treats the mean-variance coupling that
counts inherently have as if it were an independent parameter. So the dispersion index
below is reported as a *description* of how the observed spread compares with the
mean-equals-variance behaviour a simple count process would show. It is not a test, it does
not license a Poisson model, and no p-value is computed from it.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import date
from typing import Any, Sequence


@dataclass(frozen=True)
class Distribution:
    """Robust summary of one numeric series."""

    n: int
    mean: float
    median: float
    variance: float
    stdev: float
    mad: float                    # median absolute deviation
    minimum: float
    p10: float
    p25: float
    p75: float
    p90: float
    maximum: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile. Chosen over interpolation because these are counts, and an
    interpolated 'occupancy of 3.4 vessels' is not a thing that can be observed."""
    if not sorted_values:
        return float("nan")
    idx = max(0, min(len(sorted_values) - 1, int(round(q * (len(sorted_values) - 1)))))
    return float(sorted_values[idx])


def describe(values: Sequence[float]) -> Distribution:
    vals = [float(v) for v in values]
    if not vals:
        nan = float("nan")
        return Distribution(0, nan, nan, nan, nan, nan, nan, nan, nan, nan, nan, nan)

    ordered = sorted(vals)
    med = statistics.median(ordered)
    var = statistics.pvariance(vals) if len(vals) > 1 else 0.0
    return Distribution(
        n=len(vals),
        mean=round(statistics.fmean(vals), 4),
        median=round(med, 4),
        variance=round(var, 4),
        stdev=round(var ** 0.5, 4),
        mad=round(statistics.median([abs(v - med) for v in vals]), 4),
        minimum=ordered[0],
        p10=_percentile(ordered, 0.10),
        p25=_percentile(ordered, 0.25),
        p75=_percentile(ordered, 0.75),
        p90=_percentile(ordered, 0.90),
        maximum=ordered[-1],
    )


def dispersion_index(values: Sequence[float]) -> float | None:
    """variance / mean.

    Descriptive only. A simple count process with no clustering sits near 1; values well
    above 1 mean the observations cluster more than independent counts would, which is what
    persistent occupancy looks like. Reported so the reader can see whether ordinary
    variation is already over-dispersed *before* any event is invoked to explain spread.
    """
    vals = [float(v) for v in values]
    if not vals:
        return None
    mean = statistics.fmean(vals)
    if mean <= 0:
        return None
    return round(statistics.pvariance(vals) / mean, 4)


def autocorrelation(values: Sequence[float], lag: int = 1) -> float | None:
    """Lag-k sample autocorrelation. Matters here because consecutive days are obviously not
    independent — a ship at anchor on Tuesday is usually still there on Wednesday — and that
    dependence is what makes a 'persistence' detection rule non-trivial."""
    vals = [float(v) for v in values]
    if len(vals) <= lag + 1:
        return None
    mean = statistics.fmean(vals)
    denom = sum((v - mean) ** 2 for v in vals)
    if denom == 0:
        return None
    num = sum((vals[i] - mean) * (vals[i + lag] - mean) for i in range(len(vals) - lag))
    return round(num / denom, 4)


def weekday_effect(dates: Sequence[str], values: Sequence[float]) -> dict[str, float]:
    """Mean value by weekday name. Reported to show whether a weekly cycle exists that a
    detection rule would otherwise mistake for signal."""
    buckets: dict[int, list[float]] = defaultdict(list)
    for d, v in zip(dates, values):
        buckets[date.fromisoformat(d).weekday()].append(float(v))
    names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    return {
        names[k]: round(statistics.fmean(vs), 3) for k, vs in sorted(buckets.items()) if vs
    }


def per_window(dates: Sequence[str], windows: Sequence[str | None], values: Sequence[float]):
    """Mean and max per sampled window, so between-window drift is visible."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for w, v in zip(windows, values):
        if w:
            buckets[w].append(float(v))
    return {
        w: {"n": len(vs), "mean": round(statistics.fmean(vs), 3), "max": max(vs)}
        for w, vs in sorted(buckets.items())
    }


def value_histogram(values: Sequence[float]) -> dict[int, int]:
    """Exact count of each observed integer level — the most honest view of a small-count
    series, and the one that shows immediately whether dynamic range exists."""
    return dict(sorted(Counter(int(v) for v in values).items()))
