#!/usr/bin/env python3
"""
Open World Engine – Web UI.
Serves a simple interface to submit free-text scenarios, run simulations, and view snapshots.
Run: python ui.py [--port 5000]
"""

from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import traceback
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from flask import Flask, jsonify, render_template, request, Response, stream_with_context

from scenario_parser import parse_scenario_text


def _make_json_safe(obj: object) -> object:
    """Replace float('nan')/inf with None so jsonify never fails."""
    if obj is None:
        return None
    if isinstance(obj, float):
        if obj != obj or obj == float("inf") or obj == float("-inf"):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    return obj


from schemas.scenario_schema import validate_scenario, normalize_scenario
from simulation.loop import SimulationLoop
from core.narrative_builder import build_narrative, trace_from_snapshot
from core.llm_client import get_llm_logs, clear_llm_logs, call_llm
from core.scenario_analysis_output import build_scenario_analysis_output, build_strategic_analysis
from summarization.facts import build_narrative_facts
from core.agent_generator import generate_agents_from_scenario  # LLM Integration: scenario-to-simulation pipeline
from visualization.graph_viewer import prepare_graph_data
from visualization.impact_data import prepare_impact_data
from ui.dashboard import register_routes as register_dashboard_routes
from ui.dashboard import build_dashboard_payload, on_turn_complete as dashboard_on_turn_complete

app = Flask(__name__, template_folder=str(_PROJECT_ROOT / "templates"), static_folder=str(_PROJECT_ROOT / "static"))
register_dashboard_routes(app)


@app.errorhandler(500)
def handle_500(e):
    """Ensure 500 responses are always JSON so frontend never gets empty/invalid body."""
    return jsonify({"ok": False, "error": str(e) if e else "Internal server error", "final": None, "turns": None}), 500

# Store last run result in memory for "View Snapshot" and narrative
_last_scenario: dict | None = None
_last_run_result: dict | None = None  # {"final": ..., "turns": [...], "provenance": [...]} or {"error": "..."}
_last_snapshot_path: str | None = None
# Run ID: only the most recent run's result is shown (avoids scenario 1 overwriting scenario 2 when runs finish out of order)
_current_run_id: int = 0


def _get_snapshot_dir() -> Path:
    d = _PROJECT_ROOT / "data" / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    """Health check for load balancer / reverse proxy. Returns 200 when app is up."""
    return jsonify({"status": "ok", "service": "open_world_engine"}), 200


@app.route("/api/submit_scenario", methods=["POST"])
def api_submit_scenario():
    """Parse free-text scenario to JSON. Body: { "text": "...", "use_llm": true }."""
    global _last_scenario
    try:
        data = request.get_json(force=True, silent=True)
        if data is None or not isinstance(data, dict):
            return jsonify({
                "ok": False,
                "error": "Request body must be a JSON object with a 'text' field (e.g. {\"text\": \"your scenario\"}).",
                "scenario": None,
            }), 400
        text = (data.get("text") or "").strip()
        use_llm = data.get("use_llm", True)
        use_llm_for_agents = data.get("use_llm_for_agents", False)

        if not text:
            return jsonify({"ok": False, "error": "Scenario text is required. Provide a non-empty 'text' field.", "scenario": None}), 400

        try:
            scenario = parse_scenario_text(text, use_llm=use_llm)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e), "scenario": None}), 400

        errors = validate_scenario(scenario)
        if errors:
            return jsonify({"ok": False, "error": "; ".join(errors), "scenario": None}), 400

        scenario = normalize_scenario(scenario)
        # LLM Integration: optionally generate agent definitions (personality, initial_variables) from scenario
        if use_llm_for_agents and use_llm:
            try:
                def llm_wrapper(prompt: str, system: str | None = None, *, as_json: bool = False):
                    return call_llm(prompt, system=system, as_json=as_json)
                scenario["initial_agents"] = generate_agents_from_scenario(scenario, llm_wrapper)
                errors = validate_scenario(scenario)
                if not errors:
                    scenario = normalize_scenario(scenario)
            except Exception:
                pass  # keep scenario without generated agents on failure
        _last_scenario = scenario
        return jsonify({"ok": True, "error": None, "scenario": scenario})
    except Exception as e:
        logging.exception("api_submit_scenario failed: %s", e)
        return jsonify({
            "ok": False,
            "error": str(e),
            "scenario": None,
        }), 500


