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

# --- Max LLM calls per turn (global)
_max_env = _from_env("MAX_LLM_CALLS_PER_TURN")
MAX_LLM_CALLS_PER_TURN: int = int(_max_env or _cfg.get("max_llm_calls_per_turn", 20))

# --- Max LLM calls per agent per turn (for diversity and budget)
_max_agent_env = _from_env("MAX_LLM_CALLS_PER_AGENT_PER_TURN")
MAX_LLM_CALLS_PER_AGENT_PER_TURN: int = int(_max_agent_env or _cfg.get("max_llm_calls_per_agent_per_turn", 2))

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

# --- LLM consistency: optional double-call and compare (when True, log inconsistency; use first or rule fallback)
ENABLE_LLM_REDUNDANCY_CHECK: bool = bool(_cfg.get("enable_llm_redundancy_check", False))
LLM_AUTO_CORRECT_CONSISTENCY: bool = bool(_cfg.get("llm_auto_correct_consistency", False))

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

# --- Enable uncertainty (when False, with ENABLE_SHOCKS=False and fixed RANDOM_SEED, runs are deterministic)
_uncertainty_env = _from_env("ENABLE_UNCERTAINTY")
ENABLE_UNCERTAINTY: bool = (
    _uncertainty_env.lower() in ("true", "1", "yes") if _uncertainty_env is not None
    else bool(_cfg.get("enable_uncertainty", False))
)

# --- Stochastic event probability sampling for delayed/env events (when False, treat probability as 1.0 or 0.0)
_stoch_events = _cfg.get("enable_stochastic_events")
ENABLE_STOCHASTIC_EVENTS: bool = bool(_stoch_events) if _stoch_events is not None else ENABLE_UNCERTAINTY

# --- Compute budget per turn (soft): cost units; 1 per LLM call, 1 per MC sim. If exceeded, use deterministic fallback.
COMPUTE_BUDGET_PER_TURN: int | None = _cfg.get("compute_budget_per_turn")
if COMPUTE_BUDGET_PER_TURN is not None and not isinstance(COMPUTE_BUDGET_PER_TURN, int):
    try:
        COMPUTE_BUDGET_PER_TURN = int(COMPUTE_BUDGET_PER_TURN)
    except (ValueError, TypeError):
        COMPUTE_BUDGET_PER_TURN = None
if _from_env("COMPUTE_BUDGET_PER_TURN"):
    try:
        COMPUTE_BUDGET_PER_TURN = int(_from_env("COMPUTE_BUDGET_PER_TURN"))
    except (ValueError, TypeError):
        pass

# --- RL table max entries per agent
RL_TABLE_MAX_ENTRIES: int = int(_cfg.get("rl_table_max_entries", 50))

# --- Delta apply level flags (default True: apply variables, entities, relations)
DELTA_APPLY_VARIABLES: bool = bool(_cfg.get("delta_apply_variables", True))
DELTA_APPLY_ENTITIES: bool = bool(_cfg.get("delta_apply_entities", True))
DELTA_APPLY_RELATIONS: bool = bool(_cfg.get("delta_apply_relations", True))
_delta_gran = _cfg.get("delta_apply_granularity")
DELTA_APPLY_GRANULARITY: int | None = int(_delta_gran) if _delta_gran is not None and isinstance(_delta_gran, (int, float)) else None

# --- Event processing
MAX_EVENTS_PER_TURN: int = int(_cfg.get("max_events_per_turn", 20))

# --- Checkpoint/rollback
CHECKPOINT_ENABLED: bool = bool(_cfg.get("checkpoint_enabled", False))
CHECKPOINT_MAX_COUNT: int = int(_cfg.get("checkpoint_max_count", 10))

# --- Calibration
CALIBRATION_RECALIBRATE_TURNS: int = int(_cfg.get("calibration_recalibrate_turns", 10))
CALIBRATION_DRIFT_THRESHOLD_PCT: float = float(_cfg.get("calibration_drift_threshold_pct", 0.2))
CALIBRATION_RMSE_RED_THRESHOLD: float = float(_cfg.get("calibration_rmse_red_threshold", 3.0))
_cal_min = _cfg.get("calibration_min_interval_turns")
CALIBRATION_MIN_INTERVAL_TURNS: int | None = int(_cal_min) if _cal_min is not None else None
_cal_max = _cfg.get("calibration_max_interval_turns")
CALIBRATION_MAX_INTERVAL_TURNS: int | None = int(_cal_max) if _cal_max is not None else None

# --- Assumption impact
ASSUMPTION_HIGH_IMPACT_THRESHOLD: float = float(_cfg.get("assumption_high_impact_threshold", 0.5))

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

