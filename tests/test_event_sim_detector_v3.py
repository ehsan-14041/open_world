"""
Tests for Detector v3 — the coverage-regime model and the data-role split.

The scientific claims defended here:

  * both earlier verdicts are immutable, and both earlier datasets are spent,
  * coverage is context: occupancy is never divided by it, regressed on it, or corrected by it,
  * a rise in observed vessels is not automatically a measurement artifact,
  * every component is causal,
  * the validity criteria stay meaningful when only a couple of windows exist — the specific
    defect that failed Detector v2,
  * `STOP_HAMPTON_ROADS` is reachable, so the project can conclude rather than iterate.
"""

from __future__ import annotations

import ast
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from event_sim.detect import detector_v2 as dv2
from event_sim.detect import detector_v3 as dv3
from event_sim.detect import sampling

REPO = Path(__file__).resolve().parent.parent
REPLAYS = REPO / "docs" / "replays"
V3_SRC = REPO / "event_sim" / "detect" / "detector_v3.py"

V1_DOC = REPLAYS / "HAMPTON_ROADS_DETECTABILITY.md"
V2_RESULTS = REPLAYS / "HAMPTON_ROADS_DETECTOR_V2_RESULTS.md"
V3_SPLIT = REPLAYS / "HAMPTON_ROADS_DETECTOR_V3_DATA_SPLIT.md"
V3_PROTOCOL = REPLAYS / "HAMPTON_ROADS_DETECTOR_V3_PROTOCOL.md"
V3_BLIND = REPLAYS / "HAMPTON_ROADS_DETECTOR_V3_BLIND_SAMPLE.md"
V3_RESULTS = REPLAYS / "HAMPTON_ROADS_DETECTOR_V3_RESULTS.md"
V3_WINDOWS = REPLAYS / "HAMPTON_ROADS_DETECTOR_V3_WINDOWS.md"


def _prose(path: Path) -> str:
    lines = [re.sub(r"^\s*>\s?", "", ln) for ln in path.read_text(encoding="utf-8").splitlines()]
    return " ".join(" ".join(lines).split())


def _dates(n: int, start: date = date(2024, 1, 1)) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


# ---------------------------------------------------------------------------------------
# 1-3. History is immutable; earlier datasets are spent
# ---------------------------------------------------------------------------------------

def test_v1_verdict_immutable():
    assert "HAMPTON_ROADS_LOW_POWER" in V1_DOC.read_text(encoding="utf-8")


def test_v2_verdict_immutable():
    assert "DETECTOR_V2_COVERAGE_CONFOUNDED" in V2_RESULTS.read_text(encoding="utf-8")


def test_v3_split_records_both_verdicts_without_changing_them():
    text = _prose(V3_SPLIT)
    assert "HAMPTON_ROADS_LOW_POWER" in text
    assert "DETECTOR_V2_COVERAGE_CONFOUNDED" in text
    assert "not changed" in text or "immutable" in text.lower()


def test_data_roles_are_declared():
    text = V3_SPLIT.read_text(encoding="utf-8")
    assert "measurement_protocol_development_set_v1" in text
    assert "detector_v2_blind_validation_spent" in text


def test_v2_lesson_is_recorded_and_is_not_the_wrong_lesson():
    text = _prose(V3_SPLIT)
    assert "measurement-regime model" in text
    # The two summaries explicitly ruled out must be named as ruled out.
    assert "is not" in text.lower() and "divided out" in text


# ---------------------------------------------------------------------------------------
# 4. Blind sample non-overlap
# ---------------------------------------------------------------------------------------

def test_v3_blind_is_disjoint_from_both_spent_datasets():
    assert sampling.v3_splits_are_disjoint()
    v3 = set(sampling.v3_blind_days())
    assert not (v3 & set(sampling.baseline_days()))
    assert not (v3 & set(sampling.blind_days()))


def test_v3_buffer_exceeds_the_lookback():
    gap = (
        date.fromisoformat(min(sampling.v3_blind_days()))
        - date.fromisoformat(max(sampling.blind_days()))
    ).days
    assert gap > dv3.LOOKBACK_DAYS, "a v3 lookback must not reach into the spent v2 sample"


