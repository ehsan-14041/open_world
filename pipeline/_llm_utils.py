"""Shared LLM utilities for pipeline stages."""

from __future__ import annotations

import json
import re
from typing import Any, Callable


def strip_markdown_json(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _repair_truncated_json(s: str, error: json.JSONDecodeError) -> str:
    """Attempt to repair JSON truncated with an unterminated string."""
    if "Unterminated string" not in str(error):
        return s
    # Close the unterminated string
    repair = s.rstrip()
    if not repair.endswith('"'):
        repair += '"'
    # Build closing delimiters in correct order (reverse of opening)
    stack: list[str] = []
    in_string = False
    escape = False
    i = 0
    while i < len(repair):
        c = repair[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            stack.append("}")
        elif c == "[":
            stack.append("]")
        elif c in "}]":
            if stack and stack[-1] == c:
                stack.pop()
        i += 1
    repair += "".join(reversed(stack))
    return repair


def parse_json_response(raw: str | dict | list, stage_name: str) -> dict[str, Any] | list[Any]:
    """Parse LLM response to JSON. Attempts repair for truncated/unterminated strings."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return raw
    s = strip_markdown_json(str(raw))
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        if "Unterminated string" in str(e):
            try:
                repaired = _repair_truncated_json(s, e)
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Invalid JSON: {e}") from e


def run_llm_stage(
    stage_name: str,
    user_prompt: str,
    system_prompt: str,
    llm_client: Callable[..., Any],
    config: dict[str, Any],
    validator: Callable[[Any], str | None],
    retry_prompt: str = "Your previous output was invalid. Return ONLY valid JSON.",
) -> Any:
    """Run one LLM stage with optional retry."""
    debug = config.get("debug_llm", False)
    last_error: Exception | None = None
    prompt = user_prompt
    for attempt in range(2):
        try:
            out = llm_client(prompt, system=system_prompt, as_json=True)
            parsed = parse_json_response(out, stage_name)
            err = validator(parsed)
            if err:
                last_error = ValueError(err)
                if attempt == 0:
                    prompt = prompt + "\n\n" + retry_prompt
                    continue
                raise last_error
            return parsed
        except Exception as e:
            last_error = e
            if attempt == 0:
                prompt = prompt + "\n\n" + retry_prompt
                continue
            raise
    if last_error:
        raise last_error
    raise ValueError("Validation failed after retry")


# Placeholder name patterns to reject
PLACEHOLDER_PATTERNS = (
    r"^actor_\d+$",
    r"^agent_\d+$",
    r"^faction_[a-z]$",
    r"^agent$",
    r"^actor$",
)


def is_placeholder_name(name: str) -> bool:
    """Return True if name is a generic placeholder (actor_1, agent_2, etc.)."""
    if not name or not isinstance(name, str):
        return True
    n = name.strip().lower()
    for pat in PLACEHOLDER_PATTERNS:
        if re.match(pat, n):
            return True
    return False