# --- Monte Carlo + lightweight RL (action evaluation and selection; small alpha/beta to avoid overfitting)
MC_RL_ENABLED: bool = bool(_cfg.get("mc_rl_enabled", True))
ENABLE_MC_RL: bool = bool(_cfg.get("enable_mc_rl", _cfg.get("mc_rl_enabled", True)))
MC_RL_BETA: float = float(_cfg.get("mc_rl_beta", 0.01))
MC_RL_ALPHA: float = float(_cfg.get("mc_rl_alpha", 0.01))
_mc_n_sims_raw = _cfg.get("mc_n_sims", 3)
MC_N_SIMS: int = min(5, max(1, int(_mc_n_sims_raw) if _mc_n_sims_raw is not None else 3))
MC_KEY_VARS: int = int(_cfg.get("mc_key_vars", 5))
MC_RL_TEMPERATURE: float = float(_cfg.get("mc_rl_temperature", 0.5))
MC_RL_TEMPERATURE_MIN: float = float(_cfg.get("mc_rl_temperature_min", 0.1))

# --- Belief modeling layer (optional; when disabled, no belief term in scoring)
ENABLE_BELIEF_LAYER: bool = bool(_cfg.get("enable_belief_layer", False))
BELIEF_WEIGHT: float = float(_cfg.get("belief_weight", 0.2))
BELIEF_UPDATE_RATE: float = float(_cfg.get("belief_update_rate", 0.7))
_epistemic_gap = _cfg.get("epistemic_gap_threshold")
EPISTEMIC_GAP_THRESHOLD: float = float(_epistemic_gap if _epistemic_gap is not None else 5.0)
CONFLICT_EVENT_STRICT: bool = bool(_cfg.get("conflict_event_strict", False))

# --- Research draft export (show/hide dashboard button)
ENABLE_RESEARCH_EXPORT: bool = bool(_cfg.get("enable_research_export", True))

# --- Oracle (LLM Advisor) - advisory-only, no state modification
_DASHBOARD_OVERRIDES_FILE = _PROJECT_ROOT / "config" / "dashboard_overrides.json"


def _load_dashboard_overrides() -> dict[str, Any]:
    """Read dashboard runtime overrides (e.g. enable_oracle from UI toggle)."""
    path = _DASHBOARD_OVERRIDES_FILE
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def get_enable_oracle() -> bool:
    """Return enable_oracle: dashboard override if set, else config file. Used so UI toggle takes effect on next run."""
    overrides = _load_dashboard_overrides()
    if "enable_oracle" in overrides:
        return bool(overrides["enable_oracle"])
    return bool(_cfg.get("enable_oracle", False))


ENABLE_ORACLE: bool = bool(_cfg.get("enable_oracle", False))
ORACLE_HISTORY_TURNS: int = int(_cfg.get("oracle_history_turns", 5))
ORACLE_MAX_TOKENS: int = int(_cfg.get("oracle_max_tokens", 600))
_oracle_sig = _cfg.get("oracle_significance_threshold")
ORACLE_SIGNIFICANCE_THRESHOLD: float = float(_oracle_sig if _oracle_sig is not None else 0.0)
_oracle_ssi = _cfg.get("oracle_ssi_threshold")
ORACLE_SSI_THRESHOLD: float = float(_oracle_ssi if _oracle_ssi is not None else 100.0)
_dev_thresh = _cfg.get("deviation_threshold")
DEVIATION_THRESHOLD: float = float(_dev_thresh if _dev_thresh is not None else 2.0)
_planner_decay_adj = _cfg.get("planner_decay_adjustment")
PLANNER_DECAY_ADJUSTMENT: float = float(_planner_decay_adj if _planner_decay_adj is not None else 0.05)
_belief_drift = _cfg.get("belief_drift_rate")
BELIEF_DRIFT_RATE: float = float(_belief_drift if _belief_drift is not None else 0.1)

# --- Hardening: proposal throttle, propagation, phase detection
_proposal_throttle = _cfg.get("proposal_throttle_turns")
PROPOSAL_THROTTLE_TURNS: int = int(_proposal_throttle or 3)
_prop_max_iter = _cfg.get("propagation_max_iter")
PROPAGATION_MAX_ITER: int = int(_prop_max_iter or 5)
_prop_epsilon = _cfg.get("propagation_epsilon")
PROPAGATION_EPSILON: float = float(_prop_epsilon or 1e-6)
_prop_damping = _cfg.get("propagation_damping")
PROPAGATION_DAMPING: float = float(_prop_damping or 0.6)
_prop_decay = _cfg.get("propagation_decay_factor")
PROPAGATION_DECAY_FACTOR: float = float(_prop_decay if _prop_decay is not None else 1.0)
_prop_sig = _cfg.get("propagation_significance_threshold")
PROPAGATION_SIGNIFICANCE_THRESHOLD: float = float(_prop_sig if _prop_sig is not None else 1e-6)
_flow_damping = _cfg.get("flow_damping_default")
FLOW_DAMPING_DEFAULT: float = float(_flow_damping if _flow_damping is not None else 0.8)
# --- Light propagation for planner (Unified Physics)
_light_hops = _cfg.get("light_prop_hops")
LIGHT_PROP_HOPS: int = int(_light_hops if _light_hops is not None else 1)
_planner_decay = _cfg.get("planner_decay_factor")
PLANNER_DECAY_FACTOR: float | None = float(_planner_decay) if _planner_decay is not None else None  # None = use PROPAGATION_DECAY_FACTOR
_ssi_eps = _cfg.get("ssi_epsilon")
SSI_EPSILON: float = float(_ssi_eps if _ssi_eps is not None else 1e-9)
_ssi_thresh = _cfg.get("ssi_intervention_threshold")
SSI_INTERVENTION_THRESHOLD: float = float(_ssi_thresh if _ssi_thresh is not None else 0.01)
_ssi_history = _cfg.get("ssi_history_size")
SSI_HISTORY_SIZE: int = int(_ssi_history if _ssi_history is not None else 20)
_phase_top_k = _cfg.get("phase_top_k_turns")
PHASE_TOP_K_TURNS: int = int(_phase_top_k or 3)

