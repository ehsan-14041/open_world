"""Config: settings and scenario paths."""

from config.settings import (
    SCENARIO_PATH,
    DRY_RUN,
    MAX_LLM_CALLS_PER_TURN,
    SNAPSHOT_PATH,
    META_PROPOSAL_AUTO_APPROVE_MAX_AGENTS,
    DEBUG_LLM,
    get_settings,
    get_llm_provider_config,
)

__all__ = [
    "SCENARIO_PATH",
    "DRY_RUN",
    "MAX_LLM_CALLS_PER_TURN",
    "SNAPSHOT_PATH",
    "META_PROPOSAL_AUTO_APPROVE_MAX_AGENTS",
    "DEBUG_LLM",
    "get_settings",
    "get_llm_provider_config",
]