def test_v3_blind_is_contiguous_and_deterministic():
    import inspect

    days = sampling.v3_blind_days()
    assert not inspect.signature(sampling.v3_blind_days).parameters
    assert days == sampling.v3_blind_days()
    for a, b in zip(days, days[1:]):
        assert date.fromisoformat(b) - date.fromisoformat(a) == timedelta(days=1)


# ---------------------------------------------------------------------------------------
# 5. H1 and the engine stay out of the detection path
# ---------------------------------------------------------------------------------------

_FORBIDDEN = (
    "event_sim.engine", "event_sim.sweep", "event_sim.freeze", "event_sim.h1_report",
    "event_sim.mechanism", "event_sim.historical", "event_sim.causal_scope",
    "event_sim.registry", "event_sim.world_builder", "event_sim.api",
)


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize(
    "path", sorted((REPO / "event_sim" / "detect").glob("*.py")), ids=lambda p: p.name
)
def test_detection_path_never_imports_h1_or_the_engine(path):
    names = _imports(path)
    for bad in _FORBIDDEN:
        assert not any(m == bad or m.startswith(bad + ".") for m in names)


def test_v3_contains_no_dates_or_event_names():
    text = V3_SRC.read_text(encoding="utf-8")
    assert not re.search(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", text)
    for token in ("hurricane", "strike", "closure", "yantian", "baltimore", "typhoon"):
        assert not re.search(rf"\b{token}\b", text.lower())


# ---------------------------------------------------------------------------------------
# 6-7. Coverage is context, never correction
# ---------------------------------------------------------------------------------------

_COVERAGE_TOKENS = ("coverage", "vessels_in_region", "vessel_residual", "density", "footprint")


def test_occupancy_is_never_divided_by_coverage():
    src = V3_SRC.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            seg = (ast.get_source_segment(src, node) or "").lower()
            if "occupancy" in seg:
                assert not any(t in seg for t in _COVERAGE_TOKENS), (
                    f"occupancy divided by a coverage quantity: {seg!r}"
                )


def test_occupancy_is_never_regression_corrected_using_coverage():
    """No fitted coverage effect may be estimated, let alone subtracted from occupancy."""
    src = V3_SRC.read_text(encoding="utf-8").lower()
    for banned in ("linear_regression", "polyfit", "lstsq", "ols", "curve_fit",
                   "linregress", "correlation("):
        assert banned not in src, f"regression machinery present: {banned}"


def test_occupancy_and_coverage_are_computed_from_separate_series():
    """The classifier must never see occupancy, and the detector never sees coverage."""
    import inspect

    assert "occupancy" not in inspect.signature(dv3.classify_series).parameters
    assert set(inspect.signature(dv3.classify_regime).parameters) == {
        "vessel_residual", "density_residual", "footprint_residual"
    }


# ---------------------------------------------------------------------------------------
# 8-10. Causality
# ---------------------------------------------------------------------------------------

def test_coverage_classification_is_causal_under_future_mutation():
    n = 60
    dates = _dates(n)
    v = [40.0] * n
    m = [300.0] * n
    s = [180.0] * n
    a = dv3.classify_series(dates, v, m, s)

    v2_, m2_, s2_ = list(v), list(m), list(s)
    for i in range(40, n):
        v2_[i], m2_[i], s2_[i] = 999.0, 9999.0, 9999.0
    b = dv3.classify_series(dates, v2_, m2_, s2_)

    for i in range(40):
        assert a[i].regime == b[i].regime, f"regime at day {i} changed when the future changed"
        assert a[i].vessel_residual == b[i].vessel_residual


def test_occupancy_residual_is_causal_under_future_mutation():
    n = 60
    dates = _dates(n)
    base = [8.0] * n
    mutated = list(base)
    mutated[40:] = [900.0] * (n - 40)
    a = dv3.occupancy_residuals(dates, base)
    b = dv3.occupancy_residuals(dates, mutated)
    for i in range(40):
        assert a[i].residual == b[i].residual


def test_trigger_state_is_causal_under_future_mutation():
    n = 80
    dates = _dates(n)
    occ = [8.0] * n
    for i in range(30, 40):
        occ[i] = 20.0
    early = dv3.detect_occupancy(dv3.occupancy_residuals(dates[:50], occ[:50]))
    later = [w for w in dv3.detect_occupancy(dv3.occupancy_residuals(dates, occ))
             if w.end <= dates[49]]
    assert [w.start for w in early] == [w.start for w in later]


def test_v3_uses_no_centred_windows():
    src = V3_SRC.read_text(encoding="utf-8")
    for banned in ("center=True", "centered", "center_window", "rolling(center"):
        assert banned not in src


# ---------------------------------------------------------------------------------------
# 11-14. The regime classifier's semantics
# ---------------------------------------------------------------------------------------

def test_more_vessels_with_steady_observation_character_is_traffic_not_measurement():
    """The distinction the whole module exists for."""
    assert dv3.classify_regime(5.0, 0.5, 0.5) == dv3.CoverageRegime.GRADUAL_SHIFT


def test_gradual_drift_is_not_quarantined_as_a_measurement_shift():
    regime = dv3.classify_regime(5.0, 0.5, 0.5)
    assert regime != dv3.CoverageRegime.ABRUPT_MEASUREMENT_SHIFT
    assert dv3.REGIME_TO_CANDIDATE[regime] == "candidate_with_context"


def test_density_jump_is_an_abrupt_measurement_shift():
    assert dv3.classify_regime(5.0, 6.0, 0.5) == dv3.CoverageRegime.ABRUPT_MEASUREMENT_SHIFT


def test_footprint_jump_is_an_abrupt_measurement_shift():
    assert dv3.classify_regime(0.0, 0.0, 6.0) == dv3.CoverageRegime.ABRUPT_MEASUREMENT_SHIFT


def test_observation_character_outranks_observation_volume():
    """A steady vessel count does not rescue a day whose reporting character jumped."""
    assert dv3.classify_regime(0.0, 9.0, 0.0) == dv3.CoverageRegime.ABRUPT_MEASUREMENT_SHIFT


def test_vessel_move_with_unsettled_character_is_uncertain_not_forced():
    assert dv3.classify_regime(5.0, 3.0, 0.5) == dv3.CoverageRegime.UNCERTAIN


def test_uncertain_regime_is_supported_and_reachable():
    assert dv3.CoverageRegime.UNCERTAIN in dv3.CoverageRegime.SEVERITY
    assert dv3.classify_regime(None, None, None) == dv3.CoverageRegime.UNCERTAIN
    assert dv3.REGIME_TO_CANDIDATE[dv3.CoverageRegime.UNCERTAIN] == "uncertain"


def test_quiet_day_is_stable():
    assert dv3.classify_regime(0.5, 0.5, 0.5) == dv3.CoverageRegime.STABLE


def test_abrupt_shock_quarantines_a_window():
    regimes = ["stable", "abrupt_measurement_shift", "abrupt_measurement_shift", "stable"]
    assert dv3.window_regime(regimes) == dv3.CoverageRegime.ABRUPT_MEASUREMENT_SHIFT
    assert dv3.REGIME_TO_CANDIDATE[dv3.window_regime(regimes)] == "measurement_confounded"


def test_a_single_shock_day_does_not_quarantine_a_window():
    regimes = ["stable", "stable", "stable", "abrupt_measurement_shift"]
    assert dv3.window_regime(regimes) == dv3.CoverageRegime.STABLE


def test_window_regime_uses_absolute_day_counts_not_a_share():
    """v2 failed on a share over 2 windows, whose support was {0, 0.5, 1.0}."""
    assert isinstance(dv3.WINDOW_REGIME_MIN_DAYS, int)
    long_window = ["stable"] * 20 + ["abrupt_measurement_shift"] * 2
    assert dv3.window_regime(long_window) == dv3.CoverageRegime.ABRUPT_MEASUREMENT_SHIFT


# ---------------------------------------------------------------------------------------
# 15-16. Validity criteria
# ---------------------------------------------------------------------------------------

def _rows_and_regimes(occ, regime_name="stable"):
    dates = _dates(len(occ))
    rows = dv3.occupancy_residuals(dates, occ)
    regimes = [
        dv3.RegimeDay(d, regime_name, 0.0, 0.0, 0.0) for d in dates
    ]
    return rows, regimes


def test_threshold_reachability_is_still_checked():
    occ = [8.0] * 60
    rows, regimes = _rows_and_regimes(occ)
    v = dv3.evaluate_validity(rows, regimes, trigger_days=0)
    assert v["checks"]["V1_threshold_reachable"] is False
    assert v["outcome"] == "DETECTOR_V3_TOO_INSENSITIVE"


def test_a_reachable_threshold_with_no_trigger_is_not_a_failure():
    occ = [8.0] * 60
    occ[40] = 40.0  # single spike: reachable, not persistent
    rows, regimes = _rows_and_regimes(occ)
    # Two regimes so V5 is satisfied.
    regimes[20] = dv3.RegimeDay(regimes[20].date, "gradual_shift", 0.0, 0.0, 0.0)
    v = dv3.evaluate_validity(rows, regimes, trigger_days=0)
    assert v["checks"]["V1_threshold_reachable"] is True
    assert v["outcome"] == "DETECTOR_V3_VALID"


def test_criteria_are_day_level_so_they_survive_a_single_trigger_window():
    """The n=2 failure mode: with one window a share-based gate is degenerate; these are not."""
    occ = [8.0] * 60
    for i in range(40, 46):
        occ[i] = 30.0
    rows, regimes = _rows_and_regimes(occ)
    regimes[20] = dv3.RegimeDay(regimes[20].date, "gradual_shift", 0.0, 0.0, 0.0)
    v = dv3.evaluate_validity(rows, regimes, trigger_days=6)
    assert v["outcome"] == "DETECTOR_V3_VALID"
    assert 0.0 < v["trigger_day_share"] < 1.0


def test_too_many_uncertain_days_fails():
    occ = [8.0] * 60
    occ[40] = 40.0
    rows, regimes = _rows_and_regimes(occ, regime_name="uncertain")
    regimes[20] = dv3.RegimeDay(regimes[20].date, "stable", 0.0, 0.0, 0.0)
    v = dv3.evaluate_validity(rows, regimes, trigger_days=0)
    assert v["outcome"] == "DETECTOR_V3_TOO_MANY_UNCERTAIN_DAYS"


def test_unstable_measurement_environment_fails():
    occ = [8.0] * 60
    occ[40] = 40.0
    rows, regimes = _rows_and_regimes(occ, regime_name="abrupt_measurement_shift")
    regimes[20] = dv3.RegimeDay(regimes[20].date, "stable", 0.0, 0.0, 0.0)
    v = dv3.evaluate_validity(rows, regimes, trigger_days=0)
    assert v["outcome"] == "DETECTOR_V3_MEASUREMENT_UNSTABLE"


def test_a_degenerate_single_regime_classifier_fails():
    occ = [8.0] * 60
    occ[40] = 40.0
    rows, regimes = _rows_and_regimes(occ)  # every day 'stable' -> only one regime
    v = dv3.evaluate_validity(rows, regimes, trigger_days=0)
    assert v["checks"]["V5_classifier_discriminates"] is False
    assert v["outcome"] == "DETECTOR_V3_MEASUREMENT_UNSTABLE"


def test_over_triggering_fails():
    occ = [8.0] * 60
    occ[40] = 40.0
    rows, regimes = _rows_and_regimes(occ)
    regimes[20] = dv3.RegimeDay(regimes[20].date, "gradual_shift", 0.0, 0.0, 0.0)
    v = dv3.evaluate_validity(rows, regimes, trigger_days=45)
    assert v["outcome"] == "DETECTOR_V3_TOO_SENSITIVE"


# ---------------------------------------------------------------------------------------
# 17. STOP_HAMPTON_ROADS is reachable and correctly scoped
# ---------------------------------------------------------------------------------------

def test_stop_hampton_roads_is_recommended_for_environmental_failures_only():
    assert set(dv3.STOP_HAMPTON_ROADS_OUTCOMES) == {
        "DETECTOR_V3_MEASUREMENT_UNSTABLE",
        "DETECTOR_V3_TOO_MANY_UNCERTAIN_DAYS",
    }


def test_implementation_failures_do_not_trigger_the_project_exit():
    occ = [8.0] * 60
    occ[40] = 40.0
    rows, regimes = _rows_and_regimes(occ)
    regimes[20] = dv3.RegimeDay(regimes[20].date, "gradual_shift", 0.0, 0.0, 0.0)
    v = dv3.evaluate_validity(rows, regimes, trigger_days=45)
    assert v["outcome"] == "DETECTOR_V3_TOO_SENSITIVE"
    assert v["recommend_stop_hampton_roads"] is False


def test_environmental_failure_sets_the_project_exit_flag():
    occ = [8.0] * 60
    occ[40] = 40.0
    rows, regimes = _rows_and_regimes(occ, regime_name="abrupt_measurement_shift")
    regimes[20] = dv3.RegimeDay(regimes[20].date, "stable", 0.0, 0.0, 0.0)
    assert dv3.evaluate_validity(rows, regimes, 0)["recommend_stop_hampton_roads"] is True


def test_protocol_declares_the_project_exit_condition():
    assert "STOP_HAMPTON_ROADS" in V3_PROTOCOL.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------
# 18. Occupancy parameters genuinely unchanged from v2
# ---------------------------------------------------------------------------------------

def test_occupancy_parameters_are_imported_from_v2_not_restated():
    assert dv3.LOOKBACK_DAYS is dv2.LOOKBACK_DAYS
    assert dv3.RESIDUAL_THRESHOLD is dv2.RESIDUAL_THRESHOLD
    assert dv3.PERSISTENCE_DAYS is dv2.PERSISTENCE_DAYS
    assert dv3.detect_occupancy is dv2.detect


def test_frozen_v3_coverage_parameters():
    assert (dv3.V_SHIFT, dv3.M_ABRUPT, dv3.S_ABRUPT, dv3.M_STABLE, dv3.S_STABLE) == (
        3.5, 4.0, 4.5, 2.0, 2.5
    )
    assert dv3.WINDOW_REGIME_MIN_DAYS == 2


def test_protocol_and_blind_documents_exist_and_agree_with_the_code():
    assert V3_PROTOCOL.exists() and V3_BLIND.exists() and V3_SPLIT.exists()
    protocol = V3_PROTOCOL.read_text(encoding="utf-8")
    for token in ("V_SHIFT", "M_ABRUPT", "S_ABRUPT", "3.5", "4.0", "4.5"):
        assert token in protocol
    blind = V3_BLIND.read_text(encoding="utf-8")
    assert sampling.V3_BLIND_FIRST_DAY in blind
    assert max(sampling.v3_blind_days()) in blind


# ---------------------------------------------------------------------------------------
# 19-21. Staging, drivers, stopping rule
# ---------------------------------------------------------------------------------------

def test_windows_are_frozen_before_results_are_interpreted():
    if V3_WINDOWS.exists():
        assert V3_RESULTS.exists(), "windows recorded without the run that produced them"


def test_no_event3_v5_freeze_without_windows():
    if (REPLAYS / "EVENT3_FREEZE_V5.md").exists():
        assert V3_WINDOWS.exists()


def test_driver_evidence_must_be_independent_of_ais():
    if not V3_WINDOWS.exists():
        pytest.skip("no v3 windows in this checkout")
    text = _prose(V3_WINDOWS)
    if "classification" in text.lower():
        assert "non-AIS" in text or "NCEI" in text or "NOAA" in text or "USCG" in text


def test_first_qualified_stopping_rule_is_declared():
    text = _prose(V3_PROTOCOL)
    assert "first candidate that passes" in text.lower() or "first qualified" in text.lower()


def test_protocol_forbids_h1_from_candidate_ordering():
    text = _prose(V3_PROTOCOL).lower()
    assert "expected h1 performance is not a criterion" in text


# ---------------------------------------------------------------------------------------
# 22-24. Nothing upstream moved
# ---------------------------------------------------------------------------------------

def test_event3_eligibility_contract_unchanged():
    from event_sim.historical import dataset_contract as dc

    assert dc.H1_SENSITIVE_METRICS == (
        "vessel_queue", "waiting_vessels", "average_waiting_time", "anchorage_wait",
        "port_dwell_time", "container_dwell_time", "local_shipping_delay",
    )
    assert dc.DRIVER_METRICS == (
        "throughput", "arrivals", "departures", "port_capacity", "berth_availability",
    )
    assert dc.FREQUENCY_RANK == {"daily": 3, "weekly": 2, "monthly": 1, "irregular": 0}


def test_frozen_model_and_evaluation_hashes_unchanged():
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
    for path in (REPO / "event_sim" / "detect").glob("*.py"):
        for m in _imports(path):
            assert m.split(".")[0] not in {"core", "config", "ui"}


def test_results_confirm_h1_not_run():
    if not V3_RESULTS.exists():
        pytest.skip("v3 not yet run in this checkout")
    assert "H1 was not run" in _prose(V3_RESULTS)