def _stream_simulation(
    scenario: dict,
    steps: int,
    dry_run: bool,
    delay_between_rounds: float,
    snapshot_path: str | None = None,
):
    """Generator for SSE stream of simulation turns. If snapshot_path is None, uses default last_snapshot.json."""
    if snapshot_path is None:
        snapshot_path = str(_get_snapshot_dir() / "last_snapshot.json")
    try:
        loop = SimulationLoop(
            scenario_data=scenario,
            dry_run=dry_run,
            snapshot_path=snapshot_path,
        )
        for chunk in loop.run_streaming(
            steps=steps,
            snapshot_out_path=snapshot_path,
            delay_between_rounds=delay_between_rounds,
        ):
            yield f"data: {json.dumps(_make_json_safe(chunk))}\n\n"
    except Exception as e:
        logging.exception("run_simulation_stream failed: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


@app.route("/api/run_simulation", methods=["POST"])
def api_run_simulation():
    """Run simulation. Body: { "scenario": {...} } or { "text": "..." } with optional "steps", "dry_run", "use_llm"."""
    global _last_scenario, _last_run_result, _last_snapshot_path, _current_run_id
    data = request.get_json(force=True, silent=True) or {}
    scenario = data.get("scenario") if isinstance(data.get("scenario"), dict) else _last_scenario
    steps = max(1, min(int(data.get("steps", 5)), 50))
    dry_run = bool(data.get("dry_run", False))
    use_llm_for_agents = bool(data.get("use_llm_for_agents", False))

    if not scenario and data.get("text"):
        try:
            scenario = parse_scenario_text((data.get("text") or "").strip(), use_llm=data.get("use_llm", True))
            scenario = normalize_scenario(scenario)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e), "final": None, "turns": None}), 400

    if not scenario or not isinstance(scenario, dict):
        return jsonify({
            "ok": False,
            "error": "No scenario provided. Submit a scenario first or send scenario JSON or text in the request.",
            "final": None,
            "turns": None,
        }), 400

    errors = validate_scenario(scenario)
    if errors:
        return jsonify({"ok": False, "error": "; ".join(errors), "final": None, "turns": None}), 400

    scenario = normalize_scenario(scenario)
    # LLM Integration: optionally generate agent definitions before run (scenario-to-simulation pipeline)
    if use_llm_for_agents and not dry_run:
        try:
            def llm_wrapper(prompt: str, system: str | None = None, *, as_json: bool = False):
                return call_llm(prompt, system=system, as_json=as_json)
            scenario["initial_agents"] = generate_agents_from_scenario(scenario, llm_wrapper)
            scenario = normalize_scenario(scenario)
        except Exception:
            pass
    _last_scenario = scenario

    _current_run_id += 1
    my_run_id = _current_run_id
    snapshot_dir = _get_snapshot_dir()
    snapshot_path = str(snapshot_dir / f"snapshot_{my_run_id}.json")

    try:
        loop = SimulationLoop(
            scenario_data=scenario,
            dry_run=dry_run,
            snapshot_path=snapshot_path,
        )
        # تاخیر بین راندها برای جلوگیری از rate limit (پیش‌فرض: 0.5 ثانیه؛ کلاینت می‌تواند 0 بفرستد)
        delay_between_rounds = float(data.get("delay_between_rounds", 0.5))
        result = loop.run(
            steps=steps,
            snapshot_out_path=snapshot_path,
            return_turns=True,
            return_provenance=True,
            silent=True,
            delay_between_rounds=delay_between_rounds,
        )
        result["initial_state"] = scenario.get("initial_state") or {}
        if my_run_id == _current_run_id:
            _last_run_result = result
            _last_snapshot_path = snapshot_path
        try:
            provenance_list = result.get("provenance") or []
            turns_list = result.get("turns") or []
            agents_for_dashboard = [
                {"name": getattr(a, "name", ""), "role": getattr(a, "role", ""), "objectives": getattr(a, "objectives", {})}
                for a in loop.agents
            ] if getattr(loop, "agents", None) else [
                {"name": a.get("name"), "role": a.get("role"), "objectives": a.get("objectives") or a.get("goals") or {}}
                for a in (scenario.get("initial_agents") or []) if isinstance(a, dict) and a.get("name")
            ]
            for i, pe in enumerate(provenance_list):
                snap = turns_list[i] if i < len(turns_list) else (pe.get("turn_record") or {}).get("post_state") or {}
                payload = build_dashboard_payload(snap, pe, scenario, agents_for_dashboard, provenance_history=provenance_list[: i + 1])
                dashboard_on_turn_complete(payload)
        except Exception:
            pass
        agents_for_analysis = [
            {"name": getattr(a, "name", ""), "role": getattr(a, "role", ""), "objectives": getattr(a, "objectives", {})}
            for a in loop.agents
        ] if getattr(loop, "agents", None) else list(scenario.get("initial_agents") or [])
        action_defs = getattr(loop, "_action_definitions", None)
        strategic = build_strategic_analysis(
            result,
            scenario=scenario,
            agents=agents_for_analysis,
            action_definitions=action_defs,
            allow_numbers=False,
        )
        payload = {
            "ok": True,
            "error": None,
            "final": _make_json_safe(result["final"]),
            "turns": _make_json_safe(result["turns"]),
            "steps": steps,
            "dry_run": dry_run,
            "strategic_analysis": _make_json_safe(strategic),
        }
        return jsonify(payload)
    except Exception as e:
        if my_run_id == _current_run_id:
            _last_run_result = {"error": str(e)}
        logging.exception("run_simulation failed: %s", e)
        try:
            return jsonify({
                "ok": False,
                "error": str(e),
                "final": None,
                "turns": None,
            }), 500
        except Exception:
            return jsonify({"ok": False, "error": "Internal error", "final": None, "turns": None}), 500


