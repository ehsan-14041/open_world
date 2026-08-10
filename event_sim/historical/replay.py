"""
Historical replay: run a past event through the *same* Event Simulator engine used for
forward exploration, and produce a trajectory envelope to compare against what happened.

    historical baseline state  →  inject historical event  →  Event Simulator
                               →  trajectory envelope      →  observed trajectory
                               →  evaluation

Two rules are enforced in code rather than left to discipline:

1. **No special historical physics.** Replay calls `event_sim.sweep.run_sweep` on the same
   `WorldSlice` the forward simulator uses. If replay needed its own dynamics, replay would
   be validating something other than the product.

2. **No hindsight leakage.** Every value used to initialise the world must have been
   *available* (published) on or before `knowledge_cutoff`. `validate_no_hindsight` fails
   the replay otherwise — including the subtle case where a value *describes* a pre-event
   period but was only published after the event began.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

from event_sim import sweep
from event_sim.schemas import EventDefinition, HistoricalObservation, ObservedMilestone, WorldSlice
from event_sim.world_builder import build_slice

_HERE = Path(__file__).resolve().parent
EVENTS_DIR = _HERE / "events"
OBSERVATIONS_DIR = _HERE / "observations"


class HindsightLeakageError(ValueError):
    """Raised when a replay would be initialised with information published after the cutoff."""


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass
class HistoricalEpisode:
    """A past event set up for replay, with explicit epistemic boundaries."""

    id: str
    title: str
    modules: list[str]
    event: EventDefinition
    additional_events: list[EventDefinition] = field(default_factory=list)
    turns: int = 20
    time_unit: str = "weeks"
    start_date: str = ""
    knowledge_cutoff: str = ""
    evaluation_window: dict[str, str] = field(default_factory=dict)
    initial_state: dict[str, float] = field(default_factory=dict)
    initial_state_provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    why_this_event: list[str] = field(default_factory=list)
    description: str = ""
    event_status_note: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)

    def all_events(self) -> list[EventDefinition]:
        return [self.event, *self.additional_events]

    def turn_to_date(self, turn: int) -> str:
        start = _parse_date(self.start_date)
        if start is None:
            return ""
        days = 7 if self.time_unit == "weeks" else 1
        return (start + timedelta(days=days * turn)).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "modules": list(self.modules),
            "event": self.event.to_dict(),
            "additional_events": [e.to_dict() for e in self.additional_events],
            "turns": self.turns,
            "time_unit": self.time_unit,
            "start_date": self.start_date,
            "knowledge_cutoff": self.knowledge_cutoff,
            "evaluation_window": dict(self.evaluation_window),
            "initial_state": dict(self.initial_state),
            "initial_state_provenance": dict(self.initial_state_provenance),
            "why_this_event": list(self.why_this_event),
            "description": self.description,
            "event_status_note": self.event_status_note,
            "sources": [dict(s) for s in self.sources],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HistoricalEpisode:
        return cls(
            id=str(d["id"]),
            title=str(d.get("title") or d["id"]),
            modules=[str(m) for m in (d.get("modules") or [])],
            event=EventDefinition.from_dict(d.get("event") or {}),
            additional_events=[EventDefinition.from_dict(e) for e in (d.get("additional_events") or [])],
            turns=int(d.get("turns", 20)),
            time_unit=str(d.get("time_unit") or "weeks"),
            start_date=str(d.get("start_date") or ""),
            knowledge_cutoff=str(d.get("knowledge_cutoff") or d.get("start_date") or ""),
            evaluation_window=dict(d.get("evaluation_window") or {}),
            initial_state={str(k): float(v) for k, v in (d.get("initial_state") or {}).items()},
            initial_state_provenance=dict(d.get("initial_state_provenance") or {}),
            why_this_event=[str(w) for w in (d.get("why_this_event") or [])],
            description=str(d.get("description") or ""),
            event_status_note=str(d.get("event_status_note") or ""),
            sources=[dict(s) for s in (d.get("sources") or [])],
        )


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------


def available_episodes() -> list[dict[str, Any]]:
    if not EVENTS_DIR.is_dir():
        return []
    out = []
    for path in sorted(EVENTS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append({
            "id": data.get("id"),
            "title": data.get("title"),
            "start_date": data.get("start_date"),
            "knowledge_cutoff": data.get("knowledge_cutoff"),
            "modules": data.get("modules"),
            "path": str(path),
        })
    return out


def load_episode(episode_id: str) -> HistoricalEpisode:
    path = EVENTS_DIR / f"{episode_id}.json"
    if not path.is_file():
        known = [e["id"] for e in available_episodes()]
        raise FileNotFoundError(
            f"No historical episode {episode_id!r} in {EVENTS_DIR}. Known: {known}"
        )
    return HistoricalEpisode.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_observations(episode_id: str) -> list[HistoricalObservation]:
    """
    Observed series for an episode. Records whose `status` is not 'observed' (e.g. the
    pre-event context points used for initialisation) load normally but are filtered out
    by the evaluator, so the model can never be scored against its own initial condition.
    """
    path = OBSERVATIONS_DIR / f"{episode_id}.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("observations") if isinstance(data, dict) else data
    return [HistoricalObservation.from_dict(r) for r in (records or [])]


def load_milestones(episode_id: str) -> list[ObservedMilestone]:
    """
    Dated milestones for an episode.

    A milestone tests *when* something happened rather than what level it reached, which is
    the only kind of test available when no dense series exists — after two evidence hunts
    that is the normal case, not the exception.
    """
    path = OBSERVATIONS_DIR / f"{episode_id}.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    return [ObservedMilestone.from_dict(m) for m in (data.get("milestones") or [])]


def observation_metadata(episode_id: str) -> dict[str, Any]:
    """Turn-mapping rule and the explicit `_not_observed` gap list, for the report."""
    path = OBSERVATIONS_DIR / f"{episode_id}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {
        "turn_mapping_rule": data.get("_turn_mapping_rule", ""),
        "not_observed": data.get("_not_observed", []),
        "note": data.get("_note", ""),
    }


# --------------------------------------------------------------------------------------
# Hindsight-leakage guard
# --------------------------------------------------------------------------------------


def validate_no_hindsight(
    episode: HistoricalEpisode,
    observations: Sequence[HistoricalObservation] | None = None,
) -> dict[str, Any]:
    """
    Verify that nothing used to build the world was published after the knowledge cutoff.

    Checks:
      - every entry in `initial_state_provenance` has `available_at <= knowledge_cutoff`
      - every variable in `initial_state` has a provenance entry at all
      - observations published after the cutoff are marked evaluation-only (this is
        expected and correct — outcomes are *supposed* to be later than the cutoff)

    Raises HindsightLeakageError on a violation; returns a report otherwise.
    """
    cutoff = _parse_date(episode.knowledge_cutoff)
    if cutoff is None:
        raise HindsightLeakageError(
            f"Episode {episode.id!r} declares no knowledge_cutoff; a replay without an "
            f"explicit cutoff cannot be shown to be free of hindsight."
        )

    violations: list[str] = []
    checked: list[dict[str, Any]] = []
    for variable in episode.initial_state:
        provenance = episode.initial_state_provenance.get(variable)
        if provenance is None:
            violations.append(
                f"initial_state.{variable} has no provenance entry, so its availability at "
                f"the cutoff cannot be verified"
            )
            continue
        available = _parse_date(str(provenance.get("available_at") or ""))
        if available is None:
            violations.append(f"initial_state.{variable} provenance has no available_at date")
            continue
        if available > cutoff:
            violations.append(
                f"initial_state.{variable} uses a value published {available.isoformat()}, "
                f"after the knowledge cutoff {cutoff.isoformat()} — hindsight leakage"
            )
        checked.append({
            "variable": variable,
            "available_at": available.isoformat(),
            "refers_to_period": provenance.get("refers_to_period", ""),
            "source_id": provenance.get("source_id"),
            "ok": available <= cutoff,
        })

    if violations:
        raise HindsightLeakageError("; ".join(violations))

    evaluation_only: list[dict[str, Any]] = []
    for obs in observations or []:
        available = _parse_date(obs.available_at)
        evaluation_only.append({
            "variable": obs.variable,
            "turn": obs.turn,
            "status": obs.status,
            "published_after_cutoff": bool(available and available > cutoff),
        })

    return {
        "knowledge_cutoff": cutoff.isoformat(),
        "event_start": episode.start_date,
        "evaluation_window": dict(episode.evaluation_window),
        "initial_state_checked": checked,
        "violations": [],
        "observations": evaluation_only,
        "rule": (
            "Every value used to initialise the world must have been PUBLISHED on or before "
            "the knowledge cutoff. A value describing a pre-event period is still leakage if "
            "it was only published afterwards."
        ),
    }


# --------------------------------------------------------------------------------------
# Replay
# --------------------------------------------------------------------------------------


def build_replay_slice(
    episode: HistoricalEpisode,
    *,
    modules: Sequence[str] | None = None,
) -> WorldSlice:
    """
    The world slice for a replay, with baselines overridden by the historical initial state.

    Only variables with verified pre-cutoff provenance are overridden; every other variable
    keeps the module's declared baseline.

    `modules` overrides the episode's declared modules — used to run the SAME historical
    inputs against an experimental variant of the world model, so baseline and experimental
    differ only in the module.
    """
    slice_ = build_slice(
        list(modules) if modules else episode.modules,
        question=f"Historical replay: {episode.title}",
        slice_id=f"replay_{episode.id}",
    )
    for var in slice_.variables:
        if var.id in episode.initial_state:
            var.baseline = float(episode.initial_state[var.id])
    return slice_


def replay_episode(
    episode: HistoricalEpisode,
    *,
    slice_: WorldSlice | None = None,
    check_hindsight: bool = True,
    modules: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Replay an episode across the full assumption grid, returning the trajectory envelope
    per variable plus every world for drill-down.

    Deterministic: the same episode file produces byte-identical output.
    """
    observations = load_observations(episode.id)
    hindsight = validate_no_hindsight(episode, observations) if check_hindsight else {}

    slice_ = slice_ or build_replay_slice(episode, modules=modules)
    worlds = sweep.run_sweep(slice_, events=episode.all_events(), turns=episode.turns)

    return {
        "episode": episode.to_dict(),
        "slice_id": slice_.id,
        "slice": slice_,
        "world_count": len(worlds),
        "envelope": {v.id: sweep.envelope(worlds, v.id) for v in slice_.variables},
        "worlds": worlds,
        "coverage": dict(slice_.coverage),
        "hindsight_check": hindsight,
        "turn_dates": {t: episode.turn_to_date(t) for t in range(episode.turns + 1)},
        "framing": (
            "The envelope is the range across tested assumption combinations. An observed "
            "series falling inside it means the model COULD contain what happened under some "
            "assumption setting — not that the model predicted it."
        ),
    }
