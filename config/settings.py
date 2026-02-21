"""
Central settings: read from config file (config/settings.json), then override with env.
Config path: set OWE_CONFIG to use another file. API keys: in settings.json or env.
"""

import json
import os
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_env = os.environ
_CONFIG_FILE = _PROJECT_ROOT / "config" / "settings.json"


def _load_config_file() -> dict[str, Any]:
    config_path = _env.get("OWE_CONFIG", str(_CONFIG_FILE))
    path = Path(config_path)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


_cfg = _load_config_file()


def _from_env(key: str, env_key: str | None = None) -> str | None:
    name = env_key or f"OWE_{key.upper()}"
    v = _env.get(name)
    return v.strip() if isinstance(v, str) and v.strip() else None


def _path_from_file(key: str) -> str | None:
    v = _cfg.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    p = Path(str(v).strip())
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    return str(p.resolve())


# --- Scenario
_scenario_env = _from_env("SCENARIO_PATH")
_default_scenario = str(_PROJECT_ROOT / "config" / "scenarios" / "demo_scenario.json")
if _scenario_env:
    p = Path(_scenario_env)
    SCENARIO_PATH = str(p.resolve()) if p.is_absolute() else str((_PROJECT_ROOT / p).resolve())
else:
    SCENARIO_PATH = _path_from_file("scenario_path") or _default_scenario

# --- Dry run
_dry_env = _from_env("DRY_RUN")
DRY_RUN: bool = (
    _dry_env.lower() in ("true", "1", "yes") if _dry_env is not None
    else bool(_cfg.get("dry_run", False))
)

# --- Max LLM calls per turn
_max_env = _from_env("MAX_LLM_CALLS_PER_TURN")
MAX_LLM_CALLS_PER_TURN: int = int(_max_env or _cfg.get("max_llm_calls_per_turn", 20))

# --- Snapshot path
_snap_env = _from_env("SNAPSHOT_PATH")
SNAPSHOT_PATH: str | None = None
if _snap_env:
    p = Path(_snap_env)
    SNAPSHOT_PATH = str(p.resolve()) if p.is_absolute() else str((_PROJECT_ROOT / p).resolve())
elif _cfg.get("snapshot_path") is not None and str(_cfg.get("snapshot_path")).strip():
    SNAPSHOT_PATH = _path_from_file("snapshot_path")

# --- Meta-proposal auto-approve
_meta_env = _from_env("META_PROPOSAL_AUTO_APPROVE_MAX_AGENTS")
META_PROPOSAL_AUTO_APPROVE_MAX_AGENTS: int = int(_meta_env or _cfg.get("meta_proposal_auto_approve_max_agents", 1))

# --- Environment agent (default False for backward compat; set true to enable)
_env_agent_env = _from_env("ENABLE_ENVIRONMENT_AGENT")
ENABLE_ENVIRONMENT_AGENT: bool = (
    _env_agent_env.lower() in ("true", "1", "yes") if _env_agent_env is not None
    else bool(_cfg.get("enable_environment_agent", False))
)

# --- Meta-actions and limits
_meta_actions = _cfg.get("enable_meta_actions")
ENABLE_META_ACTIONS: bool = bool(_meta_actions) if _meta_actions is not None else False
MAX_NEW_VARIABLES_PER_N_TURNS: int = int(_cfg.get("max_new_variables_per_N_turns", 2))
META_TURNS_WINDOW: int = int(_cfg.get("meta_turns_window", 10))
MAX_NEW_ACTIONS_PER_N_TURNS: int = int(_cfg.get("max_new_actions_per_N_turns", 2))
CHANGE_BUDGET: float | None = _cfg.get("change_budget")

# --- Debug LLM
_debug_env = _from_env("DEBUG_LLM")
DEBUG_LLM: bool = (
    _debug_env.lower() in ("true", "1", "yes") if _debug_env is not None
    else bool(_cfg.get("debug_llm", False))
)

# --- Multi-stage scenario compiler
_multi_stage_env = _from_env("MULTI_STAGE_COMPILER")
MULTI_STAGE_COMPILER: bool = (
    _multi_stage_env.lower() in ("true", "1", "yes") if _multi_stage_env is not None
    else bool(_cfg.get("multi_stage_compiler", False))
)

# --- Enable uncertainty
_uncertainty_env = _from_env("ENABLE_UNCERTAINTY")
ENABLE_UNCERTAINTY: bool = (
    _uncertainty_env.lower() in ("true", "1", "yes") if _uncertainty_env is not None
    else bool(_cfg.get("enable_uncertainty", False))
)

