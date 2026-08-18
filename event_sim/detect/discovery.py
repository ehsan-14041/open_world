"""
Event #3 sequential discovery — chronological blocks over the unseen search universe.

Detector development is finished. Detector v3 is frozen and this module does not touch it: it
only decides *which unseen days to look at, in what order*, and applies pre-registered rules
for recovery and for stopping.

The design is a sequential stopping rule. Blocks are processed strictly in chronological
order; each block is acquired, run through the frozen detector, its triggers frozen, then
researched. Only if nothing qualifies is the next block acquired. The first chronologically
encountered candidate that satisfies the frozen eligibility contract ends the search.

That ordering is the whole anti-shopping mechanism. Nothing here may consult, rank, or prefer
a period because something is remembered to have happened in it — this module contains no
event names and no notion of an interesting date, and a test asserts it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from event_sim.detect.detector_v2 import LOOKBACK_DAYS
from event_sim.detect.sampling import baseline_days, blind_days, v3_blind_days

# ---------------------------------------------------------------------------------------
# Search universe
# ---------------------------------------------------------------------------------------

#: The frozen geometry (33 CFR 110.168 @ 2022-01-01) takes effect between 2020-04-01 and
#: 2020-07-01 and is unchanged through 2026-01-01. Days before this cannot be measured with
#: the frozen instrument, so they are outside the universe by definition rather than by
#: preference.
GEOMETRY_ERA_START = "2020-07-01"

#: National AIS daily coverage, established by probing the publisher's own directory listings
#: and the artifacts themselves:
#:   * 2023 complete,
#:   * 2024-01-01 .. 2024-06-30 listed but every artifact returns 404,
#:   * 2024-07-01 .. 2024-12-31 present,
#:   * 2025 onwards: no directory at all.
AIS_UNAVAILABLE_SPANS = (("2024-01-01", "2024-06-30"),)
AIS_LAST_AVAILABLE_DAY = "2024-12-31"

#: Minimum contiguous run that can host a block: warmup plus at least this many discovery
#: days. A shorter run cannot be processed identically to the others and is excluded rather
#: than handled as a special case.
MIN_DISCOVERY_DAYS = 45

#: Discovery days per full block.
BLOCK_DISCOVERY_DAYS = 90

#: Warmup days preceding a span's first discovery day. Equal to the detector's lookback, so
#: the first discovery day of a span has a fully populated trailing baseline. For later blocks
#: inside the same span the warmup is the previous block's tail, already acquired — see
#: `Block.warmup_days`.
BLOCK_WARMUP_DAYS = LOOKBACK_DAYS

#: Pre-registered ceiling on the search. The universe turns out to be smaller than this, but
#: the bound is declared anyway so that the search cannot be extended post-hoc if it is not.
MAX_DISCOVERY_BLOCKS = 8

# ---------------------------------------------------------------------------------------
# Recovery, declared before any discovery day was acquired
# ---------------------------------------------------------------------------------------

#: Occupancy residual at or below this is "back in the local normal band".
RECOVERY_RESIDUAL_BAND = 1.0

#: Consecutive days required inside the band, after the trigger window ends, for recovery to
#: count as observed. Longer than the 4-day persistence rule, so a brief dip mid-event cannot
#: be mistaken for recovery.
RECOVERY_DAYS = 7

#: If recovery is not observable before the acquired data ends, extend forward in fixed
#: increments rather than by an amount chosen after seeing the trajectory.
EXTENSION_INCREMENT_DAYS = 14
MAX_EXTENSION_DAYS = 56


def _spent_days() -> set[str]:
    """Every day already used for development or validation. None may be a discovery day."""
    return set(baseline_days()) | set(blind_days()) | set(v3_blind_days())


def _unavailable(day: str) -> bool:
    if day > AIS_LAST_AVAILABLE_DAY:
        return True
    return any(lo <= day <= hi for lo, hi in AIS_UNAVAILABLE_SPANS)


def eligible_days() -> list[str]:
    """Every day in the universe: measurable, available, and not previously seen."""
    out: list[str] = []
    d = date.fromisoformat(GEOMETRY_ERA_START)
    last = date.fromisoformat(AIS_LAST_AVAILABLE_DAY)
    spent = _spent_days()
    while d <= last:
        s = d.isoformat()
        if s not in spent and not _unavailable(s):
            out.append(s)
        d += timedelta(days=1)
    return out


def eligible_spans() -> list[tuple[str, str]]:
    """Maximal contiguous runs of eligible days, long enough to host a block."""
    days = eligible_days()
    spans: list[tuple[str, str]] = []
    if not days:
        return spans

    run_start = prev = days[0]
    for day in days[1:]:
        if date.fromisoformat(day) - date.fromisoformat(prev) == timedelta(days=1):
            prev = day
            continue
        spans.append((run_start, prev))
        run_start = prev = day
    spans.append((run_start, prev))

    need = BLOCK_WARMUP_DAYS + MIN_DISCOVERY_DAYS
    return [
        (a, b)
        for a, b in spans
        if (date.fromisoformat(b) - date.fromisoformat(a)).days + 1 >= need
    ]


@dataclass(frozen=True)
class Block:
    index: int
    span: tuple[str, str]
    discovery_start: str
    discovery_end: str
    warmup_start: str
    warmup_end: str

    @property
    def discovery_days(self) -> list[str]:
        return _range(self.discovery_start, self.discovery_end)

    @property
    def warmup_days(self) -> list[str]:
        return _range(self.warmup_start, self.warmup_end)

    @property
    def all_days(self) -> list[str]:
        return self.warmup_days + self.discovery_days


def _range(a: str, b: str) -> list[str]:
    start, end = date.fromisoformat(a), date.fromisoformat(b)
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def discovery_blocks() -> list[Block]:
    """All blocks, in strict chronological order. A pure function of the calendar.

    Boundary continuity: every block's first discovery day is preceded by 14 acquired days.
    For the first block in a span those are dedicated warmup; for later blocks they are the
    previous block's own tail, so the trailing baseline is never reset at a boundary and a
    trigger cannot appear merely because a block started.
    """
    blocks: list[Block] = []
    for span_start, span_end in eligible_spans():
        warmup_start = span_start
        warmup_end = (
            date.fromisoformat(span_start) + timedelta(days=BLOCK_WARMUP_DAYS - 1)
        ).isoformat()
        cursor = (date.fromisoformat(warmup_end) + timedelta(days=1)).isoformat()

        while cursor <= span_end:
            remaining = (date.fromisoformat(span_end) - date.fromisoformat(cursor)).days + 1
            if remaining < MIN_DISCOVERY_DAYS:
                break
            length = min(BLOCK_DISCOVERY_DAYS, remaining)
            d_end = (
                date.fromisoformat(cursor) + timedelta(days=length - 1)
            ).isoformat()
            blocks.append(
                Block(
                    index=len(blocks) + 1,
                    span=(span_start, span_end),
                    discovery_start=cursor,
                    discovery_end=d_end,
                    warmup_start=warmup_start,
                    warmup_end=warmup_end,
                )
            )
            # Next block's warmup is this block's tail — already acquired, no reset.
            warmup_start = (
                date.fromisoformat(d_end) - timedelta(days=BLOCK_WARMUP_DAYS - 1)
            ).isoformat()
            warmup_end = d_end
            cursor = (date.fromisoformat(d_end) + timedelta(days=1)).isoformat()

    return blocks[:MAX_DISCOVERY_BLOCKS]


def find_recovery(
    dates: Sequence[str], residuals: Sequence[float | None], window_end: str
) -> str | None:
    """First day on which recovery completes, or None if not observable in this data.

    Recovery = the occupancy residual sits at or below `RECOVERY_RESIDUAL_BAND` for
    `RECOVERY_DAYS` consecutive days, all strictly after the trigger window ends. Returns the
    last day of that run — the point at which recovery has been *demonstrated*, not the point
    at which it began.
    """
    run = 0
    for day, resid in zip(dates, residuals):
        if day <= window_end:
            continue
        if resid is None:
            run = 0
            continue
        if resid <= RECOVERY_RESIDUAL_BAND:
            run += 1
            if run >= RECOVERY_DAYS:
                return day
        else:
            run = 0
    return None
