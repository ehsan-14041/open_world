"""
Build the daily Hampton Roads observation series from acquired AIS extracts.

Implements exactly the aggregation frozen in
docs/replays/HAMPTON_ROADS_MEASUREMENT_FREEZE.md §3. In particular:

  * a vessel contributes at most 1 to a day (distinct MMSI),
  * entries, exits and spells are only defined *within* a sampled window, never across the
    gap between two windows, because absence in a gap is unobserved rather than departure,
  * a spell touching a window edge is censored and is never reported as a completed dwell.

The censoring rule is the one that matters. With 7-day sample windows, any vessel that stays
longer than a week is guaranteed to hit an edge, so treating censored spells as completed
would systematically understate dwell — and understating dwell is exactly the direction that
would make a congestion event look smaller than it was.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from event_sim.detect.sampling import DEVELOPMENT_DAYS, window_of
from event_sim.ingest.ais import DAILY_DIR, Region, SOG_STATIONARY_KTS, commercial_polygons
from event_sim.ingest.cfr_anchorage import AnchoragePolygon, point_in_polygon


@dataclass(frozen=True)
class DayRecord:
    date: str
    window: str | None
    anchorage_occupancy: int
    entries: int | None          # None at a window's first day: undefined, not zero
    exits: int | None            # None at a window's last day
    vessels_in_region: int
    messages_kept: int
    status_agreement_rate: float | None


@dataclass(frozen=True)
class Spell:
    mmsi: str
    window: str
    first_day: str
    last_day: str
    duration_hours: float
    censored: bool               # touches a window edge, so the true dwell is longer


@dataclass
class SeriesResult:
    days: list[DayRecord] = field(default_factory=list)
    spells: list[Spell] = field(default_factory=list)

    @property
    def occupancy(self) -> list[int]:
        return [d.anchorage_occupancy for d in self.days]

    @property
    def completed_spells(self) -> list[Spell]:
        return [s for s in self.spells if not s.censored]


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def day_presence(
    path: Path, polygons: Sequence[AnchoragePolygon]
) -> tuple[dict[str, tuple[datetime, datetime]], dict[str, int]]:
    """Qualifying vessels for one day, with first/last in-anchorage timestamp.

    Returns `(presence, diagnostics)`. A vessel appears in `presence` only if it was observed
    stationary inside a commercial anchorage polygon at least once that day.
    """
    presence: dict[str, tuple[datetime, datetime]] = {}
    in_region: set[str] = set()
    kept = agree = disagree = 0

    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            mmsi = row.get("MMSI", "")
            if not mmsi:
                continue
            in_region.add(mmsi)
            try:
                lat, lon, sog = float(row["LAT"]), float(row["LON"]), float(row["SOG"])
            except (KeyError, TypeError, ValueError):
                continue
            if sog >= SOG_STATIONARY_KTS:
                continue
            if not any(point_in_polygon(lat, lon, p.vertices) for p in polygons):
                continue

            ts = _parse_ts(row.get("BaseDateTime", ""))
            if ts is None:
                continue
            kept += 1
            if row.get("Status") == "1":
                agree += 1
            else:
                disagree += 1

            first, last = presence.get(mmsi, (ts, ts))
            presence[mmsi] = (min(first, ts), max(last, ts))

    checked = agree + disagree
    diagnostics = {
        "vessels_in_region": len(in_region),
        "messages_kept": kept,
        "agree": agree,
        "checked": checked,
    }
    return presence, diagnostics


def build(region: Region, days: Iterable[str]) -> SeriesResult:
    """Assemble the series for the given days, skipping any not yet acquired."""
    polygons = commercial_polygons(region)

    presence_by_day: dict[str, dict[str, tuple[datetime, datetime]]] = {}
    diagnostics_by_day: dict[str, dict[str, int]] = {}

    for day in sorted(days):
        if day in DEVELOPMENT_DAYS:
            continue
        path = DAILY_DIR / f"{region.name}_{day}.csv"
        if not path.exists():
            continue
        presence, diagnostics = day_presence(path, polygons)
        presence_by_day[day] = presence
        diagnostics_by_day[day] = diagnostics

    ordered = sorted(presence_by_day)
    result = SeriesResult()

    for i, day in enumerate(ordered):
        win = window_of(day)
        prev = ordered[i - 1] if i else None
        nxt = ordered[i + 1] if i + 1 < len(ordered) else None

        # Entries and exits require the neighbouring day to be in the same sampled window.
        # Otherwise the neighbour is unobserved, and a vessel's absence there says nothing.
        same_prev = prev is not None and window_of(prev) == win
        same_next = nxt is not None and window_of(nxt) == win

        here = set(presence_by_day[day])
        entries = len(here - set(presence_by_day[prev])) if same_prev else None
        exits = (
            len(set(presence_by_day[day]) - set(presence_by_day[nxt])) if same_next else None
        )

        d = diagnostics_by_day[day]
        result.days.append(
            DayRecord(
                date=day,
                window=win,
                anchorage_occupancy=len(here),
                entries=entries,
                exits=exits,
                vessels_in_region=d["vessels_in_region"],
                messages_kept=d["messages_kept"],
                status_agreement_rate=(
                    round(d["agree"] / d["checked"], 4) if d["checked"] else None
                ),
            )
        )

    result.spells.extend(_spells(presence_by_day))
    return result


def _spells(
    presence_by_day: dict[str, dict[str, tuple[datetime, datetime]]]
) -> list[Spell]:
    """Maximal runs of consecutive observed days per vessel, within one window."""
    by_window: dict[str, list[str]] = {}
    for day in sorted(presence_by_day):
        win = window_of(day)
        if win is not None:
            by_window.setdefault(win, []).append(day)

    spells: list[Spell] = []
    for win, days in by_window.items():
        vessels = {m for d in days for m in presence_by_day[d]}
        for mmsi in sorted(vessels):
            run: list[str] = []
            for day in days + [None]:  # sentinel flushes the final run
                present = day is not None and mmsi in presence_by_day[day]
                if present:
                    run.append(day)
                    continue
                if run:
                    spells.append(_make_spell(mmsi, win, run, days, presence_by_day))
                    run = []
    return spells


def _make_spell(
    mmsi: str,
    window: str,
    run: list[str],
    window_days: list[str],
    presence_by_day: dict[str, dict[str, tuple[datetime, datetime]]],
) -> Spell:
    first_day, last_day = run[0], run[-1]
    start = presence_by_day[first_day][mmsi][0]
    end = presence_by_day[last_day][mmsi][1]
    censored = first_day == window_days[0] or last_day == window_days[-1]
    return Spell(
        mmsi=mmsi,
        window=window,
        first_day=first_day,
        last_day=last_day,
        duration_hours=round((end - start).total_seconds() / 3600.0, 2),
        censored=censored,
    )
