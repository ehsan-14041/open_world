"""
Event Simulator HTTP surface — a Flask blueprint, registered separately from the
Enterprise Operations Decision Simulator.

Deliberately small. The demo exists to show that this is an executable world model, not to
be a polished product: the simulation semantics are the deliverable, the UI is evidence
that they work.

Routes:
    GET  /event-sim                        demo page
    GET  /api/event_sim/modules            world module library
    GET  /api/event_sim/slice              the world slice: in / out / assumptions / evidence
    POST /api/event_sim/run                run the vertical slice (branches + comparison + sweep)
    POST /api/event_sim/trace              causal trace for one variable at one turn
    GET  /api/event_sim/historical         historical replay episodes available
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, render_template, request

from event_sim import causal_trace
from event_sim.registry import available_modules
from event_sim.scenarios import port_disruption
from event_sim.world_builder import describe_slice

bp = Blueprint("event_sim", __name__)

#: Bound so a stray request cannot ask for a 10,000-week sweep.
MAX_TURNS = 60


def _clean(obj: Any) -> Any:
    """Replace non-finite floats with None so jsonify never fails (matches ui.py)."""
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


@bp.route("/event-sim")
def event_sim_page():
    """Minimal demo page for the port-disruption vertical slice."""
    return render_template("event_sim.html")


@bp.route("/api/event_sim/modules", methods=["GET"])
def api_modules():
    return jsonify({"ok": True, "modules": available_modules()})


@bp.route("/api/event_sim/slice", methods=["GET"])
def api_slice():
    slice_ = port_disruption.build_world_slice()
    return jsonify({"ok": True, "slice": _clean(describe_slice(slice_))})


@bp.route("/api/event_sim/run", methods=["POST"])
def api_run():
    """
    Run the port-disruption vertical slice. Body (all optional):
      turns, capacity_loss, duration, fork_turn, redirect_share, redirect_start,
      include_sweep, seed
    """
    data = request.get_json(silent=True) or {}
    try:
        turns = min(MAX_TURNS, max(2, int(data.get("turns", port_disruption.DEFAULT_TURNS))))
        duration = max(1, int(data.get("duration", port_disruption.DEFAULT_DURATION)))
        fork_turn = max(0, min(turns - 1, int(data.get("fork_turn", 2))))
        payload = port_disruption.run_vertical_slice(
            turns=turns,
            capacity_loss=float(data.get("capacity_loss", port_disruption.DEFAULT_CAPACITY_LOSS)),
            duration=duration,
            fork_turn=fork_turn,
            redirect_share=float(data.get("redirect_share", 0.3)),
            redirect_start=max(1, int(data.get("redirect_start", 3))),
            include_sweep=bool(data.get("include_sweep", True)),
            seed=int(data.get("seed", 0)),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": f"Invalid request: {exc}"}), 400
    return jsonify({"ok": True, "result": _clean(payload)})


@bp.route("/api/event_sim/trace", methods=["POST"])
def api_trace():
    """
    Causal trace for one variable at one turn, rebuilt deterministically from a fresh run
    of the same configuration (runs are reproducible, so this is the same world).
    Body: {variable, turn, world: 'a'|'b', turns, capacity_loss, duration, ...}
    """
    data = request.get_json(silent=True) or {}
    variable = str(data.get("variable") or port_disruption.OUTCOME_VARIABLE)
    try:
        turns = min(MAX_TURNS, max(2, int(data.get("turns", port_disruption.DEFAULT_TURNS))))
        turn = max(0, min(turns, int(data.get("turn", turns))))
        sim = port_disruption.build_baseline(
            turns=turns,
            capacity_loss=float(data.get("capacity_loss", port_disruption.DEFAULT_CAPACITY_LOSS)),
            duration=max(1, int(data.get("duration", port_disruption.DEFAULT_DURATION))),
            seed=int(data.get("seed", 0)),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": f"Invalid request: {exc}"}), 400

    if sim.slice.variable(variable) is None:
        return jsonify({
            "ok": False,
            "error": f"Unknown variable {variable!r}",
            "available": [v.id for v in sim.slice.variables],
        }), 400

    sim.run()
    trace = causal_trace.explain(sim, variable, turn)
    return jsonify({
        "ok": True,
        "trace": _clean(trace),
        "text": causal_trace.render_text(trace),
        "dominant_path": _clean(causal_trace.dominant_path(sim, variable, turn)),
    })


@bp.route("/api/event_sim/evidence", methods=["GET"])
def api_evidence():
    """
    Evidence state of the port-disruption model: registered sources, proxy mappings,
    influence-weighted coverage, and the high-influence / low-evidence gap report.
    """
    from event_sim import sweep
    from event_sim.evidence import (
        all_mappings,
        data_requirements,
        evidence_gap_report,
        source_summary,
        validate_slice_provenance,
        weighted_coverage,
    )
    from event_sim.evidence.coverage import merge_influence

    from event_sim.historical import (
        evaluate_replay,
        load_episode,
        load_milestones,
        load_observations,
        milestone_evaluation,
        replay_episode,
    )
    from event_sim.historical.replay import available_episodes
    from event_sim.model_health import model_health

    slice_ = port_disruption.build_world_slice()
    worlds = sweep.run_sweep(
        slice_, events=[port_disruption.build_event()], turns=port_disruption.DEFAULT_TURNS
    )
    pivotal = sweep.pivotal_assumptions(worlds, outcome_variable=port_disruption.OUTCOME_VARIABLE)
    gaps = evidence_gap_report(slice_, pivotal=pivotal)

    # Model Health folds in every historical replay we have run, so the panel reports
    # whether the model actually held up — not only how much evidence it carries.
    replays: list[dict[str, Any]] = []
    for summary in available_episodes():
        episode = load_episode(str(summary["id"]))
        replay = replay_episode(episode)
        observations = load_observations(episode.id)
        try:
            evaluation = evaluate_replay(replay, observations)
        except Exception:
            evaluation = {}
        replays.append({
            "episode": episode.id,
            "evaluation": evaluation,
            "milestones": milestone_evaluation(replay, load_milestones(episode.id)),
        })

    return jsonify({
        "ok": True,
        "sources": source_summary(),
        "mappings": [m.to_dict() for m in all_mappings()],
        "coverage": _clean(weighted_coverage(slice_.edges, merge_influence(slice_, pivotal))),
        "gaps": _clean(gaps),
        "data_requirements": _clean(data_requirements(gaps, slice_)),
        "provenance_errors": validate_slice_provenance(slice_.edges),
        "model_health": _clean(model_health(
            slice_, pivotal=pivotal, gap_report=gaps, replays=replays
        )),
        "experimental_mechanisms": _clean(experimental_mechanism_summary()),
        "measurement_risks": _clean(measurement_risk_summary()),
        "protocol_lessons": _clean(protocol_lesson_summary()),
        "heldout_status": _clean(heldout_status()),
    })


@bp.route("/api/event_sim/historical", methods=["GET"])
def api_historical():
    from event_sim.historical.replay import available_episodes

    episodes = available_episodes()
    return jsonify({
        "ok": True,
        "episodes": episodes,
        "note": (
            "Historical replay is architecturally supported but no episode has been added: "
            "no historical series was invented to populate it. See "
            "event_sim/historical/events/README.md."
        ) if not episodes else "",
    })


@bp.route("/api/event_sim/replay/<episode_id>", methods=["GET"])
def api_replay(episode_id: str):
    """
    Run a historical replay and return its evaluation. Deterministic and reproducible;
    the same payload the CLI prints.
    """
    from event_sim.historical import (
        HindsightLeakageError,
        InsufficientObservationsError,
        evaluate_replay,
        load_episode,
        load_observations,
        replay_episode,
    )

    try:
        episode = load_episode(episode_id)
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404

    observations = load_observations(episode_id)
    try:
        replay = replay_episode(episode)
    except HindsightLeakageError as exc:
        return jsonify({"ok": False, "error": f"Hindsight leakage: {exc}"}), 400

    payload: dict[str, Any] = {
        "ok": True,
        "episode": episode.to_dict(),
        "hindsight_check": _clean(replay["hindsight_check"]),
        "envelope": _clean(replay["envelope"]),
        "world_count": replay["world_count"],
        "observations": [o.to_dict() for o in observations],
    }
    try:
        payload["evaluation"] = _clean(evaluate_replay(replay, observations))
    except InsufficientObservationsError as exc:
        payload["evaluation"] = None
        payload["evaluation_error"] = str(exc)
    return jsonify(payload)


def experimental_mechanism_summary() -> list[dict[str, Any]]:
    """
    Structural hypotheses that have been implemented as experimental modules, and what the
    replay experiment concluded. Deliberately verbose about what is NOT established.
    """
    from event_sim.cross_event import STRUCTURAL_HYPOTHESES
    from event_sim.registry import available_modules

    experimental_modules = {
        m["id"] for m in available_modules() if m["id"].endswith("_experimental")
    }
    out: list[dict[str, Any]] = []
    for hypothesis in STRUCTURAL_HYPOTHESES:
        if not hypothesis["status"].startswith("experimental"):
            continue
        out.append({
            "hypothesis": hypothesis["id"],
            "name": hypothesis["name"],
            "mechanism_evidence": "independently supported (mechanism test, no simulation)",
            "implemented_as": sorted(experimental_modules),
            "experiment_result": hypothesis["status"],
            "historical_validation": "NOT YET — held-out event required",
            "default_model_changed": False,
        })
    return out


def heldout_status() -> dict[str, Any]:
    """
    Where held-out validation stands. Deliberately explicit that n is tiny and that nothing
    here is a generalisation claim.
    """
    from event_sim.cross_event import MIN_EVENTS_FOR_HELD_OUT
    from event_sim.historical.replay import available_episodes

    episodes = [str(e["id"]) for e in available_episodes()]
    return {
        "events_available": episodes,
        "events_required_for_held_out": MIN_EVENTS_FOR_HELD_OUT,
        "held_out_event": None,
        "status": "blocked — no qualifying independent event retrievable",
        "reason": (
            "Qualifying local queue/waiting-time series are either commercial or, though free "
            "and official, unreachable from this environment. See "
            "docs/replays/EVENT3_SEARCH_V2.md and EVENT3_DATA_DECISION.md."
        ),
        "claim_ceiling": (
            "With no held-out event, H1 cannot be described as validated or generalised. Even "
            "a future success on one event would only support 'H1 generalised to one "
            "independent disruption' — never 'H1 is validated'."
        ),
    }


def measurement_risk_summary() -> list[dict[str, Any]]:
    from event_sim.evidence.measurement_risk import registry_summary

    return registry_summary()


def protocol_lesson_summary() -> list[dict[str, Any]]:
    from event_sim.protocol_lessons import registry_summary

    return registry_summary()


def register_routes(app: Any) -> None:
    """Attach the Event Simulator surface to a Flask app."""
    app.register_blueprint(bp)
