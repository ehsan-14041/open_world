"""
Evidence provenance schemas.

Three record types, each answering a different question about a number in the model:

  EvidenceSource     — where did this claim come from, and can someone else go check it?
  ProxyMapping       — what real-world metric is standing in for this simulation variable,
                       under what transformation, and what does that cost us?
  FittingProvenance  — how was this coefficient estimated, on what data, how well?
  CalibrationRecord  — how did a historical replay move this coefficient, from what prior?

The point of all four is *inspectability*. A reader must be able to get from a number in a
trajectory back to a URL, a dataset version, or an explicit statement that there is none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: A source must carry at least enough to find it again.
REQUIRED_SOURCE_FIELDS = ("id", "type", "title")

#: Source types we distinguish. `expert_judgement` is a legitimate source type — it is how
#: an honest assumption is recorded, not a way to dress one up as data.
SOURCE_TYPES = (
    "dataset",
    "academic_study",
    "technical_report",
    "industry_index",
    "press_release",
    "news_report",
    "official_statistics",
    "carrier_advisory",
    "expert_judgement",
)

#: How a real metric maps onto a simulation variable.
MAPPING_TYPES = ("direct", "normalized", "derived", "proxy", "index")


def _clean(value: Any) -> Any:
    return value if value not in ("", None) else None


@dataclass
class EvidenceSource:
    """
    One external source, with enough metadata to re-find and re-check it.

    Fields that genuinely do not exist for a source type are left empty rather than
    invented: a press release has no DOI, and a news report has no dataset version.
    """

    id: str
    type: str
    title: str
    publisher: str = ""
    url: str = ""
    publication_year: int | None = None
    published_at: str = ""
    accessed_at: str = ""
    license: str = ""
    notes: str = ""
    # academic
    doi: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    # dataset
    dataset_version: str = ""
    coverage_period: str = ""
    geography: list[str] = field(default_factory=list)
    frequency: str = ""
    variables_used: list[str] = field(default_factory=list)
    # what this source is offered as evidence for (optional, informational)
    supports: dict[str, Any] = field(default_factory=dict)
    #: True when the underlying series is not redistributable and only derived/quoted
    #: values are stored in this repository.
    redistributable: bool = True
    access_note: str = ""

    def is_citable(self) -> bool:
        """A source is citable when someone else could go and check it."""
        return bool(self.url or self.doi or self.publisher)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "publisher": self.publisher,
            "url": self.url,
            "publication_year": self.publication_year,
            "published_at": self.published_at,
            "accessed_at": self.accessed_at,
            "license": self.license,
            "notes": self.notes,
            "doi": self.doi,
            "authors": list(self.authors),
            "journal": self.journal,
            "dataset_version": self.dataset_version,
            "coverage_period": self.coverage_period,
            "geography": list(self.geography),
            "frequency": self.frequency,
            "variables_used": list(self.variables_used),
            "supports": dict(self.supports),
            "redistributable": self.redistributable,
            "access_note": self.access_note,
        }
        return {k: v for k, v in out.items() if v not in ("", None, [], {})} | {
            "id": self.id, "type": self.type, "title": self.title,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EvidenceSource:
        return cls(
            id=str(d["id"]),
            type=str(d.get("type") or "unspecified"),
            title=str(d.get("title") or ""),
            publisher=str(d.get("publisher") or ""),
            url=str(d.get("url") or ""),
            publication_year=(int(d["publication_year"]) if d.get("publication_year") else None),
            published_at=str(d.get("published_at") or ""),
            accessed_at=str(d.get("accessed_at") or ""),
            license=str(d.get("license") or ""),
            notes=str(d.get("notes") or ""),
            doi=str(d.get("doi") or ""),
            authors=[str(a) for a in (d.get("authors") or [])],
            journal=str(d.get("journal") or ""),
            dataset_version=str(d.get("dataset_version") or ""),
            coverage_period=str(d.get("coverage_period") or ""),
            geography=[str(g) for g in (d.get("geography") or [])],
            frequency=str(d.get("frequency") or ""),
            variables_used=[str(v) for v in (d.get("variables_used") or [])],
            supports=dict(d.get("supports") or {}),
            redistributable=bool(d.get("redistributable", True)),
            access_note=str(d.get("access_note") or ""),
        )


@dataclass
class ProxyMapping:
    """
    An explicit statement that a real metric is standing in for a simulation variable.

    `limitations` is required and must be non-empty for `proxy` mappings: if we cannot say
    what the proxy costs us, we do not understand the proxy well enough to use it.
    """

    id: str
    source_metric: str
    simulation_variable: str
    mapping_type: str
    transformation: str = "identity"
    source_unit: str = ""
    target_unit: str = ""
    rationale: str = ""
    limitations: str = ""
    source_ids: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_metric": self.source_metric,
            "simulation_variable": self.simulation_variable,
            "mapping_type": self.mapping_type,
            "transformation": self.transformation,
            "source_unit": self.source_unit,
            "target_unit": self.target_unit,
            "rationale": self.rationale,
            "limitations": self.limitations,
            "source_ids": list(self.source_ids),
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProxyMapping:
        return cls(
            id=str(d["id"]),
            source_metric=str(d.get("source_metric") or ""),
            simulation_variable=str(d.get("simulation_variable") or ""),
            mapping_type=str(d.get("mapping_type") or "proxy"),
            transformation=str(d.get("transformation") or "identity"),
            source_unit=str(d.get("source_unit") or ""),
            target_unit=str(d.get("target_unit") or ""),
            rationale=str(d.get("rationale") or ""),
            limitations=str(d.get("limitations") or ""),
            source_ids=[str(s) for s in (d.get("source_ids") or [])],
            parameters=dict(d.get("parameters") or {}),
        )


@dataclass
class FittingProvenance:
    """How a coefficient was estimated. Required for any edge claiming `empirical`."""

    method: str                       # e.g. "ridge_levels", "lagged_ols"
    dataset_source_ids: list[str] = field(default_factory=list)
    n_observations: int = 0
    tested_lags: list[int] = field(default_factory=list)
    selected_lag: int | None = None
    lag_selection_method: str = ""
    fit_quality: dict[str, Any] = field(default_factory=dict)
    holdout: dict[str, Any] = field(default_factory=dict)
    fitted_at: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "dataset_source_ids": list(self.dataset_source_ids),
            "n_observations": self.n_observations,
            "tested_lags": list(self.tested_lags),
            "selected_lag": self.selected_lag,
            "lag_selection_method": self.lag_selection_method,
            "fit_quality": dict(self.fit_quality),
            "holdout": dict(self.holdout),
            "fitted_at": self.fitted_at,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FittingProvenance:
        return cls(
            method=str(d.get("method") or ""),
            dataset_source_ids=[str(s) for s in (d.get("dataset_source_ids") or [])],
            n_observations=int(d.get("n_observations", 0)),
            tested_lags=[int(x) for x in (d.get("tested_lags") or [])],
            selected_lag=(int(d["selected_lag"]) if d.get("selected_lag") is not None else None),
            lag_selection_method=str(d.get("lag_selection_method") or ""),
            fit_quality=dict(d.get("fit_quality") or {}),
            holdout=dict(d.get("holdout") or {}),
            fitted_at=str(d.get("fitted_at") or ""),
            warnings=[str(w) for w in (d.get("warnings") or [])],
        )


@dataclass
class CalibrationRecord:
    """
    How a historical replay moved a coefficient. Required for `historically_calibrated`.

    `prior_range` is never overwritten — a reader must always be able to see what the
    coefficient was before the replay touched it, and by how much it was allowed to move.
    """

    edge_id: str
    calibration_event_id: str
    method: str
    prior_range: dict[str, float]
    calibrated_range: dict[str, float]
    data_used: list[str] = field(default_factory=list)
    fit_quality: dict[str, Any] = field(default_factory=dict)
    n_observations: int = 0
    max_movement_allowed: float | None = None
    identifiable: bool = True
    timestamp: str = ""
    warnings: list[str] = field(default_factory=list)
    notes: str = ""

    def movement(self) -> float:
        """Absolute change in the central value."""
        return abs(
            float(self.calibrated_range.get("central", 0.0))
            - float(self.prior_range.get("central", 0.0))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "calibration_event_id": self.calibration_event_id,
            "method": self.method,
            "prior_range": dict(self.prior_range),
            "calibrated_range": dict(self.calibrated_range),
            "movement": self.movement(),
            "data_used": list(self.data_used),
            "fit_quality": dict(self.fit_quality),
            "n_observations": self.n_observations,
            "max_movement_allowed": self.max_movement_allowed,
            "identifiable": self.identifiable,
            "timestamp": self.timestamp,
            "warnings": list(self.warnings),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalibrationRecord:
        return cls(
            edge_id=str(d["edge_id"]),
            calibration_event_id=str(d.get("calibration_event_id") or ""),
            method=str(d.get("method") or ""),
            prior_range={k: float(v) for k, v in (d.get("prior_range") or {}).items()},
            calibrated_range={k: float(v) for k, v in (d.get("calibrated_range") or {}).items()},
            data_used=[str(s) for s in (d.get("data_used") or [])],
            fit_quality=dict(d.get("fit_quality") or {}),
            n_observations=int(d.get("n_observations", 0)),
            max_movement_allowed=(float(d["max_movement_allowed"])
                                  if d.get("max_movement_allowed") is not None else None),
            identifiable=bool(d.get("identifiable", True)),
            timestamp=str(d.get("timestamp") or ""),
            warnings=[str(w) for w in (d.get("warnings") or [])],
            notes=str(d.get("notes") or ""),
        )
