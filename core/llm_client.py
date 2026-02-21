"""
LLM client: reuse sim_app's client when available; otherwise fallback with openai + env.
API key: set OPENAI_API_KEY (or use sim_app settings when run from repo). See INTEGRATION_NOTES.md to swap in real client.
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

# Debug: set via config/settings DEBUG_LLM; log inputs/outputs, never log raw API keys
_DEBUG = False

# In-memory log of LLM calls for UI inspection (last N entries)
_LLM_LOG: list[dict[str, Any]] = []
_LLM_LOG_MAX = 100


def append_llm_log(entry: dict[str, Any]) -> None:
    """Append an LLM call log entry. Used internally by call_llm."""
    global _LLM_LOG
    _LLM_LOG.append(entry)
    if len(_LLM_LOG) > _LLM_LOG_MAX:
        _LLM_LOG = _LLM_LOG[-_LLM_LOG_MAX:]


def get_llm_logs() -> list[dict[str, Any]]:
    """Return copy of LLM call log (for API)."""
    return list(_LLM_LOG)


def clear_llm_logs() -> None:
    """Clear the LLM call log."""
    global _LLM_LOG
    _LLM_LOG = []


def _strip_markdown_json(raw: str) -> str:
    """Strip markdown code block if present."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _mask_key(key: str | None) -> str:
    if not key or len(key) < 8:
        return "***"
    return key[:4] + "..." + key[-4:] if len(key) > 8 else "***"


def _call_llm_sim_app(
    prompt: str,
    system: str | None,
    as_json: bool,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str | dict:
    """Use sim_app's generate_json/generate_text and config. Add sim_app to path."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    sim_app_path = repo_root / "sim_app"
    if not sim_app_path.is_dir():
        raise ImportError("sim_app not found")
    if str(sim_app_path) not in sys.path:
        sys.path.insert(0, str(sim_app_path))
    from llm_client import generate_json, generate_text
    from config import get_llm_provider_config

    try:
        from config.settings import LLM_PROVIDER as _owe_provider
        provider = (_owe_provider or "avalai").strip().lower()
    except Exception:
        provider = "avalai"
    if provider not in ("groq", "avalai"):
        provider = "avalai"
    cfg = get_llm_provider_config(provider)
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("LLM API key not set. Set GROQ_API_KEY or AVALAI_API_KEY in env or sim_app settings.")
    messages = [{"role": "user", "content": prompt}]
    if system:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    if as_json:
        content, usage = generate_json(
            messages,
            base_url=cfg["base_url"],
            api_key=api_key,
            model=cfg["model"],
            temperature=temperature if temperature is not None else cfg.get("temperature", 0.2),
            max_tokens=max_tokens if max_tokens is not None else cfg.get("max_tokens", 512),
            timeout=cfg.get("timeout", 15),
            response_format={"type": "json_object"},
        )
        raw = _strip_markdown_json(content)
        if _DEBUG:
            import logging
            logging.getLogger("open_world_engine.llm").debug("LLM out (redacted): %s", _mask_key(api_key) and "***")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise
    else:
        content, _ = generate_text(
            messages,
            base_url=cfg["base_url"],
            api_key=api_key,
            model=cfg["model"],
            temperature=temperature if temperature is not None else cfg.get("temperature", 0.2),
            max_tokens=max_tokens if max_tokens is not None else cfg.get("max_tokens", 512),
            timeout=cfg.get("timeout", 15),
        )
        return content.strip()


def _call_llm_fallback(
    prompt: str,
    system: str | None,
    as_json: bool,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str | dict:
    """Standalone: use AvalAI if configured, else OpenAI-compatible env/config."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package required. pip install openai>=1.0.0") from None

    from config.settings import (
        AVALAI_API_KEY,
        AVALAI_BASE_URL,
        AVALAI_MODEL,
        AVALAI_TEMPERATURE,
        AVALAI_MAX_TOKENS,
        AVALAI_TIMEOUT,
        OPENAI_API_KEY,
        OPENAI_BASE_URL,
        OPENAI_MODEL,
    )

    if (AVALAI_API_KEY or "").strip():
        api_key = AVALAI_API_KEY.strip()
        base_url = (AVALAI_BASE_URL or "https://api.avalai.ir/v1").strip()
        model = (AVALAI_MODEL or "gpt-4o-mini").strip()
        _temp = AVALAI_TEMPERATURE
        _tokens = AVALAI_MAX_TOKENS
        timeout = AVALAI_TIMEOUT
    elif (OPENAI_API_KEY or "").strip():
        api_key = OPENAI_API_KEY.strip()
        base_url = (OPENAI_BASE_URL or "https://api.openai.com/v1").strip()
        model = (OPENAI_MODEL or "gpt-4o-mini").strip()
        _temp = 0.2
        _tokens = 512
        timeout = 15
    else:
        raise ValueError(
            "LLM API key not set. Set AVALAI_API_KEY or OPENAI_API_KEY in config/settings.json or env. See README."
        )

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    messages = [{"role": "user", "content": prompt}]
    if system:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    use_temp = temperature if temperature is not None else _temp
    use_tokens = max_tokens if max_tokens is not None else _tokens
    kwargs = {"model": model, "messages": messages, "temperature": use_temp, "max_tokens": use_tokens}
    if as_json:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    content = (resp.choices[0].message.content or "").strip() if resp.choices else ""
    if _DEBUG:
        import logging
        logging.getLogger("open_world_engine.llm").debug("LLM out (key redacted)")
    if as_json:
        raw = _strip_markdown_json(content)
        return json.loads(raw)
    return content


