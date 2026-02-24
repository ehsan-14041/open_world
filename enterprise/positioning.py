"""
Enterprise Pricing & Positioning Layer.
Product tiers define feature flags, dashboard modules, simulation horizon, calibration depth.
No billing implementation — positioning only.
"""

from __future__ import annotations

from typing import Any

# Tier display names and internal keys
TIER_RESEARCH = "Research Edition"
TIER_ENTERPRISE_CORE = "Enterprise Core"
TIER_ENTERPRISE_PRO = "Enterprise Pro"
TIER_GOVERNMENT = "Government / Geopolitical"

_VALID_TIERS = (TIER_RESEARCH, TIER_ENTERPRISE_CORE, TIER_ENTERPRISE_PRO, TIER_GOVERNMENT)

_DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    TIER_RESEARCH: {
        "label": TIER_RESEARCH,
        "feature_flags": {
            "belief_layer": False,
            "shock_global": False,
            "research_export": True,
        },
        "dashboard_modules_enabled": ["state", "risk", "calibration", "action_selection", "explainability"],
        "simulation_horizon": 50,
        "calibration_depth": "shallow",
    },
    TIER_ENTERPRISE_CORE: {
        "label": TIER_ENTERPRISE_CORE,
        "feature_flags": {
            "belief_layer": True,
            "shock_global": False,
            "research_export": True,
        },
        "dashboard_modules_enabled": ["state", "risk", "calibration", "action_selection", "explainability", "belief_alignment"],
        "simulation_horizon": 100,
        "calibration_depth": "full",
    },
    TIER_ENTERPRISE_PRO: {
        "label": TIER_ENTERPRISE_PRO,
        "feature_flags": {
            "belief_layer": True,
            "shock_global": True,
            "research_export": True,
        },
        "dashboard_modules_enabled": ["state", "risk", "calibration", "action_selection", "explainability", "belief_alignment", "shock"],
        "simulation_horizon": None,
        "calibration_depth": "full",
    },
    TIER_GOVERNMENT: {
        "label": TIER_GOVERNMENT,
        "feature_flags": {
            "belief_layer": True,
            "shock_global": True,
            "research_export": True,
        },
        "dashboard_modules_enabled": ["state", "risk", "calibration", "action_selection", "explainability", "belief_alignment", "shock"],
        "simulation_horizon": None,
        "calibration_depth": "full",
    },
}


def get_enterprise_profile(tier_name: str) -> dict[str, Any]:
    """
    Return feature config for the given tier.
    Keys: label, feature_flags, dashboard_modules_enabled, simulation_horizon, calibration_depth.
    Unknown tier falls back to Research Edition.
    """
    name = (tier_name or "").strip() or TIER_RESEARCH
    if name not in _DEFAULT_PROFILES:
        name = TIER_RESEARCH
    return dict(_DEFAULT_PROFILES[name])


def get_current_tier() -> str:
    """
    Return current tier from config (settings). Reads ENTERPRISE_TIER from settings module.
    """
    try:
        from config.settings import ENTERPRISE_TIER
        tier = (ENTERPRISE_TIER or "").strip() or TIER_RESEARCH
    except Exception:
        tier = TIER_RESEARCH
    return tier if tier in _VALID_TIERS else TIER_RESEARCH
