"""
Live Enterprise Dashboard: real-time visualization of world state, risk, calibration,
action selection, assumptions, and explainability. Reads only from structured JSON;
no direct coupling with simulation internals.
"""

from __future__ import annotations

import json
import queue
import threading
from typing import Any

from config.settings import DASHBOARD_HISTORY_SIZE, DASHBOARD_ENABLED
from core.dashboard_payload import build_dashboard_payload as _build_dashboard_payload

# Re-export for ui.py and callers
build_dashboard_payload = _build_dashboard_payload

# In-memory buffer of dashboard payloads (last N turns)
_buffer: list[dict[str, Any]] = []
_lock = threading.Lock()
_MAX_HISTORY = max(1, DASHBOARD_HISTORY_SIZE)

# Last run provenance and scenario (for research draft export)
_last_provenance: list[dict[str, Any]] = []
_last_scenario: dict[str, Any] = {}

# Optional SSE: queue for notifying listeners when a new payload is added
_sse_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()


def _make_json_safe(obj: object) -> object:
    """Replace float('nan')/inf with None for JSON."""
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


def on_turn_complete(event_payload: dict[str, Any]) -> None:
    """Append a dashboard event payload to the history buffer (bounded by DASHBOARD_HISTORY_SIZE)."""
    if not DASHBOARD_ENABLED:
        return
    safe = _make_json_safe(event_payload)
    payload_copy = dict(safe) if safe is not None else dict(event_payload)
    with _lock:
        _buffer.append(payload_copy)
        while len(_buffer) > _MAX_HISTORY:
            _buffer.pop(0)
    try:
        _sse_queue.put_nowait(payload_copy)
    except queue.Full:
        pass


def get_latest_payload() -> dict[str, Any] | None:
    """Return the most recent dashboard payload, or None if empty."""
    with _lock:
        p = _buffer[-1] if _buffer else None
    if p is not None:
        safe = _make_json_safe(p)
        return dict(safe) if safe is not None else p
    return None


def get_history_payloads() -> list[dict[str, Any]]:
    """Return the last N dashboard payloads (for time-series and calibration)."""
    with _lock:
        out = list(_buffer)
    return [dict(_make_json_safe(p) or p) for p in out]


def set_last_provenance(provenance: list[dict[str, Any]]) -> None:
    """Store the last run's provenance for research draft export."""
    global _last_provenance
    _last_provenance = list(provenance) if provenance else []


def get_last_provenance() -> list[dict[str, Any]]:
    """Return the last run's provenance (for research draft)."""
    with _lock:
        return list(_last_provenance)


def set_last_scenario(scenario: dict[str, Any]) -> None:
    """Store the last run's scenario for research draft."""
    global _last_scenario
    _last_scenario = dict(scenario) if scenario else {}


def get_last_scenario() -> dict[str, Any]:
    """Return the last run's scenario."""
    with _lock:
        return dict(_last_scenario)


def register_routes(app: Any) -> None:
    """Register dashboard Flask routes on the given app."""
    if not DASHBOARD_ENABLED:
        return

    from flask import Response, render_template, jsonify, stream_with_context

    @app.route("/dashboard")
    def dashboard_page():
        return render_template("dashboard.html")

    @app.route("/api/dashboard/config", methods=["GET", "POST"])
    def api_dashboard_config():
        """GET: return dashboard config (edition, research_export, enable_oracle). POST: update enable_oracle from UI toggle (takes effect on next run)."""
        from flask import request
        if request.method == "POST":
            try:
                from config.settings import _DASHBOARD_OVERRIDES_FILE, _load_dashboard_overrides, get_enable_oracle
            except ImportError:
                return jsonify({"error": "Settings not available"}), 500
            data = request.get_json(silent=True) or {}
            if "enable_oracle" not in data:
                return jsonify({"ok": True, "enable_oracle": get_enable_oracle()})
            overrides = _load_dashboard_overrides()
            overrides["enable_oracle"] = bool(data["enable_oracle"])
            path = _DASHBOARD_OVERRIDES_FILE
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(overrides, f, indent=2)
            except OSError as e:
                return jsonify({"error": str(e)}), 500
            return jsonify({"ok": True, "enable_oracle": get_enable_oracle()})
        try:
            from enterprise.positioning import get_current_tier, get_enterprise_profile
            edition = get_current_tier()
            profile = get_enterprise_profile(edition)
            research_export = profile.get("feature_flags") or {}
            research_export = research_export.get("research_export", True)
        except Exception:
            edition = "Research Edition"
            research_export = True
        try:
            from config.settings import ENABLE_RESEARCH_EXPORT
            research_export = research_export and ENABLE_RESEARCH_EXPORT
        except Exception:
            pass
        try:
            from config.settings import get_enable_oracle
            enable_oracle = get_enable_oracle()
        except Exception:
            enable_oracle = False
        return jsonify({
            "edition": edition,
            "research_export": bool(research_export),
            "enable_oracle": bool(enable_oracle),
        })

    @app.route("/api/dashboard/research_draft")
    def api_dashboard_research_draft():
        """Generate research draft from last run provenance; return as downloadable markdown."""
        from flask import make_response
        provenance = get_last_provenance()
        if not provenance:
            return jsonify({"error": "No simulation provenance available. Run a simulation first."}), 400
        try:
            from research.paper_draft import generate_research_draft
            from config.settings import get_settings
            config = get_settings()
            config["scenario"] = get_last_scenario() or config
            md = generate_research_draft(provenance, config=config)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        resp = make_response(md)
        resp.headers["Content-Type"] = "text/markdown; charset=utf-8"
        resp.headers["Content-Disposition"] = 'attachment; filename="research_draft.md"'
        return resp

    @app.route("/api/dashboard/latest")
    def api_dashboard_latest():
        payload = get_latest_payload()
        return jsonify(payload if payload is not None else {})

    @app.route("/api/dashboard/history")
    def api_dashboard_history():
        return jsonify(get_history_payloads())

    @app.route("/api/dashboard/events")
    def api_dashboard_events():
        """Lightweight SSE: stream latest payload when available; heartbeat every 15s."""

        def generate():
            import time
            last_sent: dict[str, Any] | None = None
            heartbeat_interval = 15.0
            last_heartbeat = time.monotonic()
            while True:
                try:
                    payload = _sse_queue.get(timeout=1.0)
                    if payload is None:
                        break
                    last_sent = payload
                    yield f"data: {json.dumps(_make_json_safe(payload) or payload)}\n\n"
                except queue.Empty:
                    pass
                now = time.monotonic()
                if now - last_heartbeat >= heartbeat_interval:
                    last_heartbeat = now
                    if last_sent is not None:
                        yield f"data: {json.dumps(_make_json_safe(last_sent) or last_sent)}\n\n"
                    else:
                        with _lock:
                            latest = _buffer[-1] if _buffer else None
                        if latest is not None:
                            yield f"data: {json.dumps(_make_json_safe(latest) or latest)}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
