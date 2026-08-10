"""
Measurement-risk registry.

This project has now hit the same class of problem four separate times, each in a different
disguise. Left as anecdotes in four reports they teach nothing; as a registry they become a
checklist a future variable mapping must answer.

    Yantian    a global monthly series stood in for a local weekly variable
    Panama     an official, precise, primary-source number measured the wrong quantity
    San Pedro  the measurement definition changed partway through the series
    H2         a secular trend produced apparent hysteresis until it was removed

The registry is deliberately about *measurement*, not about models: every entry describes a
way that a number can be real, correct, and still not mean what a model needs it to mean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class MeasurementRisk:
    """One recurring way an observation can mislead."""

    id: str
    name: str
    description: str
    encountered_in: tuple[str, ...]
    detection: str
    mitigation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "encountered_in": list(self.encountered_in),
            "detection": self.detection, "mitigation": self.mitigation,
        }


MEASUREMENT_RISKS: tuple[MeasurementRisk, ...] = (
    MeasurementRisk(
        id="geographic_mismatch",
        name="Geographic mismatch",
        description=(
            "The series covers a wider population than the modelled system, so it moves for "
            "reasons the model does not contain and cannot move much for reasons it does."
        ),
        encountered_in=("yantian_2021",),
        detection="Compare the geographic scope of the series with the scope of the event.",
        mitigation="Require a local series; if only an aggregate exists, record it as a proxy and expect direction only.",
    ),
    MeasurementRisk(
        id="temporal_aggregation",
        name="Temporal aggregation",
        description=(
            "The series is coarser than the dynamics under test, so accumulation and peak "
            "timing are averaged away before they can be measured."
        ),
        encountered_in=("yantian_2021",),
        detection="Count observations spanning the event window; fewer than ~4 cannot resolve a peak.",
        mitigation="Require daily/weekly data, or accept that timing cannot be tested.",
    ),
    MeasurementRisk(
        id="proxy_mismatch",
        name="Proxy mismatch",
        description="A stand-in variable is used whose relationship to the modelled variable is itself an assumption.",
        encountered_in=("yantian_2021",),
        detection="Ask whether the published quantity IS the variable, or merely correlates with it.",
        mitigation="Record a ProxyMapping with explicit limitations; never treat the proxy as the variable.",
    ),
    MeasurementRisk(
        id="scheduled_vs_observed",
        name="Scheduled vs observed",
        description=(
            "An administrative plan, allocation or schedule is mistaken for realised physical "
            "activity. It can be official, precise, primary-source — and still the wrong quantity."
        ),
        encountered_in=("panama_2023",),
        detection="Ask who set the number and whether reality was free to differ from it.",
        mitigation="Classify every quantity as physical / booking / scheduled / actual before use.",
    ),
    MeasurementRisk(
        id="definition_change",
        name="Definition change mid-series",
        description=(
            "The measurement definition changes during the window, so a jump in the data is a "
            "change in the instrument rather than in the world."
        ),
        encountered_in=("san_pedro_2021",),
        detection="Look for methodology notes, regime changes, or a step with no physical cause.",
        mitigation="Segment the series by definition version; never splice across a change.",
    ),
    MeasurementRisk(
        id="administrative_rationing",
        name="Administrative rationing",
        description=(
            "A queue or backlog is held down by a booking, auction or quota system, so it "
            "cannot free-run and the accumulation dynamic is suppressed by design."
        ),
        encountered_in=("panama_2023",),
        detection="Ask whether access to the constrained resource is allocated administratively.",
        mitigation="Reject as a queue-mechanism test; the mechanism is unfalsifiable there.",
    ),
    MeasurementRisk(
        id="circular_measurement",
        name="Circular measurement",
        description=(
            "The 'driver' is derived from the outcome by an accounting identity, so any fit is "
            "arithmetic rather than evidence."
        ),
        encountered_in=("us_manufacturing_backlog",),
        detection="Check whether the statistical agency computes one series from the other.",
        mitigation="Use a driver measured by a different agency or instrument.",
    ),
    MeasurementRisk(
        id="secular_trend",
        name="Secular trend",
        description=(
            "A long-run trend in the level produces an apparent path dependence or persistence "
            "that vanishes once removed."
        ),
        encountered_in=("us_manufacturing_backlog",),
        detection="Compare matched-condition observations that are years apart versus within one cycle.",
        mitigation="Detrend, and restrict comparisons to a single cycle.",
    ),
    MeasurementRisk(
        id="aggregation_masking",
        name="Aggregation masking",
        description=(
            "Aggregating across units averages together some that are accumulating and some "
            "that are draining, attenuating the very dynamic under test."
        ),
        encountered_in=("us_manufacturing_backlog",),
        detection="Ask whether the aggregate contains units expected to move in opposite directions.",
        mitigation="Use node-level data, or report the test as underpowered rather than negative.",
    ),
)

RISK_BY_ID: dict[str, MeasurementRisk] = {r.id: r for r in MEASUREMENT_RISKS}
RISK_IDS: tuple[str, ...] = tuple(r.id for r in MEASUREMENT_RISKS)


class MeasurementRiskError(ValueError):
    """Raised when a mapping references an unknown risk or declares none at all."""


def validate_risk_ids(risk_ids: Iterable[str], *, context: str = "") -> list[str]:
    """Every declared risk must exist in the registry."""
    problems: list[str] = []
    for risk_id in risk_ids:
        if risk_id not in RISK_BY_ID:
            problems.append(
                f"{context or 'mapping'}: unknown measurement risk {risk_id!r}; "
                f"known: {sorted(RISK_BY_ID)}"
            )
    return problems


def assess_mapping(mapping: Any) -> dict[str, Any]:
    """
    Report which risks a ProxyMapping declares, and which its own metadata suggests it
    should have declared.

    The heuristics are deliberately crude and advisory: their job is to make an author
    justify an omission, not to decide for them.
    """
    declared = list((getattr(mapping, "parameters", {}) or {}).get("measurement_risks", []))
    problems = validate_risk_ids(declared, context=f"mapping {getattr(mapping, 'id', '?')}")

    suspected: list[str] = []
    text = " ".join(str(x).lower() for x in (
        getattr(mapping, "limitations", ""), getattr(mapping, "rationale", ""),
        getattr(mapping, "source_metric", ""),
    ))
    if getattr(mapping, "mapping_type", "") == "proxy" and "proxy_mismatch" not in declared:
        suspected.append("proxy_mismatch")
    for keyword, risk_id in (
        ("global", "geographic_mismatch"), ("national", "geographic_mismatch"),
        ("monthly", "temporal_aggregation"), ("quarterly", "temporal_aggregation"),
        ("booking", "scheduled_vs_observed"), ("schedule", "scheduled_vs_observed"),
        ("definition", "definition_change"), ("trend", "secular_trend"),
    ):
        if keyword in text and risk_id not in declared and risk_id not in suspected:
            suspected.append(risk_id)

    return {
        "mapping": getattr(mapping, "id", "?"),
        "declared_risks": declared,
        "suspected_undeclared": suspected,
        "problems": problems,
        "note": (
            "Suspected risks are advisory heuristics from the mapping's own text. They are "
            "prompts for the author, not automatic failures."
        ),
    }


def registry_summary() -> list[dict[str, Any]]:
    """The registry, for reports and the API."""
    return [risk.to_dict() for risk in MEASUREMENT_RISKS]
