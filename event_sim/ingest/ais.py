"""
AIS acquisition and state reconstruction — and an explicit refusal to call it a queue.

Source: NOAA / BOEM / USCG **Marine Cadastre National AIS**, daily nationwide vessel
position files at ``coast.noaa.gov/htdata/CMSP/AISDataHandler/<year>/AIS_<date>.zip``.
Public domain, no registration, no key. Accessibility was proven with real bytes before
this module was written (see docs/replays/EVENT3_DATASET_SELECTION_V3.md).

------------------------------------------------------------------------------------------
The one thing to understand before using anything here
------------------------------------------------------------------------------------------

AIS is a stream of *positions*. It contains no arrival event, no berth assignment, no
booking, no service order, and above all **no statement of intent**. A ship sitting still
inside an anchorage might be waiting for a berth, waiting for cargo documents, waiting for
weather, changing crew, under repair, or simply cheap to park there.

Therefore this module emits:

    anchorage_occupancy — how many distinct deep-draft vessels were inside a legally
                          designated anchorage polygon, moving slower than a threshold,
                          on a given day.

and it does **not** emit ``vessel_queue``. Occupancy is an observation. A queue is an
interpretation that requires knowing why each ship is there, and AIS cannot supply that.
`assert_not_queue_named` enforces this at runtime so the distinction cannot be lost by a
later rename — the project has already been burned once by a precise official number that
turned out to measure the wrong quantity.

Occupancy may still be a useful *proxy* for queue length. Proxy status is recorded, not
assumed away, and it is the reason the resulting node is classified ``proxy_observable``
rather than ``observable``.

------------------------------------------------------------------------------------------
Reconstruction rules, stated before any measurement
------------------------------------------------------------------------------------------

1. **Geometry is external.** Polygons come from 33 CFR 110 via
   `event_sim.ingest.cfr_anchorage`, never from where ships were observed to sit.
2. **Vessel class filter.** Only AIS VesselType 70-89 (cargo, tanker). Excludes tugs,
   fishing, pleasure craft and the inland towboat traffic that otherwise dominates record
   counts on river systems.
3. **Stationarity.** Speed over ground below `SOG_STATIONARY_KTS`. A moving ship transiting
   a polygon is not occupying it.
4. **Presence, not persistence.** A vessel counts for a day if it satisfies (1)-(3) at any
   sampled instant that day; the metric is distinct-MMSI occupancy, not vessel-hours.
5. **Self-reported navigational status is a cross-check, never the definition.** AIS
   ``Status`` is keyed in by the crew. It is recorded and its agreement rate with the
   geometric reconstruction is reported, because disagreement is diagnostic — but the
   measurement stands on geometry and speed, which are observed rather than declared.

Usage:

    python -m event_sim.ingest.ais fetch --date 2022-01-01 --region hampton_roads
    python -m event_sim.ingest.ais series --region hampton_roads
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import tempfile
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from event_sim.ingest.cfr_anchorage import AnchoragePolygon, load as load_geometry, point_in_polygon

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AIS_ROOT = _PROJECT_ROOT / "data" / "external" / "ais"
GEOMETRY_DIR = AIS_ROOT / "geometry"
DAILY_DIR = AIS_ROOT / "daily"
METADATA_DIR = AIS_ROOT / "metadata"

DAILY_URL = "https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{year}/AIS_{y}_{m}_{d}.zip"

#: Below this speed over ground (knots) a vessel is treated as stationary.
SOG_STATIONARY_KTS = 0.5

#: AIS/ITU vessel type codes retained: 70-79 cargo, 80-89 tanker.
DEEP_DRAFT_TYPES = range(70, 90)

#: The anchorage boundary in 33 CFR 110.197 changed between these dates. Windows that
#: straddle the change are not comparable. Established empirically by diffing eCFR
#: revisions, before any measurement — see cfr_anchorage.compare_versions.
DEFINITION_CHANGE_AFTER = "2018-03-01"
DEFINITION_CHANGE_BEFORE = "2018-06-01"

#: Names this module refuses to attach to a reconstructed series.
_FORBIDDEN_METRIC_NAMES = {
    "vessel_queue",
    "queue",
    "queue_length",
    "ships_waiting",
    "vessels_waiting",
    "waiting_vessels",
}


class MeasurementError(RuntimeError):
    """Raised when a reconstruction would misrepresent what AIS can support."""


def assert_not_queue_named(metric_name: str) -> str:
    """Reject any attempt to publish reconstructed AIS occupancy as a queue.

    AIS carries no statement of intent, so it cannot distinguish a ship waiting for a berth
    from a ship anchored for any other reason. Naming the series a queue would assert the
    difference had been observed. It has not been.
    """
    if metric_name.strip().lower() in _FORBIDDEN_METRIC_NAMES:
        raise MeasurementError(
            f"refusing to name an AIS-reconstructed series {metric_name!r}: AIS observes "
            f"position and speed, not intent. Use 'anchorage_occupancy'. If a genuine "
            f"queue measurement is required, it needs a source that records berth requests."
        )
    return metric_name


@dataclass(frozen=True)
class Region:
    """A study region: a coarse filter box plus the legal anchorage geometry inside it."""

    name: str
    bbox: tuple[float, float, float, float]  # (lat_min, lat_max, lon_min, lon_max)
    geometry_file: str
    description: str


REGIONS: dict[str, Region] = {
    "hampton_roads": Region(
        name="hampton_roads",
        bbox=(36.80, 37.10, -76.45, -75.95),
        geometry_file="hampton_roads_110.168_2022-01-01.json",
        description=(
            "Hampton Roads / Norfolk port approach. Selected because the independent legal "
            "anchorage geometry demonstrably contains the observed waiting fleet (median "
            "distance from a stationary deep-draft vessel to a designated anchorage: 0.9 km, "
            "none beyond 10 km). Selection used measurement-validity criteria only."
        ),
    ),
}

#: Regions examined and rejected on measurement grounds, kept so the rejection is auditable
#: rather than invisible. A region that fails containment cannot be rescued by fetching more
#: days of it — the geometry simply does not describe where the ships are.
REJECTED_REGIONS: dict[str, str] = {
    "houston_galveston": (
        "REJECTED: 33 CFR 110 designates only Bolivar Roads (110.197) near Houston, and 111 "
        "of 120 observed stationary deep-draft vessels lay more than 10 km outside it "
        "(median 30.3 km). A full day's reconstruction found occupancy=2 against ~55 vessels "
        "self-reporting at anchor in the region. Deep-draft vessels wait for Houston in "
        "offshore areas that carry no Part 110 designation, so no AIS-independent legal "
        "boundary exists to measure them. Drawing a polygon around where they were observed "
        "would be circular and is not done."
    ),
    "san_francisco_bay": (
        "REJECTED: containment is good (median 1.1 km) but 33 CFR 110.224 spans San Pablo "
        "Bay, Carquinez Strait, Suisun Bay and the Sacramento River — roughly 100 km of "
        "inland waterway. The geometry describes a river system rather than a port approach, "
        "which fails local specificity."
    ),
}


def _record_path(path: Path) -> str:
    try:
        return str(path.relative_to(_PROJECT_ROOT))
    except ValueError:
        return str(path)


def daily_url(date: str) -> str:
    y, m, d = date.split("-")
    return DAILY_URL.format(year=y, y=y, m=m, d=d)


def _iter_national_rows(zip_path: Path) -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(zip_path) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(members) != 1:
            raise MeasurementError(f"expected one CSV member, found {members!r}")
        with zf.open(members[0]) as raw:
            yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))


def _is_deep_draft(row: dict[str, str]) -> bool:
    try:
        return int(row["VesselType"]) in DEEP_DRAFT_TYPES
    except (KeyError, TypeError, ValueError):
        return False


def _in_bbox(row: dict[str, str], bbox: tuple[float, float, float, float]) -> bool:
    try:
        lat, lon = float(row["LAT"]), float(row["LON"])
    except (KeyError, TypeError, ValueError):
        return False
    la0, la1, lo0, lo1 = bbox
    return la0 <= lat <= la1 and lo0 <= lon <= lo1


def fetch_day(date: str, region: Region, keep_national: bool = False) -> dict[str, Any]:
    """Download one national day, filter to the region, and store only the extract.

    The national file is ~284 MB and covers the entire United States; all but a few thousand
    rows are irrelevant here. It is streamed to a temporary file, filtered, and deleted. Only
    the regional extract and its provenance record persist.
    """
    url = daily_url(date)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    hasher = hashlib.sha256()
    total = 0
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        with urllib.request.urlopen(url, timeout=600) as resp:
            if resp.status != 200:
                raise MeasurementError(f"HTTP {resp.status} for {url}")
            while chunk := resp.read(1 << 20):
                hasher.update(chunk)
                total += len(chunk)
                tmp.write(chunk)

    try:
        kept: list[dict[str, str]] = []
        scanned = 0
        for row in _iter_national_rows(tmp_path):
            scanned += 1
            if _is_deep_draft(row) and _in_bbox(row, region.bbox):
                kept.append(row)

        out = DAILY_DIR / f"{region.name}_{date}.csv"
        if kept:
            with out.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(kept[0].keys()))
                writer.writeheader()
                writer.writerows(kept)

        record = {
            "date": date,
            "region": region.name,
            "source_url": url,
            "national_sha256": hasher.hexdigest(),
            "national_bytes": total,
            "national_rows_scanned": scanned,
            "regional_rows_kept": len(kept),
            "distinct_mmsi": len({r["MMSI"] for r in kept}),
            "extract_path": _record_path(out),
            "filters": {
                "vessel_types": "70-89 (cargo, tanker)",
                "bbox": list(region.bbox),
            },
            "national_file_retained": keep_national,
        }
        (METADATA_DIR / f"{region.name}_{date}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )
        return record
    finally:
        if not keep_national:
            tmp_path.unlink(missing_ok=True)


def reconstruct_day(
    rows: Iterable[dict[str, str]], polygons: Sequence[AnchoragePolygon]
) -> dict[str, Any]:
    """Reconstruct one day's anchorage occupancy from regional AIS rows.

    Returns occupancy plus the diagnostics needed to judge it: per-polygon breakdown, and
    the agreement rate between the geometric reconstruction and the crew-entered AIS
    navigational status. Agreement is reported, never used as the definition.
    """
    occupying: set[str] = set()
    per_polygon: dict[str, set[str]] = defaultdict(set)
    self_reported_anchored: set[str] = set()
    all_vessels: set[str] = set()
    agree = disagree = 0

    for row in rows:
        mmsi = row.get("MMSI", "")
        if not mmsi:
            continue
        all_vessels.add(mmsi)
        try:
            lat, lon, sog = float(row["LAT"]), float(row["LON"]), float(row["SOG"])
        except (KeyError, TypeError, ValueError):
            continue

        if row.get("Status") == "1":  # 1 = at anchor, self-reported
            self_reported_anchored.add(mmsi)

        if sog > SOG_STATIONARY_KTS:
            continue
        for poly in polygons:
            if point_in_polygon(lat, lon, poly.vertices):
                occupying.add(mmsi)
                per_polygon[poly.label].add(mmsi)
                if row.get("Status") == "1":
                    agree += 1
                else:
                    disagree += 1
                break

    checked = agree + disagree
    return {
        # Named deliberately. See assert_not_queue_named.
        "anchorage_occupancy": len(occupying),
        "per_polygon": {k: len(v) for k, v in sorted(per_polygon.items())},
        "distinct_vessels_in_region": len(all_vessels),
        "self_reported_at_anchor_in_region": len(self_reported_anchored),
        "status_agreement_rate": round(agree / checked, 4) if checked else None,
        "metric_semantics": (
            "count of distinct cargo/tanker MMSI observed stationary inside a legally "
            "designated anchorage polygon at any point during the day; NOT a queue"
        ),
    }


def commercial_polygons(region: Region) -> list[AnchoragePolygon]:
    """Load the region's geometry, keeping only commercially usable anchorages.

    Naval and explosives anchorages are excluded: vessels occupy them for reasons unrelated
    to port service, so their occupancy is not evidence about port congestion.
    """
    return [p for p in load_geometry(GEOMETRY_DIR / region.geometry_file) if p.commercial]


def build_series(region: Region) -> list[dict[str, Any]]:
    """Assemble the daily occupancy series from whatever days have been fetched."""
    polygons = commercial_polygons(region)
    series: list[dict[str, Any]] = []
    for path in sorted(DAILY_DIR.glob(f"{region.name}_*.csv")):
        date = path.stem.rsplit("_", 1)[-1]
        with path.open(encoding="utf-8") as fh:
            day = reconstruct_day(csv.DictReader(fh), polygons)
        day["date"] = date
        series.append(day)
    return series


def _main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch")
    f.add_argument("--date", required=True)
    f.add_argument("--region", default="hampton_roads")

    s = sub.add_parser("series")
    s.add_argument("--region", default="hampton_roads")

    args = parser.parse_args(argv)
    if args.region in REJECTED_REGIONS:
        print(f"region {args.region!r} was rejected on measurement grounds:")
        print(f"  {REJECTED_REGIONS[args.region]}")
        return 2
    region = REGIONS[args.region]

    if args.cmd == "fetch":
        rec = fetch_day(args.date, region)
        print(json.dumps(rec, indent=2))
        return 0

    series = build_series(region)
    if not series:
        print(f"no fetched days for region {region.name}")
        return 1
    for day in series:
        print(
            f"  {day['date']}  occupancy={day['anchorage_occupancy']:>3}  "
            f"in-region={day['distinct_vessels_in_region']:>3}  "
            f"status-agreement={day['status_agreement_rate']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