def _format_response_for_log(val: str | dict) -> str:
    """Format LLM response for log display."""
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False, indent=2)
    return str(val)


def call_llm(
    prompt: str,
    system: str | None = None,
    *,
    as_json: bool = False,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str | dict:
    """
    Call LLM with optional system prompt. Returns string or (if as_json=True) parsed dict.
    Uses sim_app's client when available; otherwise fallback openai + config/settings.
    On JSON parse failure: retry once with corrective prompt; then raise or return {} per caller.
    Each successful call is logged for UI inspection via get_llm_logs().
    """
    global _DEBUG
    try:
        from config.settings import DEBUG_LLM
        _DEBUG = DEBUG_LLM
    except Exception:
        pass

    def do_call(use_fallback: bool, p: str, s: str | None, aj: bool) -> str | dict:
        kwargs = {}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if use_fallback:
            return _call_llm_fallback(p, s, aj, **kwargs)
        return _call_llm_sim_app(p, s, aj, **kwargs)

    def log_and_return(result: str | dict, used_prompt: str, used_system: str | None) -> str | dict:
        append_llm_log({
            "ts": time.time(),
            "system": used_system or "",
            "prompt": used_prompt,
            "response": _format_response_for_log(result),
            "as_json": as_json,
        })
        return result

    try:
        out = do_call(use_fallback=False, p=prompt, s=system, aj=as_json)
        return log_and_return(out, prompt, system)
    except (ImportError, ValueError) as e:
        if "sim_app" in str(e) or "API key" in str(e):
            try:
                out = do_call(use_fallback=True, p=prompt, s=system, aj=as_json)
                return log_and_return(out, prompt, system)
            except json.JSONDecodeError as je:
                if as_json:
                    retry_prompt = prompt + "\n\nPrevious response was invalid JSON. Reply with ONLY a valid JSON object."
                    try:
                        out = do_call(use_fallback=True, p=retry_prompt, s=system, aj=as_json)
                        if isinstance(out, dict):
                            return log_and_return(out, retry_prompt, system)
                        raw = _strip_markdown_json(str(out))
                        return log_and_return(json.loads(raw), retry_prompt, system)
                    except Exception:
                        return log_and_return({}, retry_prompt, system)
                raise je
        raise
    except json.JSONDecodeError as je:
        if as_json:
            retry_prompt = prompt + "\n\nOutput must be valid JSON only. Reply with a single JSON object."
            try:
                out = _call_llm_sim_app(
                    retry_prompt, system, as_json=False,
                    temperature=temperature, max_tokens=max_tokens,
                )
                raw = _strip_markdown_json(str(out))
                return log_and_return(json.loads(raw), retry_prompt, system)
            except Exception:
                try:
                    out = _call_llm_fallback(
                        retry_prompt, system, as_json=False,
                        temperature=temperature, max_tokens=max_tokens,
                    )
                    raw = _strip_markdown_json(str(out))
                    return log_and_return(json.loads(raw), retry_prompt, system)
                except Exception:
                    return log_and_return({}, retry_prompt, system)
        raise je
