"""
Deterministic sampling of baseline windows.

The point of a mechanical rule is that it removes the analyst from the choice. A window
picked because it "looks like a normal week" has already had the thing being measured
selected out of it, and the resulting baseline variance would be too small — which would
make detection look easier than it is.

So the windows are a pure function of the calendar. There is no data-dependent branch here,
and no argument that lets a caller nudge the selection: `baseline_windows()` takes nothing.

Rule (frozen in docs/replays/HAMPTON_ROADS_MEASUREMENT_FREEZE.md §5):

    for each quarter from 2020-Q3 through 2022-Q2, take the 7-day window beginning on the
    15th of that quarter's middle month.
"""

from __future__ import annotations

from datetime import date, timedelta

#: First quarter sampled, as (year, quarter). 2020-Q3 is the first quarter fully inside the
#: geometry validity era, which begins 2020-07-01.
FIRST_QUARTER = (2020, 3)

#: Last quarter sampled. Eight quarters gives the two years the protocol requires.
LAST_QUARTER = (2022, 2)

#: Days per sampled window.
WINDOW_DAYS = 7

#: Day of the middle month on which each window starts.
WINDOW_START_DAY = 15

#: Days already used while developing the measurement. Excluded from baseline statistics so
#: the baseline is not partly fitted to days that shaped the rules.
DEVELOPMENT_DAYS = ("2022-01-01", "2022-06-15")


def _quarters() -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, q = FIRST_QUARTER
    while (y, q) <= LAST_QUARTER:
        out.append((y, q))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


def _middle_month(quarter: int) -> int:
    """Q1 -> February, Q2 -> May, Q3 -> August, Q4 -> November."""
    return 3 * (quarter - 1) + 2


def baseline_windows() -> list[tuple[str, str, str]]:
    """Return `(label, first_day, last_day)` for every sampled window, in calendar order."""
    windows: list[tuple[str, str, str]] = []
    for year, quarter in _quarters():
        start = date(year, _middle_month(quarter), WINDOW_START_DAY)
        end = start + timedelta(days=WINDOW_DAYS - 1)
        windows.append((f"{year}-Q{quarter}", start.isoformat(), end.isoformat()))
    return windows


def baseline_days() -> list[str]:
    """Every sampled day, flattened, in calendar order and free of development days."""
    days: list[str] = []
    for _, first, _last in baseline_windows():
        start = date.fromisoformat(first)
        days.extend((start + timedelta(days=i)).isoformat() for i in range(WINDOW_DAYS))
    return [d for d in days if d not in DEVELOPMENT_DAYS]


def window_of(day: str) -> str | None:
    """Which sampled window a day belongs to, or None. Used to avoid computing entries,
    exits or spells across a gap between windows, where they are undefined."""
    for label, first, last in baseline_windows():
        if first <= day <= last:
            return label
    return None
