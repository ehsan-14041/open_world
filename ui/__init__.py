"""
UI package: dashboard and optional UI components.
Dashboard provides real-time visualization of world state, risk, calibration, and explainability.
"""

from ui.dashboard import (
    build_dashboard_payload,
    on_turn_complete,
    register_routes,
    get_latest_payload,
    get_history_payloads,
)

__all__ = [
    "build_dashboard_payload",
    "on_turn_complete",
    "register_routes",
    "get_latest_payload",
    "get_history_payloads",
]