@app.route("/api/run_simulation_stream", methods=["POST"])
def api_run_simulation_stream():
    """Stream simulation turns as Server-Sent Events. Same body as run_simulation; use stream=true in body to prefer this."""
    global _last_scenario, _last_run_result, _last_snapshot_path, _current_run_id
    data = request.get_json(force=True, silent=True) or {}
    scenario = data.get("scenario") if isinstance(data.get("scenario"), dict) else _last_scenario
    steps = max(1, min(int(data.get("steps", 5)), 50))
    dry_run = bool(data.get("dry_run", False))
    delay_between_rounds = float(data.get("delay_between_rounds", 0.5))

    if not scenario and data.get("text"):
        try:
            scenario = parse_scenario_text((data.get("text") or "").strip(), use_llm=data.get("use_llm", True))
            scenario = normalize_scenario(scenario)
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

    if not scenario or not isinstance(scenario, dict):
        return jsonify({"ok": False, "error": "No scenario provided."}), 400

    errors = validate_scenario(scenario)
    if errors:
        return jsonify({"ok": False, "error": "; ".join(errors)}), 400

    scenario = normalize_scenario(scenario)
    if data.get("use_llm_for_agents") and not dry_run:
        try:
            def llm_wrapper(prompt: str, system: str | None = None, *, as_json: bool = False):
                return call_llm(prompt, system=system, as_json=as_json)
            scenario["initial_agents"] = generate_agents_from_scenario(scenario, llm_wrapper)
            scenario = normalize_scenario(scenario)
        except Exception:
            pass
    _last_scenario = scenario

    _current_run_id += 1
    my_run_id = _current_run_id
    snapshot_path = str(_get_snapshot_dir() / f"snapshot_{my_run_id}.json")

    _heartbeat_interval = 30  # send ping every 30s when a turn takes long

    def generate():
        global _last_run_result, _last_snapshot_path, _current_run_id
        chunk_queue: queue.Queue[str | None] = queue.Queue()

        def producer():
            try:
                for chunk in _stream_simulation(
                    scenario, steps, dry_run, delay_between_rounds, snapshot_path=snapshot_path
                ):
                    chunk_queue.put(chunk)
            except Exception as e:
                chunk_queue.put(f'data: {json.dumps({"type": "error", "error": str(e)})}\n\n')
            finally:
                chunk_queue.put(None)

        t = threading.Thread(target=producer, daemon=True)
        t.start()

        turns_accumulated: list = []
        provenance_accumulated: list = []
        agents_list = [
            {"name": a.get("name"), "role": a.get("role"), "objectives": a.get("objectives") or a.get("goals") or {}}
            for a in (scenario.get("initial_agents") or [])
            if isinstance(a, dict) and a.get("name")
        ]
        while True:
            try:
                chunk = chunk_queue.get(timeout=_heartbeat_interval)
            except queue.Empty:
                yield f'data: {json.dumps({"type": "ping"})}\n\n'
                continue
            if chunk is None:
                break
            yield chunk
            try:
                data_line = chunk.replace("data: ", "").strip()
                parsed = json.loads(data_line)
                if parsed.get("type") == "turn":
                    turns_accumulated.append(parsed.get("turn"))
                    pe = parsed.get("provenance_entry")
                    if pe is not None:
                        provenance_accumulated.append(pe)
                    try:
                        payload = build_dashboard_payload(
                            parsed.get("turn") or {},
                            pe,
                            scenario,
                            agents_list,
                            provenance_history=provenance_accumulated,
                        )
                        dashboard_on_turn_complete(payload)
                    except Exception:
                        pass
                elif parsed.get("type") == "done":
                    if my_run_id == _current_run_id:
                        _last_run_result = {
                            "final": parsed.get("final"),
                            "turns": turns_accumulated,
                            "provenance": parsed.get("provenance", []),
                            "initial_state": scenario.get("initial_state") or {},
                        }
                        _last_snapshot_path = snapshot_path
            except Exception:
                pass

    resp = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    return resp


