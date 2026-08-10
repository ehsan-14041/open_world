"""
Tests for Detector v2 and the development/validation split.

The central rule these defend: Detector v2 was designed on the old 56 days and must be judged
on new ones. Most of what follows exists to make that claim mechanically checkable rather
than a promise in prose — the split is disjoint, the detector is causal, the parameters are
frozen, and the previous failure is preserved rather than relabelled.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest

from event_sim.detect import detector_v2 as dv2
from event_sim.detect import sampling

REPO = Path(__file__).resolve().parent.parent
REPLAYS = REPO / "docs" / "replays"
SPLIT_DOC = REPLAYS / "HAMPTON_ROADS_DETECTOR_V2_DATA_SPLIT.md"
PROTOCOL_DOC = REPLAYS / "HAMPTON_ROADS_DETECTOR_V2_PROTOCOL.md"
BLIND_DOC = REPLAYS / "HAMPTON_ROADS_DETECTOR_V2_BLIND_SAMPLE.md"
V1_DOC = REPLAYS / "HAMPTON_ROADS_DETECTABILITY.md"
WINDOWS_DOC = REPLAYS / "HAMPTON_ROADS_DETECTOR_V2_WINDOWS.md"
RESULTS_DOC = REPLAYS / "HAMPTON_ROADS_DETECTOR_V2_RESULTS.md"


# ---------------------------------------------------------------------------------------
# 1. The previous failure is preserved, not rewritten
# ---------------------------------------------------------------------------------------

def test_v1_low_power_verdict_is_preserved():
    text = V1_DOC.read_text(encoding="utf-8")
    assert "HAMPTON_ROADS_LOW_POWER" in text
    assert "STOP" in text


def test_v1_is_not_relabelled_as_a_success():
    text = V1_DOC.read_text(encoding="utf-8").lower()
    for claim in ("detectable_event_found", "detector_v2_valid"):
        assert claim not in text


def test_split_document_records_the_v1_failure_reason():
    text = SPLIT_DOC.read_text(encoding="utf-8")
    assert "HAMPTON_ROADS_LOW_POWER" in text
    assert "nonstationarity" in text.lower()


# ---------------------------------------------------------------------------------------
# 2. The 56 days are development-only, and the splits are disjoint
# ---------------------------------------------------------------------------------------

def _prose(path: Path) -> str:
    """Markdown prose as one line: blockquote markers stripped, whitespace collapsed.

    Needed because a sentence inside a `>` block wraps as `... may\\n> **not** be ...`, and a
    naive whitespace collapse leaves the marker embedded mid-sentence.
    """
    lines = [re.sub(r"^\s*>\s?", "", ln) for ln in path.read_text(encoding="utf-8").splitlines()]
    return " ".join(" ".join(lines).split())


def test_development_set_is_declared_development_only():
    text = _prose(SPLIT_DOC)
    assert "measurement_protocol_development_set" in text
    assert "may **not** be used as validation evidence" in text


def test_split_document_lists_every_development_day_with_a_hash():
    text = SPLIT_DOC.read_text(encoding="utf-8")
    days = sampling.baseline_days()
    assert len(days) == 56
    for day in days:
        assert day in text, f"{day} missing from split document"
    assert len(re.findall(r"`[0-9a-f]{64}`", text)) >= 2 * len(days), (
        "expected an extract hash and a national hash for every development day"
    )


def test_development_and_blind_samples_are_disjoint():
    assert sampling.splits_are_disjoint()
    assert not (set(sampling.baseline_days()) & set(sampling.blind_days()))


def test_blind_sample_starts_after_the_development_set_ends():
    assert min(sampling.blind_days()) > max(sampling.baseline_days())


def test_gap_exceeds_the_lookback_so_no_blind_baseline_reaches_development_data():
    from datetime import date

    gap = (
        date.fromisoformat(min(sampling.blind_days()))
        - date.fromisoformat(max(sampling.baseline_days()))
    ).days
    assert gap > dv2.LOOKBACK_DAYS, (
        "the first blind day's trailing window must not be able to reach development days"
    )


def test_blind_sample_is_contiguous():
    from datetime import date, timedelta

    days = sampling.blind_days()
    for a, b in zip(days, days[1:]):
        assert date.fromisoformat(b) - date.fromisoformat(a) == timedelta(days=1)


def test_blind_sample_is_deterministic_and_takes_no_arguments():
    import inspect

    assert not inspect.signature(sampling.blind_days).parameters
    assert sampling.blind_days() == sampling.blind_days()


# ---------------------------------------------------------------------------------------
# 3. Pre-registration exists, and matches the code
# ---------------------------------------------------------------------------------------

def test_protocol_and_blind_sample_documents_exist():
    assert PROTOCOL_DOC.exists(), "protocol must be pre-registered before blind acquisition"
    assert BLIND_DOC.exists(), "blind sample must be frozen before acquisition"


def test_frozen_parameters_have_their_declared_values():
    assert dv2.LOOKBACK_DAYS == 14
    assert dv2.MIN_LOOKBACK_PRESENT == 10
    assert dv2.SCALE_FLOOR == 1.0
    assert dv2.RESIDUAL_THRESHOLD == 3.0
    assert dv2.PERSISTENCE_DAYS == 4
    assert dv2.COVERAGE_GUARD_RESIDUAL == 3.0
    assert dv2.COVERAGE_CONFOUND_SHARE == 0.5


def test_protocol_document_states_the_same_parameters_as_the_code():
    text = PROTOCOL_DOC.read_text(encoding="utf-8")
    for value in ("14", "3.0", "4", "1.0", "10"):
        assert value in text
    assert "LOOKBACK_DAYS" in text and "RESIDUAL_THRESHOLD" in text


def test_blind_document_states_the_frozen_date_range():
    text = BLIND_DOC.read_text(encoding="utf-8")
    assert sampling.BLIND_FIRST_DAY in text
    assert max(sampling.blind_days()) in text
    assert str(sampling.BLIND_DAYS) in text


# ---------------------------------------------------------------------------------------
# 4. Causality — the property most easily lost
# ---------------------------------------------------------------------------------------

def _dates(n: int) -> list[str]:
    from datetime import date, timedelta

    start = date(2023, 1, 1)
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def test_future_observations_cannot_change_a_past_residual():
    n = 40
    dates = _dates(n)
    base = [5.0] * n
    mutated = list(base)
    mutated[30:] = [900.0] * (n - 30)  # anything at all, later

    a = dv2.residuals(dates, base)
    b = dv2.residuals(dates, mutated)
    for i in range(30):
        assert a[i].residual == b[i].residual, f"day {i} changed when the future changed"
        assert a[i].expected == b[i].expected


def test_the_day_under_test_is_excluded_from_its_own_baseline():
    n = 30
    dates = _dates(n)
    values = [5.0] * n
    spiked = list(values)
    spiked[20] = 50.0

    rows = dv2.residuals(dates, spiked)
    # If day 20 were included in its own window the median would shift and the residual shrink.
    assert rows[20].expected == 5.0
    assert rows[20].residual == pytest.approx((50.0 - 5.0) / 1.0)


def test_baseline_uses_a_strictly_trailing_slice_not_a_centred_one():
    source = (REPO / "event_sim" / "detect" / "detector_v2.py").read_text(encoding="utf-8")
    assert "values[lo:i]" in source, "expected a trailing slice ending at i (exclusive)"
    for banned in ("center=True", "centered", "center_window"):
        assert banned not in source


def test_first_days_have_no_residual_because_the_lookback_is_not_yet_filled():
    dates = _dates(20)
    rows = dv2.residuals(dates, [5.0] * 20)
    assert all(r.residual is None for r in rows[: dv2.MIN_LOOKBACK_PRESENT])
    assert rows[dv2.MIN_LOOKBACK_PRESENT].residual is not None


# ---------------------------------------------------------------------------------------
# 5. Trend-awareness — the whole point of v2
# ---------------------------------------------------------------------------------------

def test_a_steady_drift_produces_no_trigger():
    """The exact series shape that killed v1: a long monotonic rise, no disruption."""
    n = 200
    dates = _dates(n)
    values = [3.0 + 0.09 * i for i in range(n)]  # steeper than the observed worst drift
    rows = dv2.residuals(dates, values)
    assert dv2.detect(rows) == []


def test_a_step_change_is_detected_regardless_of_the_level_it_sits_on():
    """Level invariance: the same absolute jump on a low and a high background."""
    n = 60
    dates = _dates(n)
    found = []
    for base in (4.0, 40.0):
        values = [base] * n
        for i in range(30, 40):
            values[i] = base + 8.0
        found.append(dv2.detect(dv2.residuals(dates, values)))
    assert len(found[0]) == 1 and len(found[1]) == 1
    assert found[0][0].start == found[1][0].start
    assert found[0][0].duration_days == found[1][0].duration_days


def test_a_transient_shorter_than_the_persistence_rule_is_rejected():
    n = 60
    dates = _dates(n)
    values = [5.0] * n
    for i in range(30, 30 + dv2.PERSISTENCE_DAYS - 1):
        values[i] = 99.0
    assert dv2.detect(dv2.residuals(dates, values)) == []


def test_persistence_is_short_enough_to_survive_baseline_adaptation():
    """C4, structural: an event must not be absorbed by the median before it can persist."""
    assert dv2.PERSISTENCE_DAYS < dv2.LOOKBACK_DAYS / 2


# ---------------------------------------------------------------------------------------
# 6. Coverage handling — flag, never correct
# ---------------------------------------------------------------------------------------

def test_occupancy_is_never_divided_by_the_regional_vessel_count():
    source = (REPO / "event_sim" / "detect" / "detector_v2.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            seg = ast.get_source_segment(source, node) or ""
            assert "coverage" not in seg.lower(), (
                f"coverage appears in a division: {seg!r}; normalising would fold a "
                f"measurement correction into the anomaly statistic"
            )


def test_coverage_residual_is_computed_on_its_own_series():
    n = 40
    dates = _dates(n)
    occ = [5.0] * n
    cov = [30.0] * n
    cov[30] = 90.0
    rows = dv2.residuals(dates, occ, cov)
    assert rows[30].residual == 0.0
    assert rows[30].coverage_residual is not None and rows[30].coverage_residual > 0
    assert rows[30].coverage_flag is True


def test_a_coverage_shock_alone_does_not_create_a_trigger():
    n = 60
    dates = _dates(n)
    occ = [5.0] * n
    cov = [30.0] * n
    for i in range(30, 40):
        cov[i] = 200.0
    assert dv2.detect(dv2.residuals(dates, occ, cov)) == []


def test_a_trigger_whose_days_are_coverage_flagged_is_marked_confounded():
    n = 60
    dates = _dates(n)
    occ = [5.0] * n
    cov = [30.0] * n
    for i in range(30, 40):
        occ[i] = 25.0
        cov[i] = 200.0
    windows = dv2.detect(dv2.residuals(dates, occ, cov))
    assert len(windows) == 1
    assert windows[0].coverage_confounded is True


def test_a_trigger_without_coverage_movement_is_not_confounded():
    n = 60
    dates = _dates(n)
    occ = [5.0] * n
    cov = [30.0] * n
    for i in range(30, 40):
        occ[i] = 25.0
    windows = dv2.detect(dv2.residuals(dates, occ, cov))
    assert len(windows) == 1
    assert windows[0].coverage_confounded is False
    assert windows[0].coverage_flagged_days == 0


# ---------------------------------------------------------------------------------------
# 7. Missing data
# ---------------------------------------------------------------------------------------

def test_a_thin_lookback_leaves_the_residual_undefined():
    dates = _dates(30)
    values: list[float | None] = [None] * 25 + [5.0] * 5
    rows = dv2.residuals(dates, values)
    assert rows[27].residual is None


def test_an_undefined_day_breaks_a_run_rather_than_extending_it():
    n = 60
    dates = _dates(n)
    values: list[float | None] = [5.0] * n
    for i in range(30, 40):
        values[i] = 25.0
    values[34] = None  # a hole in the middle of what would be one long trigger
    windows = dv2.detect(dv2.residuals(dates, values))
    assert all(w.duration_days < 10 for w in windows)


# ---------------------------------------------------------------------------------------
# 8. Threshold reachability — v1's specific failure
# ---------------------------------------------------------------------------------------

def test_threshold_reachability_is_reported():
    dates = _dates(60)
    rows = dv2.residuals(dates, [5.0] * 60)
    r = dv2.threshold_reachability(rows)
    assert set(r) >= {"threshold", "max_observed_residual", "reachable"}


def test_a_flat_series_reports_the_threshold_as_unreachable():
    dates = _dates(60)
    r = dv2.threshold_reachability(dv2.residuals(dates, [5.0] * 60))
    assert r["reachable"] is False


def test_reachability_does_not_require_a_trigger_to_be_true():
    """A single spike makes the threshold reachable without satisfying persistence."""
    n = 60
    dates = _dates(n)
    values = [5.0] * n
    values[40] = 99.0
    rows = dv2.residuals(dates, values)
    assert dv2.threshold_reachability(rows)["reachable"] is True
    assert dv2.detect(rows) == []


# ---------------------------------------------------------------------------------------
# 9. The detector stays blind
# ---------------------------------------------------------------------------------------

_FORBIDDEN_IMPORTS = (
    "event_sim.engine", "event_sim.sweep", "event_sim.freeze", "event_sim.h1_report",
    "event_sim.mechanism", "event_sim.historical", "event_sim.causal_scope",
    "event_sim.registry", "event_sim.world_builder", "event_sim.api",
)


def test_detector_imports_nothing_from_h1_or_the_engine():
    tree = ast.parse((REPO / "event_sim" / "detect" / "detector_v2.py").read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    for bad in _FORBIDDEN_IMPORTS:
        assert not any(m == bad or m.startswith(bad + ".") for m in names)


def test_detector_contains_no_dates_or_event_names():
    text = (REPO / "event_sim" / "detect" / "detector_v2.py").read_text(encoding="utf-8")
    assert not re.search(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", text), "a literal date in the detector"
    for token in ("hurricane", "ian", "strike", "closure", "yantian", "baltimore",
                  "dali", "ever given", "suez", "typhoon"):
        assert not re.search(rf"\b{re.escape(token)}\b", text.lower()), f"names {token}"


def test_detector_never_uses_queue_terminology():
    text = (REPO / "event_sim" / "detect" / "detector_v2.py").read_text(encoding="utf-8")
    for bad in ("vessel_queue", "queue_length", "ships_waiting", "vessels_waiting"):
        assert bad not in text


# ---------------------------------------------------------------------------------------
# 10. Staging — downstream documents must not appear before their stage
# ---------------------------------------------------------------------------------------

def test_trigger_windows_are_frozen_before_any_historical_labelling():
    """Labels may only appear in the windows document once that document exists, and the
    results document must exist before it — detection precedes interpretation."""
    if WINDOWS_DOC.exists():
        assert RESULTS_DOC.exists(), (
            "trigger windows recorded before the blind evaluation they came from"
        )


def test_no_event3_freeze_without_a_windows_document():
    freeze = REPLAYS / "EVENT3_FREEZE_V4.md"
    if freeze.exists():
        assert WINDOWS_DOC.exists(), "Event #3 frozen before trigger windows were frozen"


# ---------------------------------------------------------------------------------------
# 11. Nothing upstream moved
# ---------------------------------------------------------------------------------------

def test_event3_eligibility_contract_is_unchanged():
    from event_sim.historical import dataset_contract as dc

    assert dc.H1_SENSITIVE_METRICS == (
        "vessel_queue", "waiting_vessels", "average_waiting_time", "anchorage_wait",
        "port_dwell_time", "container_dwell_time", "local_shipping_delay",
    )
    assert dc.DRIVER_METRICS == (
        "throughput", "arrivals", "departures", "port_capacity", "berth_availability",
    )
    assert dc.OBSERVATION_TYPES == (
        "observed", "reported", "derived", "scheduled", "estimated",
    )
    assert dc.FREQUENCY_RANK == {"daily": 3, "weekly": 2, "monthly": 1, "irregular": 0}


def test_contract_source_file_is_unchanged():
    digest = hashlib.sha256(
        (REPO / "event_sim" / "historical" / "dataset_contract.py").read_bytes()
    ).hexdigest()
    assert digest.startswith("84a2f8c3df296d0b1ef5f65b6500de38")


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
    for path in (REPO / "event_sim" / "detect").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                assert m.split(".")[0] not in {"core", "config", "ui"}
