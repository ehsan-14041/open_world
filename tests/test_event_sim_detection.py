"""
Tests for the blind detection path.

The scientific claims this file defends are not about arithmetic. They are:

  * the measurement definition is fixed and matches its freeze document,
  * the detector cannot see H1, the engine, or any historical event date,
  * thresholds were declared before the search and cannot drift,
  * a low-power outcome is a real, reachable stopping state rather than a formality.
"""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from event_sim.detect import anomaly, baseline, sampling, series
from event_sim.ingest import ais
from event_sim.ingest import cfr_anchorage as cfr

REPO = Path(__file__).resolve().parent.parent
FREEZE_DOC = REPO / "docs" / "replays" / "HAMPTON_ROADS_MEASUREMENT_FREEZE.md"
GEOMETRY = REPO / "data" / "external" / "ais" / "geometry" / "hampton_roads_110.168_2022-01-01.json"
DETECT_DIR = REPO / "event_sim" / "detect"


# ---------------------------------------------------------------------------------------
# 1. Measurement definition immutable, and matching its freeze document
# ---------------------------------------------------------------------------------------

def test_measurement_constants_match_the_freeze_document():
    doc = FREEZE_DOC.read_text(encoding="utf-8")
    assert str(ais.SOG_STATIONARY_KTS) in doc
    assert "70–89" in doc or "70-89" in doc


def test_derived_bbox_contains_every_commercial_anchorage():
    """The regression that motivated deriving the box: a literal one silently dropped
    anchorage R entirely and clipped anchorage I."""
    region = ais.REGIONS["hampton_roads"]
    la0, la1, lo0, lo1 = ais.region_bbox(region.name)
    for p in ais.commercial_polygons(region):
        b = p.bbox()
        assert b[0] >= la0 and b[1] <= la1, f"anchorage {p.label} clipped in latitude"
        assert b[2] >= lo0 and b[3] <= lo1, f"anchorage {p.label} clipped in longitude"


def test_region_carries_no_hand_set_bounding_box():
    assert "bbox" not in ais.Region.__dataclass_fields__


def test_derived_bbox_matches_the_freeze_document():
    doc = FREEZE_DOC.read_text(encoding="utf-8").replace("−", "-")
    la0, la1, lo0, lo1 = ais.region_bbox("hampton_roads")
    for value in (la0, la1, lo0, lo1):
        assert f"{value:.4f}" in doc, f"derived bbox value {value:.4f} absent from freeze doc"


def test_geometry_artifact_hash_matches_the_freeze_document():
    if not GEOMETRY.exists():
        pytest.skip("geometry not frozen in this checkout")
    digest = hashlib.sha256(GEOMETRY.read_bytes()).hexdigest()
    assert digest in FREEZE_DOC.read_text(encoding="utf-8"), (
        "geometry changed without the freeze document being reissued"
    )


def test_cfr_version_is_pinned_not_latest():
    region = ais.REGIONS["hampton_roads"]
    assert "110.168" in region.geometry_file
    assert "2022-01-01" in region.geometry_file
    rec = json.loads(GEOMETRY.read_text(encoding="utf-8")) if GEOMETRY.exists() else None
    if rec:
        assert rec["effective_date"] == "2022-01-01"
        assert "/2022-01-01/" in rec["source_url"]


# ---------------------------------------------------------------------------------------
# 2. Naval and explosives anchorages excluded
# ---------------------------------------------------------------------------------------

def test_naval_and_explosives_anchorages_are_excluded_from_the_measurement():
    if not GEOMETRY.exists():
        pytest.skip("geometry not frozen in this checkout")
    used = ais.commercial_polygons(ais.REGIONS["hampton_roads"])
    labels = {p.label for p in used}
    assert labels == {"F", "G", "H", "I", "J", "K", "M", "N", "Q", "R"}
    assert not any("naval" in p.designation.lower() for p in used)
    assert not any("explosive" in p.designation.lower() for p in used)


def test_exclusion_is_driven_by_the_cfr_designation_not_a_hand_list():
    fake = cfr.AnchoragePolygon("Z", ((0, 0), (0, 1), (1, 1)), "Naval Anchorage")
    assert not fake.commercial


# ---------------------------------------------------------------------------------------
# 3. Pre-2020-07 geometry rejected
# ---------------------------------------------------------------------------------------

