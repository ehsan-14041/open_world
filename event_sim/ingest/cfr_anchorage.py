"""
Anchorage geometry from the law, not from the data.

Port geography for AIS measurement must come from a source that is independent of the AIS
observations themselves. Drawing a polygon around wherever ships happen to sit is circular:
the boundary would be fitted to the very behaviour the boundary is supposed to measure, and
a congestion event would silently redraw its own definition.

So the geometry comes from **33 CFR Part 110** — the federal regulation that legally defines
United States anchorage grounds by explicit latitude/longitude. Properties that matter here:

  * it is authoritative — this *is* the definition of the anchorage, not an estimate of it;
  * it is completely independent of AIS;
  * eCFR serves it **versioned by effective date**, so `definition_change` — one of the nine
    registered measurement risks — stops being an unknown and becomes something this module
    can test by diffing two dates (see `compare_versions`).

What this module does NOT do: it does not decide that a vessel inside a polygon is queueing.
A polygon says where a ship is. Intent is not in this file, and is not in AIS either — see
`event_sim.ingest.ais` for that boundary.

Usage:

    python -m event_sim.ingest.cfr_anchorage freeze --section 110.197 --date 2022-01-01
    python -m event_sim.ingest.cfr_anchorage compare --section 110.197 \
        --dates 2017-01-01 2019-01-01 2022-01-01 2024-01-01
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Sequence

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
GEOMETRY_DIR = _PROJECT_ROOT / "data" / "external" / "ais" / "geometry"

#: eCFR public versioner API. No key, no registration; documented at
#: https://www.ecfr.gov/developers/documentation/api/v1
ECFR_FULL_XML = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-33.xml?part=110"

#: Degrees-minutes-seconds as Part 110 writes it, e.g. ``29°20′48.5″ N``.
_DMS = re.compile(r"(\d+)\s*°\s*(\d+)\s*′\s*([\d.]+)\s*″\s*([NSEW])")

#: Part 110 spells the column header "Longtitude". Preserved here as an observed fact about
#: the source rather than silently corrected, because the typo is a useful fingerprint that
#: the parse is reading the real table.
_SOURCE_HEADER_TYPO = "Longtitude"


class GeometryError(RuntimeError):
    """Raised when the regulation cannot be parsed into usable geometry."""


#: Part 110 writes anchorages two ways: ``Anchorage area (A)`` and ``Anchorage A``.
_ANCHORAGE_HEAD = re.compile(r"Anchorage (?:area )?\(?([A-Z])\)?(?![a-z])")

#: Bracketed designation, e.g. ``Anchorage B [Naval Anchorage]``.
_DESIGNATION = re.compile(r"\[([^\]]{0,60})\]")

#: Berths defined as a circle around a centre point rather than by a vertex list. Skipped:
#: a single centre coordinate is not a polygon, and treating it as one would invent area.
_CIRCULAR = "arc of a circle"

#: Designations that are not commercial waiting. A naval or explosives anchorage holds
#: vessels for reasons unrelated to port service, so counting it would contaminate the
#: measurement even before the vessel-type filter is applied.
_NON_COMMERCIAL = ("naval", "explosive")


@dataclass(frozen=True)
class AnchoragePolygon:
    """One legally defined anchorage area."""

    label: str
    vertices: tuple[tuple[float, float], ...]  # (lat, lon), decimal degrees, WGS84
    designation: str = ""

    @property
    def commercial(self) -> bool:
        d = self.designation.lower()
        return not any(k in d for k in _NON_COMMERCIAL)

    def bbox(self) -> tuple[float, float, float, float]:
        lats = [v[0] for v in self.vertices]
        lons = [v[1] for v in self.vertices]
        return (min(lats), max(lats), min(lons), max(lons))


def _fetch(date: str, timeout: int = 120) -> str:
    url = ECFR_FULL_XML.format(date=date)
    req = urllib.request.Request(url, headers={"Accept": "application/xml"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise GeometryError(f"eCFR returned HTTP {resp.status} for {date}")
        return resp.read().decode("utf-8", errors="replace")


def _plain_text(xml: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(xml))


def _section_text(plain: str, section: str) -> str:
    """Slice out one section, e.g. ``110.197``, up to the next section heading."""
    start = plain.find(f"{section} ")
    if start < 0:
        raise GeometryError(f"section {section} not present in this revision of Part 110")
    nxt = re.search(r"§?\s*110\.\d+[a-z]?\s", plain[start + len(section) + 1 :])
    end = start + len(section) + 1 + nxt.start() if nxt else len(plain)
    return plain[start:end]


def _dms_to_decimal(deg: str, minute: str, sec: str, hemi: str) -> float | None:
    """Convert one DMS literal, or None if the source text is malformed.

    Part 110 contains a small number of typo'd literals (e.g. a seconds field written
    ``32.6.5``). Returning None keeps the surrounding polygon's coordinate pairing honest
    instead of silently shifting every following vertex by one position.
    """
    try:
        value = int(deg) + int(minute) / 60.0 + float(sec) / 3600.0
    except ValueError:
        return None
    return -value if hemi in ("S", "W") else value


def parse_section(plain: str, section: str) -> list[AnchoragePolygon]:
    """Parse every lettered anchorage polygon in one Part 110 section."""
    body = _section_text(plain, section)

    heads = list(_ANCHORAGE_HEAD.finditer(body))
    if not heads:
        raise GeometryError(f"no anchorage blocks found in {section}")

    polygons: list[AnchoragePolygon] = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        text = body[head.end() : end]
        # An anchorage's own vertex table always precedes any "Berth X-n" subsections that
        # follow it. Those subsections are circles around a centre point, so leaving them in
        # the block would make a perfectly good polygon look radius-defined and drop it.
        text = re.split(r"\bBerth\b", text, maxsplit=1)[0]
        if _CIRCULAR in text:
            # Radius-defined area: one centre point, no vertex list.
            continue

        numbers = [_dms_to_decimal(*m) for m in _DMS.findall(text)]
        if any(n is None for n in numbers) or len(numbers) < 6 or len(numbers) % 2:
            continue

        des = _DESIGNATION.search(text[:120])
        polygons.append(
            AnchoragePolygon(
                label=head.group(1),
                vertices=tuple(zip(numbers[0::2], numbers[1::2])),
                designation=des.group(1) if des else "",
            )
        )

    if not polygons:
        raise GeometryError(f"{section} parsed to zero usable polygons")
    return polygons


def point_in_polygon(lat: float, lon: float, verts: Sequence[tuple[float, float]]) -> bool:
    """Ray-casting test. Treats (lat, lon) as planar — valid at anchorage scale (~km)."""
    inside = False
    n = len(verts)
    for i in range(n):
        y1, x1 = verts[i]
        y2, x2 = verts[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            x_cross = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_cross:
                inside = not inside
    return inside


def freeze(section: str, date: str, name: str) -> Path:
    """Fetch, parse and write an immutable geometry record with source provenance."""
    xml = _fetch(date)
    digest = hashlib.sha256(xml.encode("utf-8", errors="replace")).hexdigest()
    polygons = parse_section(_plain_text(xml), section)

    record: dict[str, Any] = {
        "name": name,
        "cfr_section": f"33 CFR {section}",
        "effective_date": date,
        "source_url": ECFR_FULL_XML.format(date=date),
        "source_sha256": digest,
        "source_bytes": len(xml.encode("utf-8", errors="replace")),
        "source_header_verbatim": _SOURCE_HEADER_TYPO,
        "coordinate_system": "WGS84 decimal degrees, (lat, lon)",
        "independent_of_ais": True,
        "polygons": [asdict(p) for p in polygons],
        "caveat": (
            "These are the LEGALLY DESIGNATED anchorages only. Vessels waiting outside a "
            "designated area are not inside any polygon and will not be counted. That is an "
            "undercount, not an error, and it is registered as a measurement risk."
        ),
    }
    GEOMETRY_DIR.mkdir(parents=True, exist_ok=True)
    out = GEOMETRY_DIR / f"{name}_{section}_{date}.json"
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return out


def compare_versions(section: str, dates: Sequence[str]) -> dict[str, Any]:
    """Diff the same section across effective dates — a direct test of `definition_change`.

    If the polygons are identical across the study period, the boundary cannot be the cause
    of any trend in the reconstructed series. That is a real, checkable reassurance rather
    than an assumption, which is the whole reason for using a versioned legal source.
    """
    seen: dict[str, list[AnchoragePolygon]] = {}
    errors: dict[str, str] = {}
    for date in dates:
        try:
            seen[date] = parse_section(_plain_text(_fetch(date)), section)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            errors[date] = f"{type(exc).__name__}: {exc}"

    fingerprints = {
        date: hashlib.sha256(
            json.dumps([asdict(p) for p in polys], sort_keys=True).encode()
        ).hexdigest()
        for date, polys in seen.items()
    }
    distinct = sorted(set(fingerprints.values()))
    return {
        "section": section,
        "dates_checked": list(dates),
        "errors": errors,
        "fingerprints": fingerprints,
        "distinct_definitions": len(distinct),
        "stable": len(distinct) == 1 and not errors,
        "vertex_counts": {d: [len(p.vertices) for p in polys] for d, polys in seen.items()},
    }


def load(path: Path) -> list[AnchoragePolygon]:
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        AnchoragePolygon(
            label=p["label"],
            vertices=tuple(tuple(v) for v in p["vertices"]),
            designation=p.get("designation", ""),
        )
        for p in record["polygons"]
    ]


def _main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("freeze")
    f.add_argument("--section", required=True)
    f.add_argument("--date", required=True)
    f.add_argument("--name", default="anchorage")

    c = sub.add_parser("compare")
    c.add_argument("--section", required=True)
    c.add_argument("--dates", nargs="+", required=True)

    args = parser.parse_args(argv)
    if args.cmd == "freeze":
        out = freeze(args.section, args.date, args.name)
        record = json.loads(out.read_text(encoding="utf-8"))
        print(f"wrote {out}")
        for p in record["polygons"]:
            tag = f" [{p['designation']}]" if p["designation"] else ""
            print(f"  anchorage {p['label']}: {len(p['vertices'])} vertices{tag}")
        return 0

    result = compare_versions(args.section, args.dates)
    print(json.dumps(result, indent=2))
    return 0 if result["stable"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