# --- Live Enterprise Dashboard
_dash_history = _cfg.get("dashboard_history_size")
DASHBOARD_HISTORY_SIZE: int = int(_from_env("DASHBOARD_HISTORY_SIZE") or _dash_history or 50)
_dash_enabled = _from_env("DASHBOARD_ENABLED")
DASHBOARD_ENABLED: bool = (
    _dash_enabled.lower() in ("true", "1", "yes") if _dash_enabled is not None
    else bool(_cfg.get("dashboard_enabled", True))
)

# --- Enterprise positioning (tier label only; no billing)
_enterprise_tier = _from_env("ENTERPRISE_TIER") or _cfg.get("enterprise_tier")
ENTERPRISE_TIER: str = str(_enterprise_tier or "Research Edition").strip()

# --- v2 narrative and shocks (when enable_shocks=False, no shock sampling; deterministic given seed with ENABLE_UNCERTAINTY=False)
ALLOW_NUMBERS: bool = bool(_cfg.get("allow_numbers", False))
ENABLE_SHOCKS: bool = bool(_cfg.get("enable_shocks", False))
LANG: str = str(_cfg.get("lang", "auto")).strip().lower() or "auto"

# --- Shock-driven global simulation mode (standard | shock_global)
_sim_mode = _from_env("SIMULATION_MODE") or _cfg.get("simulation_mode")
SIMULATION_MODE: str = str(_sim_mode or "standard").strip().lower()
if SIMULATION_MODE not in ("standard", "shock_global"):
    SIMULATION_MODE = "standard"
SHOCK_INTENSITY: float = max(0.0, min(1.0, float(_cfg.get("shock_intensity", 0.3))))
SHOCK_FREQUENCY: float = max(0.0, min(1.0, float(_cfg.get("shock_frequency", 0.15))))

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
        "dashboard_history_size": DASHBOARD_HISTORY_SIZE,
        "dashboard_enabled": DASHBOARD_ENABLED,
        "enterprise_tier": ENTERPRISE_TIER,
        "simulation_mode": SIMULATION_MODE,
        "shock_intensity": SHOCK_INTENSITY,
        "shock_frequency": SHOCK_FREQUENCY,
        "enable_belief_layer": ENABLE_BELIEF_LAYER,
        "belief_weight": BELIEF_WEIGHT,
        "max_llm_calls_per_agent_per_turn": MAX_LLM_CALLS_PER_AGENT_PER_TURN,
        "mc_n_sims": MC_N_SIMS,
        "mc_key_vars": MC_KEY_VARS,
        "mc_rl_temperature_min": MC_RL_TEMPERATURE_MIN,
        "enable_mc_rl": ENABLE_MC_RL,
        "compute_budget_per_turn": COMPUTE_BUDGET_PER_TURN,
        "rl_table_max_entries": RL_TABLE_MAX_ENTRIES,
        "enable_stochastic_events": ENABLE_STOCHASTIC_EVENTS,
        "delta_apply_variables": DELTA_APPLY_VARIABLES,
        "delta_apply_entities": DELTA_APPLY_ENTITIES,
        "delta_apply_relations": DELTA_APPLY_RELATIONS,
        "max_events_per_turn": MAX_EVENTS_PER_TURN,
        "checkpoint_enabled": CHECKPOINT_ENABLED,
        "checkpoint_max_count": CHECKPOINT_MAX_COUNT,
        "calibration_recalibrate_turns": CALIBRATION_RECALIBRATE_TURNS,
        "calibration_drift_threshold_pct": CALIBRATION_DRIFT_THRESHOLD_PCT,
        "calibration_rmse_red_threshold": CALIBRATION_RMSE_RED_THRESHOLD,
        "assumption_high_impact_threshold": ASSUMPTION_HIGH_IMPACT_THRESHOLD,
        "propagation_decay_factor": PROPAGATION_DECAY_FACTOR,
        "propagation_significance_threshold": PROPAGATION_SIGNIFICANCE_THRESHOLD,
        "flow_damping_default": FLOW_DAMPING_DEFAULT,
        "ssi_epsilon": SSI_EPSILON,
        "ssi_intervention_threshold": SSI_INTERVENTION_THRESHOLD,
        "ssi_history_size": SSI_HISTORY_SIZE,
        "enable_llm_redundancy_check": ENABLE_LLM_REDUNDANCY_CHECK,
        "enable_oracle": ENABLE_ORACLE,
        "oracle_history_turns": ORACLE_HISTORY_TURNS,
        "oracle_max_tokens": ORACLE_MAX_TOKENS,
    }