def test_definition_change_boundary_is_recorded():
    assert ais.DEFINITION_CHANGE_AFTER < ais.DEFINITION_CHANGE_BEFORE


def test_no_sampled_day_precedes_the_geometry_validity_era():
    # 110.168 changed between 2020-04-01 and 2020-07-01; everything sampled must follow it.
    assert min(sampling.baseline_days()) >= "2020-07-01"


def test_sampling_starts_in_the_first_fully_valid_quarter():
    assert sampling.FIRST_QUARTER == (2020, 3)


# ---------------------------------------------------------------------------------------
# 4. Sampling windows deterministic
# ---------------------------------------------------------------------------------------

def test_sampling_is_deterministic_across_calls():
    assert sampling.baseline_windows() == sampling.baseline_windows()
    assert sampling.baseline_days() == sampling.baseline_days()


def test_sampling_takes_no_arguments_so_it_cannot_be_nudged():
    import inspect

    assert not inspect.signature(sampling.baseline_windows).parameters
    assert not inspect.signature(sampling.baseline_days).parameters


def test_sampling_matches_the_frozen_rule_exactly():
    got = sampling.baseline_windows()
    assert len(got) == 8, "eight quarters == two years"
    assert got[0] == ("2020-Q3", "2020-08-15", "2020-08-21")
    assert got[-1] == ("2022-Q2", "2022-05-15", "2022-05-21")
    for _label, first, _last in got:
        assert date.fromisoformat(first).day == sampling.WINDOW_START_DAY


def test_sampled_windows_appear_verbatim_in_the_freeze_document():
    doc = FREEZE_DOC.read_text(encoding="utf-8")
    for label, first, last in sampling.baseline_windows():
        assert first in doc and last in doc, f"{label} missing from freeze doc"


def test_development_days_are_excluded_from_baseline():
    days = set(sampling.baseline_days())
    for d in sampling.DEVELOPMENT_DAYS:
        assert d not in days


# ---------------------------------------------------------------------------------------
# 5. Baseline calculation deterministic
# ---------------------------------------------------------------------------------------

def test_describe_is_deterministic_and_order_independent():
    a = baseline.describe([3, 1, 4, 1, 5, 9, 2, 6])
    b = baseline.describe([9, 6, 5, 4, 3, 2, 1, 1])
    assert a == b


def test_percentiles_stay_on_observable_integer_levels():
    d = baseline.describe([0, 1, 2, 3, 4])
    for q in (d.p10, d.p25, d.p75, d.p90):
        assert q == int(q), "counts must not be interpolated into fractional vessels"


def test_empty_series_does_not_crash_or_invent_values():
    d = baseline.describe([])
    assert d.n == 0 and d.mean != d.mean  # NaN


def test_dispersion_index_is_none_when_undefined():
    assert baseline.dispersion_index([]) is None
    assert baseline.dispersion_index([0, 0, 0]) is None


def test_variance_decomposition_separates_trend_from_noise():
    """A pooled MAD threshold assumes days are exchangeable across windows. This diagnostic
    is what shows they are not — the Hampton Roads baseline turned out 94% trend."""
    windows = ["A"] * 4 + ["B"] * 4
    values = [1, 2, 1, 2, 21, 22, 21, 22]  # tiny noise, huge level shift
    d = baseline.variance_decomposition(windows, values)
    assert d["between_window_share"] > 0.95
    assert d["window_mean_range"] == 20.0
    assert d["within_window_mad"] < 1.0


def test_variance_decomposition_needs_more_than_one_window():
    assert baseline.variance_decomposition(["A", "A"], [1, 2]) == {}


def test_variance_decomposition_is_flat_for_a_stationary_series():
    windows = ["A"] * 4 + ["B"] * 4
    d = baseline.variance_decomposition(windows, [5, 6, 5, 6, 5, 6, 5, 6])
    assert d["between_window_share"] == 0.0
    assert d["window_mean_range"] == 0.0


def test_low_power_outcome_is_recorded_in_the_detectability_document():
    doc = REPO / "docs" / "replays" / "HAMPTON_ROADS_DETECTABILITY.md"
    if not doc.exists():
        pytest.skip("detectability not yet run in this checkout")
    text = doc.read_text(encoding="utf-8")
    assert "HAMPTON_ROADS_LOW_POWER" in text
    assert "H1 was not run" in text or "H1 was not executed" in text