@app.route("/api/snapshot", methods=["GET"])
def api_snapshot():
    """Return last saved snapshot JSON (from last Run Simulation), or last run's final state."""
    path = request.args.get("path")
    if path:
        try:
            p = Path(path)
            if not p.is_absolute():
                p = _PROJECT_ROOT / p
            if not str(p.resolve()).startswith(str(_PROJECT_ROOT.resolve())):
                return jsonify({"ok": False, "error": "Path not allowed"}), 403
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            return jsonify({"ok": True, "snapshot": data})
        except (OSError, json.JSONDecodeError) as e:
            return jsonify({"ok": False, "error": str(e)}), 404

    if _last_run_result and isinstance(_last_run_result, dict) and "final" in _last_run_result:
        return jsonify({"ok": True, "snapshot": _last_run_result["final"]})
    if _last_snapshot_path and os.path.isfile(_last_snapshot_path):
        try:
            with open(_last_snapshot_path, encoding="utf-8") as f:
                data = json.load(f)
            return jsonify({"ok": True, "snapshot": data})
        except (OSError, json.JSONDecodeError):
            pass
    # Fallback: read from default snapshot file (survives server restart)
    snapshot_path = _last_snapshot_path or str(_get_snapshot_dir() / "last_snapshot.json")
    if os.path.isfile(snapshot_path):
        try:
            with open(snapshot_path, encoding="utf-8") as f:
                data = json.load(f)
            return jsonify({"ok": True, "snapshot": data})
        except (OSError, json.JSONDecodeError):
            pass
    return jsonify({"ok": False, "error": "No snapshot available. Run a simulation first.", "snapshot": None}), 200


