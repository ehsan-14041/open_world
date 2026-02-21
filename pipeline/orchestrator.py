"""
Pipeline orchestrator: runs the 5-stage scenario modeling pipeline in strict sequential order.
Each stage receives only the output of the previous stage. No skipping or reordering.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable

from pipeline.entity_extractor import EntityExtractor
from pipeline.variable_discovery import VariableDiscoveryEngine
from pipeline.causal_graph_builder import CausalGraphBuilder
from pipeline.incentive_modeler import IncentiveModeler
from pipeline.objective_validator import validate_and_normalize_incentives
from pipeline.action_discovery import ActionDiscoveryEngine
from pipeline.model_serializer import ModelSerializer
from pipeline.errors import PipelineError

logger = logging.getLogger("open_world_engine.pipeline")

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_MAX = 50


def run_pipeline(
    scenario_text: str,
    llm_client: Callable[..., Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """
    Run the 5-stage modeling pipeline in strict sequential order.
    Returns fully structured scenario JSON compatible with the simulation engine.
    """
    scenario_text = (scenario_text or "").strip()
    if not scenario_text:
        raise PipelineError("pipeline", "Scenario text is empty")

    cache_key = hashlib.sha256(scenario_text.encode()).hexdigest()
    if cache_key in _CACHE:
        return dict(_CACHE[cache_key])

    debug = config.get("debug_llm", False)
    if debug:
        logger.debug("Pipeline start (5 stages)")

    # Stage 1: Entity Extraction
    entities = EntityExtractor.extract(scenario_text, llm_client, config)
    if debug:
        logger.debug("Stage 1 done: %d entities", len(entities))

    # Stage 2: Variable Discovery
    variables = VariableDiscoveryEngine.discover(scenario_text, entities, llm_client, config)
    if debug:
        logger.debug("Stage 2 done: %d variables", len(variables))

    # Stage 3: Causal Graph Construction
    causal_graph = CausalGraphBuilder.build(variables, scenario_text, entities, llm_client, config)
    if debug:
        logger.debug("Stage 3 done: %d causal links", len(causal_graph))

    # Stage 4: Strategic Incentive Modeling
    incentives = IncentiveModeler.model(entities, variables, scenario_text, llm_client, config)
    if debug:
        logger.debug("Stage 4 done: %d entity incentives", len(incentives))

    # Validate objectives: sign-safe, no contradictions; normalize weights
    variable_names = set(variables.keys())
    incentives = validate_and_normalize_incentives(incentives, variable_names, causal_graph)

    # Action Discovery (LLM-based, from scenario text)
    action_model = ActionDiscoveryEngine.discover(
        scenario_text, entities, variables, causal_graph, incentives, llm_client, config
    )
    if debug:
        logger.debug("Action discovery: %d actions", len(action_model.get("allowed_actions", [])))

    # Stage 5: JSON Generation
    model = {
        "description": scenario_text,
        "entities": entities,
        "variables": variables,
        "causal_graph": causal_graph,
        "incentives": incentives,
        "actions": action_model.get("allowed_actions", []),
        "action_specs": action_model.get("action_specs", {}),
        "action_tradeoffs": action_model.get("action_tradeoffs", {}),
        "per_agent_actions": action_model.get("per_agent_actions", {}),
        "strategy_classes": action_model.get("strategy_classes", {}),
        "variable_tradeoffs": None,
        "variable_specs": None,
        "rules": [],
        "events": None,
    }
    scenario = ModelSerializer.serialize(model)

    if len(_CACHE) >= _CACHE_MAX:
        for k in list(_CACHE.keys())[: _CACHE_MAX // 2]:
            del _CACHE[k]
    _CACHE[cache_key] = scenario

    if debug:
        logger.debug("Pipeline done")

    return dict(scenario)
