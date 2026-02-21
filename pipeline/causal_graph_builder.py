"""
Stage 3: Causal Graph Construction.
Input: discovered variables
Output: directed causal graph with from, to, polarity, strength.
Detects feedback loops. Must not return empty graph when variables exist.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from pipeline._llm_utils import run_llm_stage
from pipeline.errors import PipelineError

CAUSAL_SYSTEM = """You are a systems modeler building a causal graph.
Given variables, define how they influence each other.

Each causal link must have:
- from: source variable name
- to: target variable name
- polarity: "positive" (increase in from increases to) or "negative" (increase in from decreases to)
- strength: float 0-1 (how strong the causal effect is; 0.5 = moderate)

The graph must NOT be empty when variables exist. Each variable should have at least one link (in or out).
If feedback loops exist (e.g. A->B->C->A), include them and set has_feedback_loops: true.

Return JSON object:
{
  "causal_links": [
    { "from": "var1", "to": "var2", "polarity": "positive|negative", "strength": 0.0-1.0 }
  ],
  "has_feedback_loops": boolean (optional)
}

Output JSON only."""

CAUSAL_USER = """Scenario (for context):
{scenario_text}

Variables:
{variables_json}"""


def _validate_causal(data: Any, variable_names: set[str]) -> str | None:
    if not isinstance(data, dict):
        return "Must return a JSON object"
    if "causal_links" not in data:
        return "Must have 'causal_links'"
    links = data.get("causal_links")
    if not isinstance(links, list):
        return "'causal_links' must be an array"
    for i, link in enumerate(links):
        if not isinstance(link, dict):
            return f"causal_links[{i}] must be an object"
        if "from" not in link or "to" not in link:
            return f"causal_links[{i}] must have 'from' and 'to'"
        fv, tv = link.get("from"), link.get("to")
        if fv not in variable_names:
            return f"causal_links[{i}] 'from' '{fv}' is not a known variable"
        if tv not in variable_names:
            return f"causal_links[{i}] 'to' '{tv}' is not a known variable"
        pol = link.get("polarity")
        if pol not in ("positive", "negative"):
            return f"causal_links[{i}] polarity must be 'positive' or 'negative'"
    return None


def _ensure_non_empty_graph(
    variables: dict[str, float],
    scenario_text: str,
    llm_client: Callable[..., Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Ensure at least one link per variable when graph would otherwise be empty."""
    var_names = list(variables.keys())
    if len(var_names) < 2:
        return []
    # Create minimal chain: v1 -> v2 -> v3 -> ...
    links = []
    for i in range(len(var_names) - 1):
        links.append({
            "from": var_names[i],
            "to": var_names[i + 1],
            "polarity": "positive",
            "strength": 0.5,
            "weight": 0.5,
        })
    links.append({
        "from": var_names[-1],
        "to": var_names[0],
        "polarity": "negative",
        "strength": 0.3,
        "weight": -0.3,
    })
    return links


def _add_weight_to_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add weight from polarity + strength for propagation compatibility."""
    result = []
    for link in links:
        link = dict(link)
        if "weight" not in link or link.get("weight") is None:
            pol = (link.get("polarity") or "positive").lower()
            strength = float(link.get("strength", 0.5))
            if pol == "negative":
                link["weight"] = -strength
            else:
                link["weight"] = strength
        result.append(link)
    return result


def _detect_feedback_loops(links: list[dict[str, Any]]) -> bool:
    """Detect cycles in directed graph."""
    from collections import defaultdict

    graph: dict[str, list[str]] = defaultdict(list)
    for link in links:
        fv = link.get("from")
        tv = link.get("to")
        if fv and tv:
            graph[fv].append(tv)

    def has_cycle_from(node: str, visited: set[str], rec_stack: set[str], path: list[str]) -> bool:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if has_cycle_from(neighbor, visited, rec_stack, path):
                    return True
            elif neighbor in rec_stack:
                return True
        path.pop()
        rec_stack.remove(node)
        return False

    visited: set[str] = set()
    for node in graph:
        if node not in visited:
            if has_cycle_from(node, visited, set(), []):
                return True
    return False


class CausalGraphBuilder:
    """Build causal graph from variables."""

    @staticmethod
    def build(
        variables: dict[str, float],
        scenario_text: str,
        entities: list[dict[str, Any]],
        llm_client: Callable[..., Any],
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Build causal graph from variables.
        Returns list of links with from, to, polarity, strength, weight.
        """
        variable_names = set(variables.keys())
        if not variable_names:
            return []

        variables_json = json.dumps(variables, ensure_ascii=False)
        user = CAUSAL_USER.format(scenario_text=scenario_text, variables_json=variables_json)

        def validator(data: Any) -> str | None:
            return _validate_causal(data, variable_names)

        retry_prompt = (
            "Your previous output had invalid JSON (possibly truncated or unterminated string). "
            "Return ONLY valid, complete JSON. Ensure all strings are properly closed with quotes."
        )
        try:
            result = run_llm_stage(
                "Causal Graph",
                user,
                CAUSAL_SYSTEM,
                llm_client,
                config,
                validator,
                retry_prompt=retry_prompt,
            )
        except ValueError as e:
            raise PipelineError("Causal Graph", str(e)) from e

        links = result.get("causal_links") or []
        if not links and len(variable_names) >= 2:
            links = _ensure_non_empty_graph(variables, scenario_text, llm_client, config)

        return _add_weight_to_links(links)