@app.route("/api/llm_logs", methods=["GET"])
def api_llm_logs():
    """Return list of LLM call log entries (system, prompt, response) for UI inspection."""
    logs = get_llm_logs()
    return jsonify({"ok": True, "logs": logs})


@app.route("/api/llm_logs/clear", methods=["POST"])
def api_llm_logs_clear():
    """Clear the LLM call log."""
    clear_llm_logs()
    return jsonify({"ok": True})


@app.route("/api/narrative", methods=["GET"])
def api_narrative():
    """Build narrative from last run's trace and final state (no LLM in GET). Falls back to snapshot file when run result is unavailable."""
    try:
        trace = None
        final = None

        if _last_run_result and isinstance(_last_run_result, dict) and "final" in _last_run_result:
            trace = _last_run_result.get("provenance", [])
            final = _last_run_result["final"]

        if not trace or not final:
            snapshot_path = _last_snapshot_path or str(_get_snapshot_dir() / "last_snapshot.json")
            if os.path.isfile(snapshot_path):
                try:
                    with open(snapshot_path, encoding="utf-8") as f:
                        snapshot = json.load(f)
                    if snapshot is not None and isinstance(snapshot, dict):
                        trace = trace_from_snapshot(snapshot)
                        final = snapshot
                except (OSError, json.JSONDecodeError):
                    pass

        if final is not None and isinstance(final, dict):
            if not trace and (final.get("causal_links") or []):
                try:
                    trace = trace_from_snapshot(final)
                except Exception:
                    trace = []
            if trace:
                narrative = build_narrative(trace, final, use_llm=False)
                scenario = _last_scenario or {}
                agents = [a for a in (scenario.get("initial_agents") or []) if isinstance(a, dict)]
                result = {"final": final, "provenance": trace}
                state_specs = scenario.get("variable_specs") or scenario.get("state_spec") or {}
                narrative_facts = build_narrative_facts(trace, final, agents=agents, scenario=scenario, state_specs=state_specs)
                analysis = build_scenario_analysis_output(
                    result,
                    scenario=scenario,
                    agents=agents,
                    action_definitions=None,
                    facts=narrative_facts,
                    allow_numbers=False,
                )
                strategic = build_strategic_analysis(
                    result,
                    scenario=scenario,
                    agents=agents,
                    action_definitions=None,
                    facts=narrative_facts,
                    allow_numbers=False,
                )
                return jsonify({
                    "ok": True,
                    "narrative": narrative,
                    "logic_core": _make_json_safe(analysis["logic_core"]),
                    "executive_summary": analysis["executive_summary"],
                    "strategic_analysis": _make_json_safe(strategic),
                })

        return jsonify({"ok": False, "error": "No run available. Run a simulation first.", "narrative": None}), 200
    except Exception as e:
        logging.exception("api_narrative failed")
        return jsonify({"ok": False, "error": str(e), "narrative": None}), 500


@app.route("/api/last_run_for_viewer", methods=["GET"])
def api_last_run_for_viewer():
    """Return last run result for the Run Viewer (final + turns). Used when viewer opens in a new tab and sessionStorage is empty."""
    if not _last_run_result or not isinstance(_last_run_result, dict) or "final" not in _last_run_result:
        return jsonify({"ok": False, "run": None}), 200
    run = {
        "final": _make_json_safe(_last_run_result["final"]),
        "turns": _make_json_safe(_last_run_result.get("turns") or []),
    }
    return jsonify({"ok": True, "run": run}), 200


@app.route("/viewer", methods=["GET"])
def run_viewer():
    """Run Viewer: client-only page for pasted/imported run JSON. No server-injected run data."""
    return render_template("run_viewer.html")


