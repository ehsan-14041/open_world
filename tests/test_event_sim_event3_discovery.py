"""
Tests for Event #3 sequential discovery.

Detector development is finished, so these defend a different claim from the earlier suites:
that the *search* cannot be steered. The universe is a function of the calendar and publisher
availability, the ordering is chronological, no event name can influence it, and every trigger
is frozen before anything external is consulted.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from event_sim.detect import detector_v2 as dv2
from event_sim.detect import detector_v3 as dv3
from event_sim.detect import discovery as dsc
from event_sim.detect import sampling

REPO = Path(__file__).resolve().parent.parent
REPLAYS = REPO / "docs" / "replays"
DISCOVERY_SRC = REPO / "event_sim" / "detect" / "discovery.py"
FREEZE_DOC = REPLAYS / "HAMPTON_ROADS_DETECTOR_FINAL_FREEZE.md"
UNIVERSE_DOC = REPLAYS / "EVENT3_DISCOVERY_UNIVERSE.md"
LEDGER = REPLAYS / "EVENT3_DISCOVERY_LEDGER.md"
FINAL_FREEZE = REPLAYS / "EVENT3_FREEZE_FINAL.md"
DRIVER_GAP = REPLAYS / "EVENT3_DRIVER_GAP.md"

FROZEN_SEMANTIC_HASH = "49ed3b935527f1fb000ad348c411c5049070b672eb01eea69e4f457e97022f73"


def _prose(p: Path) -> str:
    lines = [re.sub(r"^\s*>\s?", "", ln) for ln in p.read_text(encoding="utf-8").splitlines()]
    return " ".join(" ".join(lines).split())


def _days(n: int, start: date = date(2021, 1, 1)) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


# --- instrument and history frozen -------------------------------------------------------

def test_detector_semantic_hash_unchanged():
    payload = json.loads(
        (REPO / "data" / "external" / "ais" / "detector_v3_final_freeze.json").read_text("utf-8")
    )
    recomputed = hashlib.sha256(
        json.dumps(payload["parameters"], sort_keys=True).encode()
    ).hexdigest()
    assert recomputed == payload["semantic_hash"] == FROZEN_SEMANTIC_HASH


def test_detector_parameters_unchanged():
    assert (dv2.LOOKBACK_DAYS, dv2.RESIDUAL_THRESHOLD, dv2.PERSISTENCE_DAYS,
            dv2.MIN_LOOKBACK_PRESENT, dv2.SCALE_FLOOR) == (14, 3.0, 4, 10, 1.0)
    assert (dv3.V_SHIFT, dv3.M_ABRUPT, dv3.S_ABRUPT, dv3.M_STABLE, dv3.S_STABLE) == (
        3.5, 4.0, 4.5, 2.0, 2.5)
    assert dv3.WINDOW_REGIME_MIN_DAYS == 2


def test_no_detector_v4_exists():
    assert not (REPO / "event_sim" / "detect" / "detector_v4.py").exists()


@pytest.mark.parametrize("verdict,doc", [
    ("HAMPTON_ROADS_LOW_POWER", "HAMPTON_ROADS_DETECTABILITY.md"),
    ("DETECTOR_V2_COVERAGE_CONFOUNDED", "HAMPTON_ROADS_DETECTOR_V2_RESULTS.md"),
    ("DETECTOR_V3_VALID", "HAMPTON_ROADS_DETECTOR_V3_RESULTS.md"),
])
def test_all_three_verdicts_immutable(verdict, doc):
    assert verdict in (REPLAYS / doc).read_text(encoding="utf-8")


# --- universe and ordering ---------------------------------------------------------------

def test_universe_excludes_every_spent_day():
    eligible = set(dsc.eligible_days())
    for spent in (sampling.baseline_days(), sampling.blind_days(), sampling.v3_blind_days()):
        assert not (eligible & set(spent))


def test_universe_respects_geometry_era_and_availability():
    days = dsc.eligible_days()
    assert min(days) >= dsc.GEOMETRY_ERA_START
    assert max(days) <= dsc.AIS_LAST_AVAILABLE_DAY
    for lo, hi in dsc.AIS_UNAVAILABLE_SPANS:
        assert not [d for d in days if lo <= d <= hi]


def test_universe_is_deterministic_and_argument_free():
    import inspect

    assert not inspect.signature(dsc.eligible_days).parameters
    assert not inspect.signature(dsc.discovery_blocks).parameters
    assert dsc.discovery_blocks() == dsc.discovery_blocks()


def test_blocks_are_strictly_chronological():
    blocks = dsc.discovery_blocks()
    starts = [b.discovery_start for b in blocks]
    assert starts == sorted(starts)
    for a, b in zip(blocks, blocks[1:]):
        assert a.discovery_end < b.discovery_start


def test_discovery_days_are_never_reused_across_blocks():
    seen: set[str] = set()
    for b in dsc.discovery_blocks():
        days = set(b.discovery_days)
        assert not (days & seen), "a discovery day appears in two blocks"
        seen |= days


def test_discovery_days_never_include_spent_days():
    spent = (set(sampling.baseline_days()) | set(sampling.blind_days())
             | set(sampling.v3_blind_days()))
    for b in dsc.discovery_blocks():
        assert not (set(b.discovery_days) & spent)


def test_ordering_logic_contains_no_event_knowledge():
    """The module may name availability and geometry boundaries, and nothing else."""
    src = DISCOVERY_SRC.read_text(encoding="utf-8")
    allowed = {dsc.GEOMETRY_ERA_START, dsc.AIS_LAST_AVAILABLE_DAY,
               dsc.GEOMETRY_CHANGE_LAST_OLD_DAY, dsc.GEOMETRY_VERIFIED_STABLE_THROUGH}
    allowed |= {d for span in dsc.AIS_UNAVAILABLE_SPANS for d in span}
    # The frozen geometry's eCFR effective date is a measurement-definition reference, not
    # event knowledge. Derived from the artifact filename so it cannot drift from the truth.
    from event_sim.ingest import ais

    allowed |= set(re.findall(
        r"\d{4}-\d{2}-\d{2}", ais.REGIONS["hampton_roads"].geometry_file))
    for found in re.findall(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b", src):
        assert found in allowed, f"unexplained date literal in ordering logic: {found}"
    for token in ("hurricane", "typhoon", "strike", "closure", "congestion",
                  "yantian", "baltimore", "elliott"):
        assert not re.search(rf"\b{token}\b", src.lower()), f"names {token}"


def test_block_count_respects_the_pre_registered_budget():
    assert len(dsc.discovery_blocks()) <= dsc.MAX_DISCOVERY_BLOCKS


def test_budget_is_declared_in_the_universe_document():
    assert str(dsc.MAX_DISCOVERY_BLOCKS) in UNIVERSE_DOC.read_text(encoding="utf-8")


# --- boundary continuity ------------------------------------------------------------------

def test_every_block_has_a_full_lookback_of_acquired_warmup():
    for b in dsc.discovery_blocks():
        assert len(b.warmup_days) == dv2.LOOKBACK_DAYS
        assert b.warmup_end < b.discovery_start
        gap = (date.fromisoformat(b.discovery_start)
               - date.fromisoformat(b.warmup_end)).days
        assert gap == 1, "warmup must run up to the day before discovery starts"


def test_warmup_and_discovery_days_are_contiguous():
    for b in dsc.discovery_blocks():
        days = b.all_days
        for x, y in zip(days, days[1:]):
            assert date.fromisoformat(y) - date.fromisoformat(x) == timedelta(days=1)


def test_a_block_boundary_cannot_manufacture_a_trigger():
    """A flat series carried across a boundary must produce no trigger anywhere."""
    days = _days(120)
    assert dv3.detect_occupancy(dv3.occupancy_residuals(days, [10.0] * 120)) == []


# --- recovery and extension fixed ---------------------------------------------------------

def test_recovery_parameters_are_fixed():
    assert dsc.RECOVERY_RESIDUAL_BAND == 1.0
    assert dsc.RECOVERY_DAYS == 7
    assert dsc.RECOVERY_DAYS > dv2.PERSISTENCE_DAYS, (
        "recovery must be harder to satisfy than persistence, else a mid-event dip passes"
    )


def test_extension_rule_is_fixed():
    assert dsc.EXTENSION_INCREMENT_DAYS == 14
    assert dsc.MAX_EXTENSION_DAYS == 56
    assert dsc.MAX_EXTENSION_DAYS % dsc.EXTENSION_INCREMENT_DAYS == 0


def test_recovery_requires_the_full_run_after_the_window():
    days = _days(20)
    resid = [5.0] * 5 + [0.0] * 6 + [5.0] * 9   # six clean days, one short
    assert dsc.find_recovery(days, resid, days[4]) is None


def test_recovery_is_reported_at_completion_not_at_onset():
    days = _days(20)
    resid = [5.0] * 5 + [0.0] * 10 + [5.0] * 5
    assert dsc.find_recovery(days, resid, days[4]) == days[11]


def test_a_gap_breaks_a_recovery_run():
    days = _days(20)
    resid = [5.0] * 5 + [0.0, 0.0, 0.0, None, 0.0, 0.0, 0.0, 0.0] + [5.0] * 7
    assert dsc.find_recovery(days, resid, days[4]) is None


def test_recovery_ignores_days_inside_the_window():
    days = _days(20)
    assert dsc.find_recovery(days, [0.0] * 20, days[9]) == days[16]


# --- isolation from H1 ---------------------------------------------------------------------

_FORBIDDEN = ("event_sim.engine", "event_sim.sweep", "event_sim.h1_report",
              "event_sim.mechanism", "event_sim.historical", "event_sim.causal_scope",
              "event_sim.registry", "event_sim.world_builder", "event_sim.api")


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_discovery_module_imports_no_h1_or_engine():
    names = _imports(DISCOVERY_SRC)
    for bad in _FORBIDDEN:
        assert not any(m == bad or m.startswith(bad + ".") for m in names)


def test_discovery_runner_imports_no_h1_or_engine():
    runner = REPO / "scripts" / "event3_discovery_block.py"
    if runner.exists():
        names = _imports(runner)
        for bad in _FORBIDDEN:
            assert not any(m == bad or m.startswith(bad + ".") for m in names)


def test_discovery_does_not_touch_the_operations_product():
    for m in _imports(DISCOVERY_SRC):
        assert m.split(".")[0] not in {"core", "config", "ui"}


# --- staging, ledger, stopping --------------------------------------------------------------

def test_freeze_and_universe_documents_exist():
    assert FREEZE_DOC.exists() and UNIVERSE_DOC.exists()
    assert FROZEN_SEMANTIC_HASH in FREEZE_DOC.read_text(encoding="utf-8")


def test_no_final_freeze_without_a_ledger():
    if FINAL_FREEZE.exists():
        assert LEDGER.exists(), "Event #3 frozen without any trigger ever being recorded"


def test_driver_gap_and_final_freeze_are_mutually_exclusive():
    assert not (FINAL_FREEZE.exists() and DRIVER_GAP.exists())


def test_ledger_freezes_triggers_before_classification():
    if not LEDGER.exists():
        pytest.skip("no ledger yet")
    text = _prose(LEDGER).lower()
    if "classification" in text:
        assert "frozen" in text or "before" in text


def test_first_qualified_rule_declared():
    assert "first chronologically encountered" in _prose(UNIVERSE_DOC).lower()


def test_only_the_four_declared_outcomes_exist():
    text = UNIVERSE_DOC.read_text(encoding="utf-8")
    for outcome in ("EVENT3_FROZEN_READY_FOR_HELDOUT",
                    "NO_QUALIFYING_EVENT_IN_SEARCH_UNIVERSE",
                    "EVENT3_DRIVER_GAP", "MEASUREMENT_INTEGRITY_FAILURE"):
        assert outcome in text


# --- upstream unchanged ---------------------------------------------------------------------

def test_event3_eligibility_contract_unchanged():
    from event_sim.historical import dataset_contract as dc

    assert dc.H1_SENSITIVE_METRICS == (
        "vessel_queue", "waiting_vessels", "average_waiting_time", "anchorage_wait",
        "port_dwell_time", "container_dwell_time", "local_shipping_delay")
    assert dc.DRIVER_METRICS == (
        "throughput", "arrivals", "departures", "port_capacity", "berth_availability")
    assert dc.FREQUENCY_RANK == {"daily": 3, "weekly": 2, "monthly": 1, "irregular": 0}


def test_frozen_model_hashes_unchanged():
    from event_sim.freeze import snapshot

    snap = snapshot()
    assert snap["modules"]["port_disruption"] == (
        "d4670fb108c2e9a3c45d33455a652578e7a72bfce69f88ed44c6b355ead13f5b")
    assert snap["modules"]["port_disruption_h1_queue_experimental"] == (
        "324a8bf1d67d56ad082b9c7540f7d155466af50ad71359c1b4836ef79f8f3889")
    assert snap["evaluation_code"] == (
        "880d2d0ef0cc0e3d32ea6f7b1464248a825225cdb1f2445cd372ce2f9239f992")