def test_frozen_thresholds_were_not_edited_after_the_low_power_finding():
    """The detectability analysis found a trend that a trend-aware rule would handle. That
    rule must be a new pre-registration, not an edit to these constants."""
    assert (anomaly.K_LEVEL, anomaly.MAD_FLOOR, anomaly.PERSISTENCE_DAYS, anomaly.K_DWELL) == (
        4.0, 1.0, 5, 2.0
    )


def test_autocorrelation_detects_perfect_persistence():
    assert baseline.autocorrelation([1, 1, 1, 1, 2, 2, 2, 2], 1) > 0.5


# ---------------------------------------------------------------------------------------
# 6. Anomaly thresholds frozen before the event search
# ---------------------------------------------------------------------------------------

def test_threshold_constants_have_the_declared_values():
    assert anomaly.K_LEVEL == 4.0
    assert anomaly.MAD_FLOOR == 1.0
    assert anomaly.PERSISTENCE_DAYS == 5
    assert anomaly.K_DWELL == 2.0


def test_thresholds_are_a_pure_function_of_the_baseline():
    assert anomaly.thresholds_from(3.0, 1.0) == anomaly.thresholds_from(3.0, 1.0)


def test_mad_floor_prevents_a_degenerate_zero_variance_trigger():
    """With MAD == 0 an unfloored rule would fire on any vessel above the median."""
    th = anomaly.thresholds_from(baseline_median=3.0, baseline_mad=0.0)
    assert th.level == 3.0 + anomaly.K_LEVEL * anomaly.MAD_FLOOR


def test_persistence_requirement_rejects_a_transient_spike():
    th = anomaly.thresholds_from(2.0, 1.0)  # level == 6
    occ = [2, 2, 2, 99, 99, 2, 2, 2]  # huge but only two days
    dates = [f"2021-01-{i + 1:02d}" for i in range(len(occ))]
    assert anomaly.detect(dates, occ, th) == []


def test_a_sustained_elevation_is_detected_with_its_peak():
    th = anomaly.thresholds_from(2.0, 1.0)  # level == 6
    occ = [2, 2, 7, 8, 12, 9, 7, 2, 2]
    dates = [f"2021-03-{i + 1:02d}" for i in range(len(occ))]
    found = anomaly.detect(dates, occ, th)
    assert len(found) == 1
    w = found[0]
    assert (w.start, w.peak_date, w.end) == ("2021-03-03", "2021-03-05", "2021-03-07")
    assert w.duration_days == 5
    assert w.peak_occupancy == 12


def test_detect_rejects_mismatched_input_lengths():
    with pytest.raises(ValueError):
        anomaly.detect(["2021-01-01"], [1, 2], anomaly.thresholds_from(1.0, 1.0))


# ---------------------------------------------------------------------------------------
# 7. Low-power outcome can actually stop the workflow
# ---------------------------------------------------------------------------------------

def test_unused_anchorage_yields_low_power():
    v = anomaly.power_verdict([0, 0, 1, 0, 0, 1], p90=1.0, median=0.0, mad=0.0,
                              completed_spells=50, missing_rate=0.0)
    assert not v.passed
    assert any("essentially unused" in r for r in v.reasons)


def test_baseline_that_already_fires_yields_low_power():
    # Heavy right tail: level == 0 + 4*1 == 4, and 30% of days already reach it.
    occ = [0] * 7 + [10] * 3
    v = anomaly.power_verdict(occ, p90=10.0, median=0.0, mad=0.0,
                              completed_spells=50, missing_rate=0.0)
    assert not v.passed
    assert any("cannot separate" in r for r in v.reasons)


def test_missingness_yields_low_power():
    v = anomaly.power_verdict([3, 4, 5, 4], p90=5.0, median=4.0, mad=1.0,
                              completed_spells=50, missing_rate=0.9)
    assert not v.passed
    assert any("missingness" in r for r in v.reasons)


def test_censored_dwell_yields_low_power():
    v = anomaly.power_verdict([3, 4, 5, 4], p90=5.0, median=4.0, mad=1.0,
                              completed_spells=2, missing_rate=0.0)
    assert not v.passed
    assert any("dwell unmeasurable" in r for r in v.reasons)


def test_a_healthy_baseline_passes():
    occ = [3, 4, 2, 5, 3, 4, 3, 2, 4, 3]
    v = anomaly.power_verdict(occ, p90=5.0, median=3.0, mad=1.0,
                              completed_spells=40, missing_rate=0.0)
    assert v.passed and v.reasons == ()