@app.route("/graph", methods=["GET"])
def graph_viewer():
    """Render causal graph visualization. Query params: turn (optional), animate (optional)."""
    global _last_run_result, _last_snapshot_path
    
    turn_param = request.args.get("turn")
    animate_param = request.args.get("animate", "false").lower() == "true"
    
    # Get snapshot data
    snapshot = None
    turns = None
    current_turn_index = 0
    
    if _last_run_result and isinstance(_last_run_result, dict):
        if "final" in _last_run_result:
            snapshot = _last_run_result["final"]
        if "turns" in _last_run_result and isinstance(_last_run_result["turns"], list):
            turns = _last_run_result["turns"]
            if turn_param:
                try:
                    turn_idx = int(turn_param)
                    if 0 <= turn_idx < len(turns):
                        snapshot = turns[turn_idx]
                        current_turn_index = turn_idx
                except ValueError:
                    pass
    
    if not snapshot and _last_snapshot_path and os.path.isfile(_last_snapshot_path):
        try:
            with open(_last_snapshot_path, encoding="utf-8") as f:
                snapshot = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    
    if not snapshot:
        # Return empty graph
        graph_data = {"nodes": [], "edges": [], "turn": 0}
        return render_template(
            "graph.html",
            graph_data=graph_data,
            impact_data=None,
            nodes=[],
            edges=[],
            turn=0,
            turns_data=None,
            turns=None,
            current_turn_index=0,
        )
    
    # Prepare graph data
    graph_data = prepare_graph_data(snapshot)

    # Impact data (initial vs final, top drivers, activated edges) for Impact View
    impact_data = None
    if _last_run_result and isinstance(_last_run_result, dict):
        initial_state = _last_run_result.get("initial_state")
        provenance = _last_run_result.get("provenance")
        final_snapshot = _last_run_result.get("final")
        if initial_state is not None and final_snapshot is not None:
            impact_data = prepare_impact_data(
                initial_state,
                final_snapshot,
                provenance=provenance,
                causal_links=snapshot.get("causal_links"),
            )

    # Prepare turns data for animation (always pass if available, so user can navigate manually)
    turns_data = turns if turns else None

    return render_template(
        "graph.html",
        graph_data=graph_data,
        impact_data=impact_data,
        nodes=graph_data["nodes"],
        edges=graph_data["edges"],
        turn=graph_data.get("turn", 0),
        turns_data=turns_data,
        turns=turns,
        current_turn_index=current_turn_index,
    )


@app.route("/api/graph_data", methods=["GET"])
def api_graph_data():
    """Return JSON graph data for AJAX. Query params: turn (optional)."""
    global _last_run_result, _last_snapshot_path
    
    turn_param = request.args.get("turn")
    
    # Get snapshot data
    snapshot = None
    
    if _last_run_result and isinstance(_last_run_result, dict):
        if "final" in _last_run_result:
            snapshot = _last_run_result["final"]
        if turn_param and "turns" in _last_run_result and isinstance(_last_run_result["turns"], list):
            turns = _last_run_result["turns"]
            try:
                turn_idx = int(turn_param)
                if 0 <= turn_idx < len(turns):
                    snapshot = turns[turn_idx]
            except ValueError:
                pass
    
    if not snapshot and _last_snapshot_path and os.path.isfile(_last_snapshot_path):
        try:
            with open(_last_snapshot_path, encoding="utf-8") as f:
                snapshot = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    
    if not snapshot:
        snapshot_path = _last_snapshot_path or str(_get_snapshot_dir() / "last_snapshot.json")
        if os.path.isfile(snapshot_path):
            try:
                with open(snapshot_path, encoding="utf-8") as f:
                    snapshot = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
    
    if not snapshot:
        return jsonify({"ok": False, "error": "No snapshot available. Run a simulation first.", "graph_data": None}), 200
    
    graph_data = prepare_graph_data(snapshot)
    return jsonify({"ok": True, "graph_data": graph_data})


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Open World Engine – Web UI")
    ap.add_argument("--port", type=int, default=5000, help="Port (default: 5000)")
    ap.add_argument("--host", type=str, default="0.0.0.0", help="Host (default: 0.0.0.0 = all interfaces; use 127.0.0.1 for local only)")
    ap.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = ap.parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
