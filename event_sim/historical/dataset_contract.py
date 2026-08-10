"""
Event Validation Dataset contract.

What a historical event must supply before it can be used as a held-out test. Written as a
reusable, checkable contract rather than prose so that a future candidate is accepted or
rejected by the same rule that rejected the last one — and so "we couldn't find data" is a
specific, actionable statement rather than a shrug.

The contract deliberately separates three things that have each caused a failure here:

    what is measured        (metric + unit)
    how it was obtained     (observation_type: observed / scheduled / derived / reported)
    what it means over time (definition_version — a change invalidates splicing)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

#: How a value came to exist. `scheduled` is kept distinct from `observed` because Panama
#: showed an official, precise, primary-source schedule can be the wrong quantity entirely.
OBSERVATION_TYPES = ("observed", "reported", "derived", "scheduled", "estimated")

#: Metrics that fall inside H1's causal scope, i.e. can serve as a primary endpoint.
H1_SENSITIVE_METRICS = (
    "vessel_queue", "waiting_vessels", "average_waiting_time", "anchorage_wait",
    "port_dwell_time", "container_dwell_time", "local_shipping_delay",
)

#: Metrics that describe the driver rather than the outcome.
DRIVER_METRICS = ("throughput", "arrivals", "departures", "port_capacity", "berth_availability")

#: Frequencies, best first.
FREQUENCY_RANK = {"daily": 3, "weekly": 2, "monthly": 1, "irregular": 0}


class DatasetContractError(ValueError):
    """Raised when a dataset does not satisfy the held-out validation contract."""


@dataclass
class DatasetRecord:
    """One observation in an event validation dataset."""

    event_id: str
    timestamp: str
    location: str
    metric: str
    value: float
    unit: str
    observation_type: str
    source_id: str
    definition_version: str = "v1"
    quality: str = "observed"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "timestamp": self.timestamp, "location": self.location,
            "metric": self.metric, "value": self.value, "unit": self.unit,
            "observation_type": self.observation_type, "source_id": self.source_id,
            "definition_version": self.definition_version, "quality": self.quality,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DatasetRecord:
        return cls(
            event_id=str(d["event_id"]), timestamp=str(d["timestamp"]),
            location=str(d["location"]), metric=str(d["metric"]),
            value=float(d["value"]), unit=str(d.get("unit") or ""),
            observation_type=str(d.get("observation_type") or "observed"),
            source_id=str(d.get("source_id") or ""),
            definition_version=str(d.get("definition_version") or "v1"),
            quality=str(d.get("quality") or "observed"), note=str(d.get("note") or ""),
        )


@dataclass
class DatasetRequirement:
    """The predeclared minimum for a held-out validation dataset."""

    min_h1_sensitive_series: int = 1
    min_observations_in_window: int = 6
    min_pre_event_observations: int = 2
    min_post_peak_observations: int = 2
    allowed_frequencies: tuple[str, ...] = ("daily", "weekly", "monthly")
    require_single_definition_version: bool = True
    forbid_scheduled_as_outcome: bool = True
    max_interpolation_gap: int = 1  # in observation steps; larger gaps may not be filled

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_h1_sensitive_series": self.min_h1_sensitive_series,
            "min_observations_in_window": self.min_observations_in_window,
            "min_pre_event_observations": self.min_pre_event_observations,
            "min_post_peak_observations": self.min_post_peak_observations,
            "allowed_frequencies": list(self.allowed_frequencies),
            "require_single_definition_version": self.require_single_definition_version,
            "forbid_scheduled_as_outcome": self.forbid_scheduled_as_outcome,
            "max_interpolation_gap": self.max_interpolation_gap,
        }


def validate_dataset(
    records: Sequence[DatasetRecord],
    *,
    event_start: str,
    requirement: DatasetRequirement | None = None,
) -> dict[str, Any]:
    """
    Check a candidate dataset against the contract.

    Returns a report with `qualifies` and an explicit list of failures. Failures are the
    useful output: they say precisely what a future acquisition must fix.
    """
    req = requirement or DatasetRequirement()
    failures: list[str] = []

    by_metric: dict[str, list[DatasetRecord]] = {}
    for record in records:
        by_metric.setdefault(record.metric, []).append(record)

    sensitive = {m: rs for m, rs in by_metric.items() if m in H1_SENSITIVE_METRICS}
    if len(sensitive) < req.min_h1_sensitive_series:
        failures.append(
            f"no H1-sensitive series: needs at least {req.min_h1_sensitive_series} of "
            f"{list(H1_SENSITIVE_METRICS)}, found {sorted(by_metric)}"
        )

    for metric, rows in sensitive.items():
        ordered = sorted(rows, key=lambda r: r.timestamp)
        if len(ordered) < req.min_observations_in_window:
            failures.append(
                f"{metric}: {len(ordered)} observations, needs >= {req.min_observations_in_window} "
                f"to resolve accumulation and peak"
            )
        pre = [r for r in ordered if r.timestamp < event_start]
        if len(pre) < req.min_pre_event_observations:
            failures.append(
                f"{metric}: {len(pre)} pre-event observations, needs >= "
                f"{req.min_pre_event_observations} to establish a baseline"
            )
        if req.require_single_definition_version:
            versions = {r.definition_version for r in ordered}
            if len(versions) > 1:
                failures.append(
                    f"{metric}: measurement definition changes mid-series ({sorted(versions)}); "
                    f"segment it rather than splicing"
                )
        if req.forbid_scheduled_as_outcome:
            scheduled = [r for r in ordered if r.observation_type == "scheduled"]
            if scheduled:
                failures.append(
                    f"{metric}: {len(scheduled)} record(s) are 'scheduled', not observed — a "
                    f"schedule is an intention, not an outcome"
                )
        values = [r.value for r in ordered]
        if values:
            peak_index = max(range(len(values)), key=lambda i: values[i])
            after_peak = len(values) - peak_index - 1
            if after_peak < req.min_post_peak_observations:
                failures.append(
                    f"{metric}: only {after_peak} observation(s) after the peak, needs >= "
                    f"{req.min_post_peak_observations} to measure clearance timing"
                )

    return {
        "qualifies": not failures,
        "failures": failures,
        "h1_sensitive_series": sorted(sensitive),
        "driver_series": sorted(m for m in by_metric if m in DRIVER_METRICS),
        "other_series": sorted(m for m in by_metric
                               if m not in H1_SENSITIVE_METRICS and m not in DRIVER_METRICS),
        "requirement": req.to_dict(),
    }


def interpolation_allowed(gap_steps: int, requirement: DatasetRequirement | None = None) -> bool:
    """
    Whether a gap may be filled.

    Short gaps may be bridged with a documented rule; long ones may not, because filling
    them manufactures observations that were never measured and then scores the model
    against them.
    """
    req = requirement or DatasetRequirement()
    return 0 < gap_steps <= req.max_interpolation_gap
