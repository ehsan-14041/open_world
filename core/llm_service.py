"""
LLM service: centralize LLM calls, retries, schema parsing, and lightweight caching.
Wraps core/llm_client with schema validation, repair-once, and cache_key support.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any, Callable

from core.llm_client import call_llm as _call_llm

_logger = logging.getLogger(__name__)

try:
    # Optional import: when config is unavailable (e.g. very early in bootstrap),
    # LLM_USAGE_Tiers falls back to an empty mapping and call sites can still
    # pass explicit temperature/max_tokens.
    from config.settings import LLM_USAGE_TIERS as _LLM_USAGE_TIERS  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    _LLM_USAGE_TIERS: dict[str, dict[str, Any]] = {}

# In-memory LRU cache for repeated predictions (e.g., planner simulations)
_CACHE: dict[str, tuple[Any, float]] = {}
_CACHE_MAX_SIZE = 256
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _strip_markdown_json(raw: str) -> str:
    """Strip markdown code block if present."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _validate_schema(obj: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, str]:
    """
    Lightweight schema validation: check required keys exist and types match.
    schema: {"required": ["key1", "key2"], "types": {"key1": "dict", "key2": "list"}}
    Returns (ok, error_message).
    """
    if not isinstance(obj, dict):
        return False, "Expected dict"
    required = schema.get("required") or []
    for key in required:
        if key not in obj:
            return False, f"Missing required key: {key}"
    types_map = schema.get("types") or {}
    for key, expected_type in types_map.items():
        if key not in obj:
            continue
        val = obj[key]
        if expected_type == "dict" and not isinstance(val, dict):
            return False, f"Key '{key}' must be dict"
        if expected_type == "list" and not isinstance(val, list):
            return False, f"Key '{key}' must be list"
        if expected_type == "str" and not isinstance(val, str):
            return False, f"Key '{key}' must be str"
        if expected_type == "number" and not isinstance(val, (int, float)):
            return False, f"Key '{key}' must be number"
    return True, ""


class CachePolicy:
    """
    Lightweight cache policy hints for call sites.
    Callers can use these with helper functions (e.g. make_cache_key) to
    decide when to enable caching without changing the core call_llm API.
    """

    NO_CACHE = "no_cache"
    TURN_CACHE = "turn_cache"
    RUN_CACHE = "run_cache"


def call_llm(
    prompt: str,
    system: str,
    *,
    schema: dict[str, Any] | None = None,
    temperature: float = 0.0,
    max_tokens: int = 512,
    retry: int = 1,
    cache_key: str | None = None,
    client_fn: Callable[..., Any] | None = None,
    usage_tier: str | None = None,
    budget_key: str | None = None,
) -> dict | str | None:
    """
    Call LLM with optional schema validation and caching.

    Args:
        prompt: User prompt.
        system: System prompt.
        schema: Optional schema for JSON validation. If provided, parses JSON and validates.
        temperature: LLM temperature (default 0.0).
        max_tokens: Max tokens (default 512).
        retry: Number of repair attempts on parse failure (default 1).
        cache_key: Optional cache key for repeated predictions. If hit, return cached.
        client_fn: Optional custom client (prompt, system, as_json, temperature, max_tokens).
                  If None, uses core.llm_client.call_llm.

    Returns:
        If schema provided: validated dict or None on failure.
        Else: raw str or None.
        On parse/validation failure after retries: None.
    """
    client = client_fn or _default_client

    # Map usage_tier/budget_key to default temperature/max_tokens when callers
    # explicitly opt into tiering by passing None for those fields.
    tier = usage_tier or budget_key
    if tier and tier in _LLM_USAGE_TIERS:
        tier_conf = _LLM_USAGE_TIERS.get(tier) or {}
        if temperature is None and isinstance(tier_conf.get("temperature"), (int, float)):
            temperature = float(tier_conf["temperature"])
        if max_tokens is None and isinstance(tier_conf.get("max_tokens"), (int, float)):
            max_tokens = int(tier_conf["max_tokens"])

    if cache_key:
        if cache_key in _CACHE:
            cached_val, cached_ts = _CACHE[cache_key]
            if time.time() - cached_ts < _CACHE_TTL_SECONDS:
                _logger.debug("llm_service cache hit: %s", cache_key[:32])
                return cached_val
        # Evict oldest if at capacity
        if len(_CACHE) >= _CACHE_MAX_SIZE:
            oldest = min(_CACHE.items(), key=lambda x: x[1][1])
            del _CACHE[oldest[0]]

    repair_instruction = (
        "\n\nOutput must be valid JSON only. Reply with a single JSON object matching the required schema. No markdown, no explanation."
    )

    for attempt in range(retry + 1):
        try:
            start = time.time()
            out = client(prompt, system, as_json=(schema is not None), temperature=temperature, max_tokens=max_tokens)
            latency_ms = (time.time() - start) * 1000

            if schema is None:
                result = out if isinstance(out, str) else str(out)
                if cache_key:
                    _CACHE[cache_key] = (result, time.time())
                return result

            # Parse JSON if needed
            if isinstance(out, str):
                raw = _strip_markdown_json(out)
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    if attempt < retry:
                        prompt = prompt + repair_instruction
                        continue
                    _logger.warning("llm_service: JSON parse failed after %d attempts", attempt + 1)
                    return None
            else:
                parsed = out

            if not isinstance(parsed, dict):
                # Normalize list responses to dict when schema allows
                if isinstance(parsed, list) and schema:
                    required = schema.get("required") or []
                    types_map = schema.get("types") or {}
                    if "events" in required and types_map.get("events") == "list":
                        parsed = {"events": parsed}
                    elif not required and not types_map:
                        # Empty schema (e.g. candidate_actions): wrap list for caller
                        if parsed and all(isinstance(x, str) for x in parsed):
                            parsed = {"actions": parsed}
                        elif parsed and all(isinstance(x, dict) for x in parsed):
                            parsed = {"candidates": parsed}
                        else:
                            parsed = {"items": parsed}
                    else:
                        parsed = None
                if parsed is None:
                    if attempt < retry:
                        prompt = prompt + repair_instruction
                        continue
                    _logger.warning("llm_service: expected dict, got list (could not normalize)")
                    return None

            # Schema validation
            ok, err = _validate_schema(parsed, schema)
            if not ok:
                if attempt < retry:
                    prompt = prompt + repair_instruction + f"\nValidation error: {err}"
                    continue
                _logger.warning("llm_service: schema validation failed: %s", err)
                return None

            if cache_key:
                _CACHE[cache_key] = (parsed, time.time())
            _logger.debug("llm_service: latency=%.0fms attempts=%d", latency_ms, attempt + 1)
            return parsed

        except Exception as e:
            _logger.debug("llm_service attempt %d failed: %s", attempt + 1, e)
            if attempt < retry:
                prompt = prompt + repair_instruction
                continue
            raise

    return None


def _default_client(
    prompt: str,
    system: str | None,
    *,
    as_json: bool = False,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str | dict:
    """Default client wrapper around core.llm_client.call_llm."""
    return _call_llm(
        prompt,
        system=system,
        as_json=as_json,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def make_cache_key(action: str, snapshot_hash: str) -> str:
    """
    Build cache key for planner simulations.

    This helper is intentionally simple and deterministic so it can be reused
    across hot-path call sites (e.g., WorldModelAgent.normalize_proposal)
    without leaking domain-specific details into prompts.
    """
    raw = json.dumps(
        {
            "kind": "plan",
            "action": action,
            "snapshot": snapshot_hash,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clear_cache() -> None:
    """Clear the llm_service cache."""
    global _CACHE
    _CACHE = {}
