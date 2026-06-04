"""
OntologyManager: register attributes/entities; suggest_attribute_from_text (LLM); prune_and_merge placeholder.
Domain-agnostic: ontology derives from scenario variables, relations, and scenario-defined actors only.
No predefined semantic labels (e.g. founder, investor); new attributes come from meta_proposals or LLM suggestion.
"""

from __future__ import annotations

from typing import Any

from core.llm_service import call_llm as llm_service_call

# Prompt template for ontology suggestion (in code per plan)
# Ontology suggestion prompt: to propose new attribute names/specs when relevant.
ONTOLOGY_SUGGESTION_SYSTEM = """You propose new world-model attributes when given context.
Reply with a single JSON object: { "name": "attribute_name", "entity_type": "string", "spec": { "range": [min, max], "decay": 0.0, "units": "optional" } }.
If nothing relevant, return { "name": "", "entity_type": "", "spec": {} }."""


class OntologyManager:
    """Registry of entity types and attributes with metadata; LLM-based suggestion."""

    def __init__(self) -> None:
        self._attributes: dict[str, dict[str, Any]] = {}  # (entity_type, attr_name) -> spec
        self._entity_types: set[str] = set()

    def register_attribute(self, entity_type: str, attr_name: str, spec: dict[str, Any]) -> None:
        """Store attribute spec (range, decay, units, etc.) for entity_type."""
        self._entity_types.add(entity_type)
        key = f"{entity_type}:{attr_name}"
        self._attributes[key] = dict(spec)

    def suggest_attribute_from_text(self, text_or_context: str) -> dict[str, Any]:
        """Use LLM to propose new attribute name/spec from context. Returns parsed dict or empty."""
        try:
            out = llm_service_call(
                f"Context: {text_or_context[:1000]}\nPropose a new attribute if relevant, else empty name.",
                system=ONTOLOGY_SUGGESTION_SYSTEM,
                schema={"required": [], "types": {}},
                temperature=None,
                max_tokens=None,
                usage_tier="ontology_suggestion",
            )
            if isinstance(out, dict) and out.get("name"):
                return out
        except Exception:
            pass
        return {"name": "", "entity_type": "", "spec": {}}

    def prune_and_merge(self) -> None:
        """Placeholder: simple dedupe by name or no-op."""
        # No-op for demo
        pass

    def get_spec(self, entity_type: str, attr_name: str) -> dict[str, Any] | None:
        """Return registered spec for (entity_type, attr_name) or None."""
        return self._attributes.get(f"{entity_type}:{attr_name}")