# --- Delta magnitude cap (guard: max absolute change per variable)
_delta_cap = _cfg.get("delta_magnitude_cap")
DELTA_MAGNITUDE_CAP: float | None = None
if _delta_cap is not None and isinstance(_delta_cap, (int, float)):
    DELTA_MAGNITUDE_CAP = float(_delta_cap)
elif _from_env("DELTA_MAGNITUDE_CAP"):
    try:
        DELTA_MAGNITUDE_CAP = float(_from_env("DELTA_MAGNITUDE_CAP"))
    except (ValueError, TypeError):
        DELTA_MAGNITUDE_CAP = None
# Default cap if not set: 1000 (reasonable for cash-like variables)
if DELTA_MAGNITUDE_CAP is None:
    DELTA_MAGNITUDE_CAP = 1000.0

# --- Strategic agent: max delta per variable per turn (clipped by WorldModelAgent)
_max_delta_cfg = _cfg.get("max_delta")
MAX_DELTA: float = 10.0
if _max_delta_cfg is not None and isinstance(_max_delta_cfg, (int, float)):
    MAX_DELTA = float(_max_delta_cfg)
elif _from_env("MAX_DELTA"):
    try:
        MAX_DELTA = float(_from_env("MAX_DELTA"))
    except (ValueError, TypeError):
        pass

# --- Strategic agent: observation noise scale (optional)
_obs_cfg = _cfg.get("obs_noise_scale")
OBS_NOISE_SCALE: float = 0.0
if _obs_cfg is not None and isinstance(_obs_cfg, (int, float)):
    OBS_NOISE_SCALE = float(_obs_cfg)
elif _from_env("OBS_NOISE_SCALE"):
    try:
        OBS_NOISE_SCALE = float(_from_env("OBS_NOISE_SCALE"))
    except (ValueError, TypeError):
        pass

# --- Hardening: proposal throttle, propagation, phase detection
_proposal_throttle = _cfg.get("proposal_throttle_turns")
PROPOSAL_THROTTLE_TURNS: int = int(_proposal_throttle or 3)
_prop_max_iter = _cfg.get("propagation_max_iter")
PROPAGATION_MAX_ITER: int = int(_prop_max_iter or 5)
_prop_epsilon = _cfg.get("propagation_epsilon")
PROPAGATION_EPSILON: float = float(_prop_epsilon or 1e-6)
_prop_damping = _cfg.get("propagation_damping")
PROPAGATION_DAMPING: float = float(_prop_damping or 0.6)
_phase_top_k = _cfg.get("phase_top_k_turns")
PHASE_TOP_K_TURNS: int = int(_phase_top_k or 3)

# --- v2 narrative and shocks
ALLOW_NUMBERS: bool = bool(_cfg.get("allow_numbers", False))
ENABLE_SHOCKS: bool = bool(_cfg.get("enable_shocks", False))
LANG: str = str(_cfg.get("lang", "auto")).strip().lower() or "auto"

# --- Random seed
_random_seed_env = _from_env("RANDOM_SEED")
RANDOM_SEED: int | None = None
if _random_seed_env is not None:
    try:
        RANDOM_SEED = int(_random_seed_env)
    except (ValueError, TypeError):
        RANDOM_SEED = None
elif _cfg.get("random_seed") is not None:
    try:
        RANDOM_SEED = int(_cfg.get("random_seed"))
    except (ValueError, TypeError):
        RANDOM_SEED = None

# --- Standalone LLM (OpenAI-compatible)
_openai = _cfg.get("openai") or {}
OPENAI_API_KEY: str = _env.get("OPENAI_API_KEY", "").strip() or str(_openai.get("api_key") or "").strip()
OPENAI_BASE_URL: str = _env.get("OPENAI_BASE_URL", "").strip() or str(_openai.get("base_url") or "https://api.openai.com/v1").strip()
OPENAI_MODEL: str = _env.get("OPENAI_MODEL", "").strip() or str(_openai.get("model") or "gpt-4o-mini").strip()