# ---------------------------------------------------------------------------------------
# 8. The detector cannot see H1, the engine, or historical dates
# ---------------------------------------------------------------------------------------

_FORBIDDEN_IMPORTS = (
    "event_sim.engine", "event_sim.sweep", "event_sim.freeze", "event_sim.h1_report",
    "event_sim.mechanism", "event_sim.historical", "event_sim.causal_scope",
    "event_sim.registry", "event_sim.world_builder", "event_sim.api",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module_path", sorted(DETECT_DIR.glob("*.py")), ids=lambda p: p.name)
def test_detection_path_does_not_import_h1_or_the_engine(module_path):
    imported = _imported_modules(module_path)
    for bad in _FORBIDDEN_IMPORTS:
        assert not any(m == bad or m.startswith(bad + ".") for m in imported), (
            f"{module_path.name} imports {bad}; detection must stay blind"
        )


@pytest.mark.parametrize("module_path", sorted(DETECT_DIR.glob("*.py")), ids=lambda p: p.name)
def test_no_historical_event_dates_are_hardcoded_in_the_detector(module_path):
    text = module_path.read_text(encoding="utf-8").lower()
    for token in ("yantian", "baltimore", "dali", "key bridge", "ever given", "suez"):
        assert token not in text, f"{module_path.name} names a known event: {token}"


def test_detector_signature_accepts_only_series_data():
    import inspect

    params = set(inspect.signature(anomaly.detect).parameters)
    assert params == {"dates", "occupancy", "thresholds"}


# ---------------------------------------------------------------------------------------
# 9. No queue terminology anywhere in the detection path
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("module_path", sorted(DETECT_DIR.glob("*.py")), ids=lambda p: p.name)
def test_detection_modules_never_name_the_metric_a_queue(module_path):
    text = module_path.read_text(encoding="utf-8")
    for bad in ("vessel_queue", "queue_length", "ships_waiting", "vessels_waiting"):
        assert bad not in text, f"{module_path.name} uses forbidden term {bad}"


def test_queue_guard_is_still_active():
    with pytest.raises(ais.MeasurementError):
        ais.assert_not_queue_named("vessel_queue")


def test_series_records_expose_occupancy_not_queue():
    fields = series.DayRecord.__dataclass_fields__
    assert "anchorage_occupancy" in fields
    assert not any("queue" in f for f in fields)


# ---------------------------------------------------------------------------------------
# 10. Spell censoring — the rule that keeps dwell honest
# ---------------------------------------------------------------------------------------

def test_spell_touching_a_window_edge_is_censored():
    s = series.Spell("1", "2021-Q1", "2021-02-15", "2021-02-17", 48.0, censored=True)
    assert s.censored
    result = series.SeriesResult(days=[], spells=[s])
    assert result.completed_spells == []


def test_completed_spells_are_reported_separately_from_censored_ones():
    a = series.Spell("1", "2021-Q1", "2021-02-16", "2021-02-17", 24.0, censored=False)
    b = series.Spell("2", "2021-Q1", "2021-02-15", "2021-02-21", 144.0, censored=True)
    result = series.SeriesResult(days=[], spells=[a, b])
    assert result.completed_spells == [a]


# ---------------------------------------------------------------------------------------
# 11. Ops product and frozen model hashes unaffected
# ---------------------------------------------------------------------------------------

def test_frozen_model_and_evaluation_hashes_are_unchanged():
    from event_sim.freeze import snapshot

    snap = snapshot()
    assert snap["modules"]["port_disruption"] == (
        "d4670fb108c2e9a3c45d33455a652578e7a72bfce69f88ed44c6b355ead13f5b"
    )
    assert snap["modules"]["port_disruption_h1_queue_experimental"] == (
        "324a8bf1d67d56ad082b9c7540f7d155466af50ad71359c1b4836ef79f8f3889"
    )
    assert snap["evaluation_code"] == (
        "880d2d0ef0cc0e3d32ea6f7b1464248a825225cdb1f2445cd372ce2f9239f992"
    )


def test_detection_package_does_not_touch_the_operations_product():
    for path in DETECT_DIR.glob("*.py"):
        imported = _imported_modules(path)
        assert not any(m.split(".")[0] in {"core", "config", "ui"} for m in imported)
