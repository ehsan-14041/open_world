"""
First vertical slice: "What happens if a major container port loses 70% capacity for six weeks?"

End to end, with no LLM anywhere in the path:

    world slice  →  event injection  →  time evolution  →  causal trace
                 →  branch (intervention)  →  branch comparison
                 →  assumption sweep  →  emergent trajectories  →  pivotal assumptions

Everything below is a thin wiring layer; the semantics live in event_sim/engine.py,
event_sim/sweep.py, event_sim/causal_trace.py and event_sim/comparison.py.
"""

from __future__ import annotations

from typing import Any

from event_sim import causal_trace, comparison, sweep
from event_sim.engine import EventSimulation, Intervention, SimulationConfig, build_simulation
from event_sim.schemas import EventDefinition, WorldSlice
from event_sim.world_builder import build_slice, describe_slice

QUESTION = "What happens if a major container port loses 70% of capacity for six weeks?"

# 20 weeks: long enough for the trough (which lands well after the port itself recovers)
# and the start of recovery to both be visible in the window.
DEFAULT_TURNS = 20
DEFAULT_CAPACITY_LOSS = -70.0
DEFAULT_DURATION = 6
OUTCOME_VARIABLE = "service_level"


def build_world_slice(question: str = QUESTION) -> WorldSlice:
    """The world slice for this event: supply-chain module only, everything else excluded."""
    return build_slice(["port_disruption"], question=question, slice_id="port_disruption_slice")


def build_event(
    *,
    capacity_loss: float = DEFAULT_CAPACITY_LOSS,
    duration: int = DEFAULT_DURATION,
    start_turn: int = 1,
) -> EventDefinition:
    """
    The injected shock. Status is `user_assumption`: the event is a premise the user chose
    to explore, not an observation, and it is labelled as such everywhere it appears.
    """
    return EventDefinition(
        id="port_capacity_loss",
        label=f"Port capacity {capacity_loss:+.0f} index points for {duration} weeks",
        description=(
            "A major container port loses a large share of weekly throughput (strike, "
            "casualty, closure or infrastructure failure) and recovers afterwards."
        ),
        targets={"port_capacity": capacity_loss},
        start_turn=start_turn,
        duration=duration,
        shape="step",
        status="user_assumption",
    )


def build_baseline(
    slice_: WorldSlice | None = None,
    *,
    turns: int = DEFAULT_TURNS,
    capacity_loss: float = DEFAULT_CAPACITY_LOSS,
    duration: int = DEFAULT_DURATION,
    axis_settings: dict[str, str] | None = None,
    seed: int = 0,
) -> EventSimulation:
    """Baseline world: the event, no intervention, central assumptions."""
    slice_ = slice_ or build_world_slice()
    config = SimulationConfig(
        turns=turns,
        axis_settings=dict(axis_settings or {}),
        label="World A — no intervention",
        seed=seed,
    )
    return build_simulation(
        slice_,
        config=config,
        events=[build_event(capacity_loss=capacity_loss, duration=duration)],
    )


def redirect_cargo_intervention(
    slice_: WorldSlice,
    *,
    share: float = 0.3,
    start_turn: int = 3,
    duration: int = 8,
) -> Intervention:
    """The one intervention in this slice: redirect a share of cargo to another port."""
    return Intervention.from_slice(
        slice_,
        "redirect_cargo",
        magnitude=share,
        start_turn=start_turn,
        duration=duration,
    )


def run_vertical_slice(
    *,
    turns: int = DEFAULT_TURNS,
    capacity_loss: float = DEFAULT_CAPACITY_LOSS,
    duration: int = DEFAULT_DURATION,
    fork_turn: int = 2,
    redirect_share: float = 0.3,
    redirect_start: int = 3,
    redirect_duration: int | None = None,
    include_sweep: bool = True,
    seed: int = 0,
) -> dict[str, Any]:
    """
    Run the whole vertical slice and return one payload for the API, the CLI demo and the
    tests. Deterministic: same arguments in, identical payload out.
    """
    slice_ = build_world_slice()

    # 1. Baseline world, run to the fork point, checkpointed each turn.
    world_a = build_baseline(
        slice_, turns=turns, capacity_loss=capacity_loss, duration=duration, seed=seed
    )
    world_a.run(turns=fork_turn)

    # 2. Branch from that exact checkpoint; World B adds the intervention, nothing else.
    world_b = world_a.fork(
        fork_turn,
        branch_id="world_b",
        label="World B — redirect 30% of cargo",
        interventions=[
            # Rerouting is an operational choice with an end: it covers the disruption plus
            # a short tail, then stops. Running it to the horizon would leave effective
            # throughput permanently above normal, which the model does not support.
            redirect_cargo_intervention(
                slice_,
                share=redirect_share,
                start_turn=redirect_start,
                duration=(redirect_duration if redirect_duration is not None
                          else max(1, duration + 4)),
            )
        ],
    )
    world_b.config.label = f"World B — redirect {redirect_share:.0%} of cargo"

    # 3. Both worlds run forward independently from identical state.
    result_a = world_a.run()
    result_b = world_b.run()

    diff = comparison.compare(world_a, world_b)

    # 4. Causal trace for the headline outcome, read from recorded provenance.
    trace = causal_trace.explain(world_a, OUTCOME_VARIABLE, world_a.world.turn)

    payload: dict[str, Any] = {
        "question": QUESTION,
        "slice": describe_slice(slice_),
        "event": build_event(capacity_loss=capacity_loss, duration=duration).to_dict(),
        "worlds": {"world_a": result_a, "world_b": result_b},
        "comparison": diff,
        "comparison_summary": comparison.summarize(diff),
        "causal_trace": trace,
        "causal_trace_text": causal_trace.render_text(trace),
        "dominant_path": causal_trace.dominant_path(world_a, OUTCOME_VARIABLE, world_a.world.turn),
        "coverage": dict(slice_.coverage),
        "framing": (
            "An executable world model, not a forecast. Every number below follows from the "
            "stated assumptions and the causal edges shown; change an assumption and the "
            "trajectory changes."
        ),
    }

    if include_sweep:
        worlds = sweep.run_sweep(
            slice_,
            events=[build_event(capacity_loss=capacity_loss, duration=duration)],
            turns=turns,
            seed=seed,
        )
        trajectories = sweep.group_trajectories(worlds, sweep.port_disruption_rules(slice_))
        payload["sweep"] = {
            "world_count": len(worlds),
            "axes": [a.to_dict() for a in slice_.axes],
            "trajectories": [t.to_dict() for t in trajectories],
            "pivotal_assumptions": sweep.pivotal_assumptions(
                worlds, outcome_variable=OUTCOME_VARIABLE, trajectories=trajectories
            ),
            "envelope": {
                vid: sweep.envelope(worlds, vid)
                for vid in ("service_level", "shipping_delay", "freight_cost", "inventory_availability")
            },
            "framing": (
                f"{len(worlds)} worlds were tested — one per combination of assumption "
                "settings. Counts are counts of tested worlds, not probabilities."
            ),
        }

    return payload
