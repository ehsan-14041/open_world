"""
Runtime simulation mode: mutable state for simulation_mode, enable_shocks, enable_uncertainty.
Defaults are read from config at import; control API can override at runtime.
"""

from __future__ import annotations

from typing import Any

# Defaults from config (lazy to avoid circular import)
_def_mode: str | None = None
_def_shocks: bool | None = None
_def_uncertainty: bool | None = None

_runtime_mode: str | None = None
_runtime_shocks: bool | None = None
_runtime_uncertainty: bool | None = None


def _load_defaults() -> None:
    global _def_mode, _def_shocks, _def_uncertainty
    if _def_mode is not None:
        return
    try:
        from config.settings import SIMULATION_MODE, ENABLE_SHOCKS, ENABLE_UNCERTAINTY
        _def_mode = SIMULATION_MODE
        _def_shocks = ENABLE_SHOCKS
        _def_uncertainty = ENABLE_UNCERTAINTY
    except ImportError:
        _def_mode = "standard"
        _def_shocks = False
        _def_uncertainty = False


def get_simulation_mode() -> str:
    """Return current simulation mode (standard | shock_global)."""
    _load_defaults()
    return _runtime_mode if _runtime_mode is not None else (_def_mode or "standard")


def set_simulation_mode(mode: str) -> None:
    """Set simulation mode at runtime. Use 'standard', 'shock_global', or 'stress_test'."""
    global _runtime_mode
    m = (mode or "standard").strip().lower()
    _runtime_mode = m if m in ("standard", "shock_global", "stress_test") else "standard"


def get_enable_shocks() -> bool:
    """Return whether shocks are enabled (for shock_global mode)."""
    _load_defaults()
    return _runtime_shocks if _runtime_shocks is not None else (_def_shocks or False)


def set_enable_shocks(enabled: bool) -> None:
    """Enable or disable shock engine at runtime."""
    global _runtime_shocks
    _runtime_shocks = bool(enabled)


def get_enable_uncertainty() -> bool:
    """Return whether uncertainty (noise) is enabled."""
    _load_defaults()
    return _runtime_uncertainty if _runtime_uncertainty is not None else (_def_uncertainty or False)


def set_enable_uncertainty(enabled: bool) -> None:
    """Enable or disable uncertainty/noise at runtime."""
    global _runtime_uncertainty
    _runtime_uncertainty = bool(enabled)


def get_mode_state() -> dict[str, Any]:
    """Return current mode state for API."""
    return {
        "simulation_mode": get_simulation_mode(),
        "enable_shocks": get_enable_shocks(),
        "enable_uncertainty": get_enable_uncertainty(),
    }