# --- Groq (when llm_provider is groq)
_groq = _cfg.get("groq") or {}
GROQ_BASE_URL: str = _env.get("GROQ_BASE_URL", "").strip() or str(_groq.get("base_url") or "https://api.groq.com/openai/v1").strip()
GROQ_API_KEY: str = _env.get("GROQ_API_KEY", "").strip() or str(_groq.get("api_key") or "").strip()
GROQ_MODEL: str = _env.get("GROQ_MODEL", "").strip() or str(_groq.get("model") or "llama-3.3-70b-versatile").strip()
GROQ_TEMPERATURE: float = float(_env.get("GROQ_TEMPERATURE", "") or _groq.get("temperature", 0.2))
GROQ_MAX_TOKENS: int = int(_env.get("GROQ_MAX_TOKENS", "") or _groq.get("max_tokens", 512))
GROQ_TIMEOUT: int = int(_env.get("GROQ_TIMEOUT", "") or _groq.get("timeout", 15))

# --- AvalAI (preferred when llm_provider is avalai)
_avalai = _cfg.get("avalai") or {}
AVALAI_API_KEY: str = _env.get("AVALAI_API_KEY", "").strip() or str(_avalai.get("api_key") or "").strip()
AVALAI_BASE_URL: str = _env.get("AVALAI_BASE_URL", "").strip() or str(_avalai.get("base_url") or "https://api.avalai.ir/v1").strip()
AVALAI_MODEL: str = _env.get("AVALAI_MODEL", "").strip() or str(_avalai.get("model") or "gpt-4o-mini").strip()
AVALAI_TEMPERATURE: float = float(_env.get("AVALAI_TEMPERATURE", "") or _avalai.get("temperature", 0.2))
AVALAI_MAX_TOKENS: int = int(_env.get("AVALAI_MAX_TOKENS", "") or _avalai.get("max_tokens", 512))
AVALAI_TIMEOUT: int = int(_env.get("AVALAI_TIMEOUT", "") or _avalai.get("timeout", 10))
LLM_PROVIDER: str = (_env.get("LLM_PROVIDER", "").strip() or str(_cfg.get("llm_provider") or "avalai")).strip().lower()
if LLM_PROVIDER not in ("groq", "avalai"):
    LLM_PROVIDER = "avalai"


def get_llm_provider_config(provider: str) -> dict[str, Any]:
    """Return config dict for provider. Keys: base_url, api_key, model, temperature, max_tokens, timeout."""
    p = (provider or "").strip().lower() or LLM_PROVIDER
    if p == "avalai":
        return {
            "base_url": AVALAI_BASE_URL,
            "api_key": AVALAI_API_KEY,
            "model": AVALAI_MODEL,
            "temperature": AVALAI_TEMPERATURE,
            "max_tokens": AVALAI_MAX_TOKENS,
            "timeout": AVALAI_TIMEOUT,
        }
    return {
        "base_url": GROQ_BASE_URL,
        "api_key": GROQ_API_KEY,
        "model": GROQ_MODEL,
        "temperature": GROQ_TEMPERATURE,
        "max_tokens": GROQ_MAX_TOKENS,
        "timeout": GROQ_TIMEOUT,
    }


def get_settings() -> dict[str, Any]:
    return {
        "scenario_path": SCENARIO_PATH,
        "dry_run": DRY_RUN,
        "max_llm_calls_per_turn": MAX_LLM_CALLS_PER_TURN,
        "snapshot_path": SNAPSHOT_PATH,
        "meta_proposal_auto_approve_max_agents": META_PROPOSAL_AUTO_APPROVE_MAX_AGENTS,
        "enable_environment_agent": ENABLE_ENVIRONMENT_AGENT,
        "enable_meta_actions": ENABLE_META_ACTIONS,
        "change_budget": CHANGE_BUDGET,
        "debug_llm": DEBUG_LLM,
        "multi_stage_compiler": MULTI_STAGE_COMPILER,
        "enable_uncertainty": ENABLE_UNCERTAINTY,
        "random_seed": RANDOM_SEED,
        "max_delta": MAX_DELTA,
        "obs_noise_scale": OBS_NOISE_SCALE,
        "llm_provider": LLM_PROVIDER,
        "openai_api_key": OPENAI_API_KEY,
        "openai_base_url": OPENAI_BASE_URL,
        "openai_model": OPENAI_MODEL,
        "groq_api_key": GROQ_API_KEY,
        "groq_base_url": GROQ_BASE_URL,
        "groq_model": GROQ_MODEL,
        "avalai_api_key": AVALAI_API_KEY,
        "avalai_base_url": AVALAI_BASE_URL,
        "avalai_model": AVALAI_MODEL,
        "allow_numbers": ALLOW_NUMBERS,
        "enable_shocks": ENABLE_SHOCKS,
        "lang": LANG,
    }
