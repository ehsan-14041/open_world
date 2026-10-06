"""
Evidence layer for the Event Simulator.

Package layout (the original single-module API is preserved verbatim, so existing imports
`from event_sim.evidence import validate_module, evidence_coverage, missing_evidence`
keep working):

    validation.py   structural + epistemic validation of a world module; unweighted coverage
    schema.py       EvidenceSource, ProxyMapping, FittingProvenance, CalibrationRecord
    registry.py     file-backed source/mapping store + status-vs-provenance rules
    coverage.py     evidence strength, influence weighting, gap report, data requirements
    transforms.py   named, testable unit conversions (raw values are never overwritten)

Data lives in event_sim/evidence_data/ as JSON. No database, no server.
"""

from event_sim.evidence.coverage import (
    STRENGTH_RULE,
    WEIGHTING_METHOD,
    data_requirements,
    evidence_gap_report,
    evidence_strength,
    merge_influence,
    structural_influence,
    weighted_coverage,
)
from event_sim.evidence.measurement_risk import (
    MEASUREMENT_RISKS,
    RISK_BY_ID,
    RISK_IDS,
    MeasurementRisk,
    MeasurementRiskError,
    assess_mapping,
    registry_summary,
    validate_risk_ids,
)
from event_sim.evidence.registry import (
    EvidenceRegistryError,
    all_mappings,
    all_sources,
    calibrations_for_edge,
    clear_cache,
    get_mapping,
    get_source,
    mappings_for_variable,
    resolve_source_ids,
    source_summary,
    validate_edge_provenance,
    validate_slice_provenance,
)
from event_sim.evidence.schema import (
    MAPPING_TYPES,
    SOURCE_TYPES,
    CalibrationRecord,
    EvidenceSource,
    FittingProvenance,
    ProxyMapping,
)
from event_sim.evidence.validation import (
    COVERAGE_GROUP_LABELS,
    WEAK_EVIDENCE_THRESHOLD,
    EvidenceValidationError,
    evidence_coverage,
    missing_evidence,
    validate_edge,
    validate_module,
)

__all__ = [
    "COVERAGE_GROUP_LABELS",
    "MEASUREMENT_RISKS",
    "RISK_BY_ID",
    "RISK_IDS",
    "MeasurementRisk",
    "MeasurementRiskError",
    "assess_mapping",
    "registry_summary",
    "validate_risk_ids",
    "MAPPING_TYPES",
    "SOURCE_TYPES",
    "STRENGTH_RULE",
    "WEAK_EVIDENCE_THRESHOLD",
    "WEIGHTING_METHOD",
    "CalibrationRecord",
    "EvidenceRegistryError",
    "EvidenceSource",
    "EvidenceValidationError",
    "FittingProvenance",
    "ProxyMapping",
    "all_mappings",
    "all_sources",
    "calibrations_for_edge",
    "clear_cache",
    "data_requirements",
    "evidence_coverage",
    "evidence_gap_report",
    "evidence_strength",
    "get_mapping",
    "get_source",
    "mappings_for_variable",
    "merge_influence",
    "missing_evidence",
    "resolve_source_ids",
    "source_summary",
    "structural_influence",
    "validate_edge",
    "validate_edge_provenance",
    "validate_module",
    "validate_slice_provenance",
    "weighted_coverage",
]
