"""
Narrative: token substitution {{var:ID}} / {{delta:ID}} from authoritative snapshot.
Integrity: mismatch or unresolved -> fallback or regenerate. Lang auto-detect (fa/en).
"""

from __future__ import annotations

import re
from typing import Any


def detect_lang_from_scenario(scenario: dict[str, Any]) -> str:
    """Auto-detect language from scenario text/description. Returns 'fa' or 'en'. Re-exports summarization.lang."""
    from summarization.lang import detect_narrative_language_from_scenario
    return detect_narrative_language_from_scenario(scenario)


def substitute_narrative_tokens(
    prose: str,
    snapshot: dict[str, Any],
    *,
    deltas: dict[str, float] | None = None,
    epsilon: float = 1e-6,
) -> tuple[str, bool]:
    """
    Replace {{var:ID}} with snapshot.variables[ID] and {{delta:ID}} with deltas[ID].
    Also supports {{DELTA:var:value}} pattern. Returns (substituted_prose, all_resolved).
    If a token cannot be resolved, leave placeholder and set all_resolved=False.
    """
    deltas = deltas or {}
    variables = snapshot.get("variables") or snapshot.get("global_state") or {}
    all_resolved = True

    # {{var:var_id}}
    def repl_var(m: re.Match) -> str:
        nonlocal all_resolved
        var_id = (m.group(1) or "").strip()
        if var_id in variables:
            v = variables[var_id]
            if isinstance(v, (int, float)):
                return str(v)
            return str(v)
        all_resolved = False
        return m.group(0)

    out = re.sub(r"\{\{var:([^}]+)\}\}", repl_var, prose)

    # {{delta:var_id}} or {{DELTA:var_id:value}}
    def repl_delta(m: re.Match) -> str:
        nonlocal all_resolved
        var_id = (m.group(1) or "").strip()
        if var_id in deltas:
            return str(deltas[var_id])
        all_resolved = False
        return m.group(0)

    out = re.sub(r"\{\{delta:([^}]+)\}\}", repl_delta, out, flags=re.IGNORECASE)
    out = re.sub(r"\{\{DELTA:([^:}]+):[^}]*\}\}", repl_delta, out)
    return out, all_resolved
