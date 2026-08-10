"""
Tests for AIS acquisition, anchorage geometry, and state reconstruction.

The central concern is not arithmetic. It is that a reconstructed *occupancy* series must
never be presented as an observed *queue*, and that the anchorage geometry must never be
derived from the vessel observations it is used to measure. Most of what follows guards
those two properties.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from event_sim.ingest import ais
from event_sim.ingest import cfr_anchorage as cfr

GEOMETRY = Path(ais.GEOMETRY_DIR)
HAMPTON = GEOMETRY / "hampton_roads_110.168_2022-01-01.json"


# --------------------------------------------------------------------------------------
# The queue/occupancy boundary
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    ["vessel_queue", "queue", "queue_length", "ships_waiting", "vessels_waiting", "VESSEL_QUEUE"],
)
def test_queue_names_are_refused(name):
    with pytest.raises(ais.MeasurementError):
        ais.assert_not_queue_named(name)


def test_occupancy_name_is_allowed():
    assert ais.assert_not_queue_named("anchorage_occupancy") == "anchorage_occupancy"


def test_refusal_explains_why_rather_than_just_failing():
    with pytest.raises(ais.MeasurementError, match="intent"):
        ais.assert_not_queue_named("vessel_queue")


def test_reconstruction_emits_occupancy_and_never_a_queue_key():
    result = ais.reconstruct_day([], [])
    assert "anchorage_occupancy" in result
    assert not any(k in result for k in ais._FORBIDDEN_METRIC_NAMES)


def test_reconstruction_semantics_string_denies_queue_interpretation():
    assert "NOT a queue" in ais.reconstruct_day([], [])["metric_semantics"]


# --------------------------------------------------------------------------------------
# Geometry parsing
# --------------------------------------------------------------------------------------

def test_dms_conversion_matches_hand_computation():
    # 36°55′36.2″ N -> 36 + 55/60 + 36.2/3600
    got = cfr._dms_to_decimal("36", "55", "36.2", "N")
    assert got == pytest.approx(36 + 55 / 60 + 36.2 / 3600)


def test_western_longitudes_are_negative():
    assert cfr._dms_to_decimal("76", "02", "46.3", "W") < 0


def test_malformed_coordinate_returns_none_rather_than_shifting_the_polygon():
    # Part 110 contains typo'd literals such as a seconds field written "32.6.5".
    assert cfr._dms_to_decimal("32", "10", "32.6.5", "N") is None


def test_both_section_formats_parse():
    """110.197 writes 'Anchorage area (A)'; 110.168 writes 'Anchorage A [Naval Anchorage]'."""
    for section, name in (("110.197", "bolivar_roads"), ("110.168", "hampton_roads")):
        path = GEOMETRY / f"{name}_{section}_2022-01-01.json"
        if not path.exists():
            pytest.skip(f"{path.name} not frozen in this checkout")
        polys = cfr.load(path)
        assert polys and all(len(p.vertices) >= 3 for p in polys)


def test_naval_and_explosives_anchorages_are_not_commercial():
    naval = cfr.AnchoragePolygon("B", ((0, 0), (0, 1), (1, 1)), "Naval Anchorage")
    expl = cfr.AnchoragePolygon("E", ((0, 0), (0, 1), (1, 1)), "Commercial Explosives Anchorage")
    plain = cfr.AnchoragePolygon("F", ((0, 0), (0, 1), (1, 1)), "")
    assert not naval.commercial
    assert not expl.commercial
    assert plain.commercial


def test_hampton_roads_designations_were_captured():
    if not HAMPTON.exists():
        pytest.skip("Hampton Roads geometry not frozen in this checkout")
    polys = cfr.load(HAMPTON)
    assert any("Naval" in p.designation for p in polys), "naval anchorages should be labelled"
    assert any(p.commercial for p in polys), "some commercial anchorages should survive"


def test_commercial_filter_actually_removes_polygons():
    if not HAMPTON.exists():
        pytest.skip("Hampton Roads geometry not frozen in this checkout")
    region = ais.REGIONS["hampton_roads"]
    assert len(ais.commercial_polygons(region)) < len(cfr.load(HAMPTON))


def test_frozen_geometry_records_its_own_provenance():
    if not HAMPTON.exists():
        pytest.skip("Hampton Roads geometry not frozen in this checkout")
    rec = json.loads(HAMPTON.read_text(encoding="utf-8"))
    assert rec["independent_of_ais"] is True
    assert rec["source_url"].startswith("https://www.ecfr.gov/")
    assert len(rec["source_sha256"]) == 64
    assert "designated" in rec["caveat"].lower()


# --------------------------------------------------------------------------------------
# Point in polygon
# --------------------------------------------------------------------------------------

_SQUARE = ((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0))


def test_point_inside_polygon():
    assert cfr.point_in_polygon(0.5, 0.5, _SQUARE)


def test_point_outside_polygon():
    assert not cfr.point_in_polygon(1.5, 0.5, _SQUARE)
    assert not cfr.point_in_polygon(0.5, -0.5, _SQUARE)


def test_concave_polygon_excludes_the_notch():
    #  an L-shape; (0.75, 0.75) sits in the missing corner
    l_shape = ((0, 0), (0, 1), (0.5, 1), (0.5, 0.5), (1, 0.5), (1, 0))
    assert cfr.point_in_polygon(0.25, 0.25, l_shape)
    assert not cfr.point_in_polygon(0.75, 0.75, l_shape)


# --------------------------------------------------------------------------------------
# Reconstruction rules
# --------------------------------------------------------------------------------------

def _row(mmsi="1", lat=0.5, lon=0.5, sog="0.0", vtype="70", status="1"):
    return {
        "MMSI": mmsi, "LAT": str(lat), "LON": str(lon), "SOG": sog,
        "VesselType": vtype, "Status": status,
    }


def _polys():
    return [cfr.AnchoragePolygon("A", _SQUARE, "")]


def test_stationary_vessel_inside_polygon_is_counted():
    assert ais.reconstruct_day([_row()], _polys())["anchorage_occupancy"] == 1


def test_moving_vessel_inside_polygon_is_not_counted():
    fast = _row(sog=str(ais.SOG_STATIONARY_KTS + 1.0))
    assert ais.reconstruct_day([fast], _polys())["anchorage_occupancy"] == 0


def test_stationary_vessel_outside_polygon_is_not_counted():
    outside = _row(lat=9.0, lon=9.0)
    assert ais.reconstruct_day([outside], _polys())["anchorage_occupancy"] == 0


def test_self_reported_anchor_status_alone_does_not_create_occupancy():
    """Status is crew-entered. Geometry decides; the declaration does not."""
    declared_but_elsewhere = _row(lat=9.0, lon=9.0, status="1")
    result = ais.reconstruct_day([declared_but_elsewhere], _polys())
    assert result["anchorage_occupancy"] == 0
    assert result["self_reported_at_anchor_in_region"] == 1


def test_vessel_counted_despite_status_disagreeing_with_geometry():
    """Conversely, geometry counts a vessel even when the crew did not declare anchoring."""
    result = ais.reconstruct_day([_row(status="0")], _polys())
    assert result["anchorage_occupancy"] == 1
    assert result["status_agreement_rate"] == 0.0


def test_repeated_positions_count_one_vessel():
    rows = [_row(mmsi="7") for _ in range(25)]
    assert ais.reconstruct_day(rows, _polys())["anchorage_occupancy"] == 1


def test_status_agreement_is_reported_not_enforced():
    rows = [_row(mmsi="1", status="1"), _row(mmsi="2", status="0")]
    result = ais.reconstruct_day(rows, _polys())
    assert result["anchorage_occupancy"] == 2
    assert result["status_agreement_rate"] == pytest.approx(0.5)


def test_agreement_rate_is_none_when_nothing_was_checked():
    assert ais.reconstruct_day([], _polys())["status_agreement_rate"] is None


def test_unparseable_rows_are_skipped_not_guessed():
    bad = {"MMSI": "9", "LAT": "", "LON": "", "SOG": "", "VesselType": "70", "Status": ""}
    assert ais.reconstruct_day([bad], _polys())["anchorage_occupancy"] == 0


@pytest.mark.parametrize("vtype,kept", [("70", True), ("89", True), ("31", False), ("60", False)])
def test_only_cargo_and_tanker_pass_the_class_filter(vtype, kept):
    assert ais._is_deep_draft({"VesselType": vtype}) is kept


# --------------------------------------------------------------------------------------
# Region bookkeeping
# --------------------------------------------------------------------------------------

def test_houston_is_recorded_as_rejected_with_its_reason():
    reason = ais.REJECTED_REGIONS["houston_galveston"]
    assert "REJECTED" in reason
    assert "circular" in reason.lower(), "the reason must say why fitting a polygon was refused"


def test_rejected_regions_are_not_silently_available_as_regions():
    assert not set(ais.REJECTED_REGIONS) & set(ais.REGIONS)


def test_definition_change_window_is_ordered_and_explicit():
    assert ais.DEFINITION_CHANGE_AFTER < ais.DEFINITION_CHANGE_BEFORE


def test_daily_url_matches_the_published_layout():
    url = ais.daily_url("2022-01-01")
    assert url.endswith("/2022/AIS_2022_01_01.zip")
    assert url.startswith("https://coast.noaa.gov/htdata/CMSP/AISDataHandler/")
