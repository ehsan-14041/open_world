"""
Optional shock engine. When disabled, runs are deterministic (given seed).
"""

from shocks.shock_engine import apply_shocks_if_enabled, ShockSpec

__all__ = ["apply_shocks_if_enabled", "ShockSpec"]
