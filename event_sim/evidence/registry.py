"""
Evidence registry: file-backed store of sources and proxy mappings, plus the rules that
decide whether an edge is allowed to claim its evidence status.

The rules (item 31 of the task brief) are the teeth of the whole evidence layer:

    literature_backed        requires >= 1 citable EvidenceSource
    empirical                requires a dataset source AND FittingProvenance
    historically_calibrated  requires a CalibrationRecord referencing a real event
    observed                 requires a source that measured the value directly

An edge that fails its rule does not get silently downgraded — validation *fails*, so the
mislabelling has to be fixed by a human rather than absorbed by the system.

Storage is JSON files under event_sim/evidence_data/. No database, no server.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from event_sim.evidence.schema import (
    MAPPING_TYPES,
    REQUIRED_SOURCE_FIELDS,
    SOURCE_TYPES,
    CalibrationRecord,
    EvidenceSource,
    FittingProvenance,
    ProxyMapping,
)
from event_sim.schemas import CausalEdgeEvidence

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EVIDENCE_DATA_DIR = _PROJECT_ROOT / "event_sim" / "evidence_data"
SOURCES_PATH = EVIDENCE_DATA_DIR / "sources.json"
MAPPINGS_PATH = EVIDENCE_DATA_DIR / "mappings.json"
CALIBRATION_PATH = EVIDENCE_DATA_DIR / "calibrations.json"

#: Which source types can support which evidence status.
STATUS_SOURCE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "observed": ("dataset", "official_statistics", "industry_index", "carrier_advisory",
                 "press_release", "news_report", "technical_report"),
    "empirical": ("dataset", "official_statistics", "industry_index"),
    "literature_backed": ("academic_study", "technical_report", "industry_index",
                          "official_statistics", "press_release"),
}


class EvidenceRegistryError(ValueError):
    """Raised on a broken evidence reference or an unsupported status claim."""


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------


def _read_json(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get(key) or [])
    return list(data or [])


@lru_cache(maxsize=1)
def _sources() -> dict[str, EvidenceSource]:
    out: dict[str, EvidenceSource] = {}
    for record in _read_json(SOURCES_PATH, "sources"):
        for required in REQUIRED_SOURCE_FIELDS:
            if not record.get(required):
                raise EvidenceRegistryError(
                    f"Evidence source missing required field {required!r}: {record}"
                )
        source = EvidenceSource.from_dict(record)
        if source.type not in SOURCE_TYPES:
            raise EvidenceRegistryError(
                f"Source {source.id!r}: unknown type {source.type!r}; expected one of {SOURCE_TYPES}"
            )
        if source.id in out:
            raise EvidenceRegistryError(f"Duplicate evidence source id {source.id!r}")
        out[source.id] = source
    return out


@lru_cache(maxsize=1)
def _mappings() -> dict[str, ProxyMapping]:
    out: dict[str, ProxyMapping] = {}
    for record in _read_json(MAPPINGS_PATH, "mappings"):
        mapping = ProxyMapping.from_dict(record)
        if mapping.mapping_type not in MAPPING_TYPES:
            raise EvidenceRegistryError(
                f"Mapping {mapping.id!r}: unknown mapping_type {mapping.mapping_type!r}"
            )
        if mapping.mapping_type == "proxy" and not mapping.limitations:
            raise EvidenceRegistryError(
                f"Mapping {mapping.id!r} is a proxy but states no limitations. "
                f"If the cost of the proxy is unknown, the proxy is not understood well "
                f"enough to use."
            )
        for source_id in mapping.source_ids:
            if source_id not in _sources():
                raise EvidenceRegistryError(
                    f"Mapping {mapping.id!r} references unknown source {source_id!r}"
                )
        if mapping.id in out:
            raise EvidenceRegistryError(f"Duplicate mapping id {mapping.id!r}")
        out[mapping.id] = mapping
    return out


@lru_cache(maxsize=1)
def _calibrations() -> dict[str, list[CalibrationRecord]]:
    out: dict[str, list[CalibrationRecord]] = {}
    for record in _read_json(CALIBRATION_PATH, "calibrations"):
        cal = CalibrationRecord.from_dict(record)
        out.setdefault(cal.edge_id, []).append(cal)
    return out


def clear_cache() -> None:
    """Drop cached registry state (tests, and after writing new calibration records)."""
    _sources.cache_clear()
    _mappings.cache_clear()
    _calibrations.cache_clear()


# --------------------------------------------------------------------------------------
# Lookup
# --------------------------------------------------------------------------------------


def get_source(source_id: str) -> EvidenceSource:
    sources = _sources()
    if source_id not in sources:
        raise EvidenceRegistryError(
            f"Unknown evidence source {source_id!r}. Known: {sorted(sources)}"
        )
    return sources[source_id]


def all_sources() -> list[EvidenceSource]:
    return sorted(_sources().values(), key=lambda s: s.id)


def get_mapping(mapping_id: str) -> ProxyMapping:
    mappings = _mappings()
    if mapping_id not in mappings:
        raise EvidenceRegistryError(
            f"Unknown proxy mapping {mapping_id!r}. Known: {sorted(mappings)}"
        )
    return mappings[mapping_id]


def all_mappings() -> list[ProxyMapping]:
    return sorted(_mappings().values(), key=lambda m: m.id)


def mappings_for_variable(variable: str) -> list[ProxyMapping]:
    return [m for m in all_mappings() if m.simulation_variable == variable]


def calibrations_for_edge(edge_id: str) -> list[CalibrationRecord]:
    return list(_calibrations().get(edge_id, []))


def resolve_source_ids(reference_strings: Iterable[str]) -> list[EvidenceSource]:
    """
    Resolve `source:<id>` references (as stored in an edge's evidence records) to sources.
    A reference that does not resolve is an error, never a silently ignored string.
    """
    out: list[EvidenceSource] = []
    for ref in reference_strings:
        if not ref:
            continue
        source_id = ref.split("source:", 1)[1] if ref.startswith("source:") else ref
        out.append(get_source(source_id))
    return out


# --------------------------------------------------------------------------------------
# Status / provenance rules
# --------------------------------------------------------------------------------------


def validate_edge_provenance(
    edge: CausalEdgeEvidence,
    *,
    fitting: FittingProvenance | None = None,
) -> list[str]:
    """
    Check that an edge's evidence *status* is actually supported by its provenance.

    Returns a list of errors (empty = the claim is supported). This is the function that
    stops an expert assumption from being relabelled as literature-backed.
    """
    errors: list[str] = []
    status = edge.status

    if status in ("expert_assumption", "user_assumption", "ai_hypothesis"):
        return errors  # honest self-declaration; nothing to prove

    # Every non-assumption status needs resolvable, citable sources.
    references = [e.reference for e in edge.evidence if e.reference]
    if not references:
        errors.append(
            f"{edge.id}: status {status!r} requires at least one evidence record with a "
            f"resolvable source reference"
        )
        return errors

    try:
        sources = resolve_source_ids(references)
    except EvidenceRegistryError as exc:
        errors.append(f"{edge.id}: {exc}")
        return errors

    for source in sources:
        if not source.is_citable():
            errors.append(
                f"{edge.id}: source {source.id!r} has no url, doi or publisher — not checkable"
            )

    allowed_types = STATUS_SOURCE_REQUIREMENTS.get(status)
    if allowed_types and not any(s.type in allowed_types for s in sources):
        errors.append(
            f"{edge.id}: status {status!r} needs a source of type {allowed_types}, "
            f"got {[s.type for s in sources]}"
        )

    if status == "empirical":
        if fitting is None or not fitting.method:
            errors.append(
                f"{edge.id}: status 'empirical' requires FittingProvenance (method, data, "
                f"fit quality). A relationship is empirical only if it was actually fitted."
            )
        elif fitting.n_observations <= 0:
            errors.append(f"{edge.id}: empirical fit records zero observations")

    if status == "historically_calibrated":
        records = calibrations_for_edge(edge.id)
        if not records:
            errors.append(
                f"{edge.id}: status 'historically_calibrated' requires a calibration record "
                f"referencing a replayed historical event"
            )
        else:
            for record in records:
                if not record.calibration_event_id:
                    errors.append(f"{edge.id}: calibration record has no event id")
                if not record.prior_range:
                    errors.append(
                        f"{edge.id}: calibration record does not preserve the prior range"
                    )

    return errors


def validate_slice_provenance(edges: Iterable[CausalEdgeEvidence]) -> list[str]:
    """Validate every edge in a slice. Used by the replay CLI and the test suite."""
    errors: list[str] = []
    for edge in edges:
        errors.extend(validate_edge_provenance(edge))
    return errors


def source_summary() -> list[dict[str, Any]]:
    """Inspectable listing of the registry, for reports and the API."""
    return [
        {
            "id": s.id,
            "type": s.type,
            "title": s.title,
            "publisher": s.publisher,
            "url": s.url,
            "published_at": s.published_at or (str(s.publication_year) if s.publication_year else ""),
            "accessed_at": s.accessed_at,
            "redistributable": s.redistributable,
            "citable": s.is_citable(),
        }
        for s in all_sources()
    ]
