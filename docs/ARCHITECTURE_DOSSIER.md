# Open World Engine — Architecture Dossier

**Document Version:** 1.4  
**Scope:** Full repository traversal, structural analysis, no code modifications.  
**Base Path:** `/root/agent/open_world_engine2`

---

# 1. High-Level System Overview

## Core Purpose

Multi-agent social simulation engine with a causal variable graph. Agents observe world state, propose actions (deltas), and the engine applies validated changes with propagation, governance, and event processing.

## Main Runtime Loop

```
SimulationLoop.run(steps)
  → for i in range(steps): loop.step()
    → world.snapshot()
    → [optional] EnvironmentAgent.propose() → append events to world.events
    → world_summarize(snapshot)
    → for each agent: agent.propose(agent_input) → extract/validate/sanitize → Delta
    → merge deltas → apply_all_constraints → world.apply_delta(combined_delta)
    → process_delayed_events, run_rules
    → agent.memory.add_event, update_beliefs, reflect
```

## System Type

**Hybrid:** Agent-based simulation with LLM-assisted decision-making, rule-based planning fallback, deterministic propagation, and optional stochastic components (noise, event probability, instability mode).

---

# 2. Module Graph

## 2.1 Entry Points

| File | Responsibility | Depends On | Used By | Key Classes | Key Functions |
|------|----------------|------------|---------|-------------|---------------|
| `main.py` | CLI entry | config, schemas, simulation, core.narrative_builder, core.llm_client | User | — | `main()` |
| `ui.py` | Flask web UI | scenario_parser, schemas, simulation, core, visualization | User | — | `app`, `main()` |
| `scenario_parser.py` | Parse scenario text/path → scenario dict | core.scenario_compiler, schemas | main, ui | — | `parse_scenario_text()`, `load_scenario()` |

## 2.2 Simulation

| File | Responsibility | Depends On | Used By | Key Classes | Key Functions |
|------|----------------|------------|---------|-------------|---------------|
| `simulation/loop.py` | Main loop: collect proposals, normalize, validate, apply, propagation, delayed_events, rules, reflect | config, core.*, agents.*, schemas, core.action_definitions_store, core.delta_attribution | main, ui | `SimulationLoop` | `step()`, `run()`, `load_scenario()` |

## 2.3 Agents

| File | Responsibility | Depends On | Used By | Key Classes | Key Functions |
|------|----------------|------------|---------|-------------|---------------|
| `agents/base_agent.py` | Memory, goals, utility, planning flow | schemas.proposal_schema, agents.memory, agents.planner, agents.utility | agents.agents | `BaseAgent` | `propose()`, `reflect()`, `rule_based_deltas_for_snapshot()` |
| `agents/agents.py` | RoleAgent, agent construction from scenario | proposal_schema, base_agent, memory, agent_constructor, llm_service | simulation.loop | `RoleAgent` | `propose()`, `generate_candidate_actions()`, `get_agents_from_scenario()` |
| `agents/planner.py` | Depth-2 planning, clone/apply for simulation | agents.utility, core.world_state | base_agent | — | `plan_depth2()`, `plan_depth2_with_callback()`, `clone_world_state()`, `apply_delta_to_state()` |
| `agents/world_model_agent.py` | Proposal → Delta via LLM | core.llm_service, schemas | simulation.loop (get_delta callback) | `WorldModelAgent` | `normalize_proposal()` |
| `agents/environment_agent.py` | Propose 0–2 events per turn | core.llm_service, schemas.meta_schema | simulation.loop | `EnvironmentAgent` | `propose()` |
| `agents/memory.py` | Episodic memory, beliefs, beliefs update | core.observation | base_agent, agents | `AgentMemory` | `add_event()`, `update_beliefs()`, `get_relevant_context()` |
| `agents/utility.py` | Utility scoring, goals from objectives | — | planner, base_agent | — | `utility_function()`, `evaluate_short_term_goals()`, `goals_from_objectives()` |

## 2.4 Core

| File | Responsibility | Depends On | Used By | Key Classes | Key Functions |
|------|----------------|------------|---------|-------------|---------------|
| `core/llm_client.py` | LLM API calls (sim_app or OpenAI fallback) | config, openai | llm_service, main, ui, scenario_parser, ontology_manager | — | `call_llm()`, `get_llm_logs()`, `clear_llm_logs()` |
| `core/llm_service.py` | Schema validation, retries, caching | core.llm_client | agents, world_model_agent, environment_agent | — | `call_llm()`, `make_cache_key()`, `clear_cache()` |
| `core/world_model.py` | Composite world state, apply_delta, propagation | schemas.delta_schema, propagation, delayed_events, event_queue | simulation.loop | `WorldModel` | `apply_delta()`, `snapshot()`, `load_snapshot()`, `process_delayed_events()` |
| `core/world_state.py` | Lightweight clone/apply for planning | schemas.delta_schema | planner (plan_depth2_llm_aware) | `WorldState` | `from_snapshot()`, `apply_delta()`, `clone()` |
| `core/world_summarizer.py` | Snapshot → text summary | — | simulation.loop | — | `summarize()` |
| `core/propagation.py` | Causal propagation along causal_links | — | world_model | — | `propagate_variable_changes()` |
| `core/governance.py` | Policy rules, validate_delta, auto-repair | schemas.delta_schema | simulation.loop | `Governance`, `PolicyRule` | `validate_delta()`, `approve_meta_proposal()` |
| `core/llm_action_guard.py` | Extract/validate/sanitize LLM JSON | schemas.llm_action_schema, strategic_action_schema | simulation.loop | `LLMActionGuard` | `extract_json()`, `validate()`, `sanitize()` |
| `core/soft_constraints.py` | Rate limit, change budget, diminishing returns, hard clip | — | simulation.loop | — | `apply_all_constraints()`, `apply_soft_constraints()`, `apply_hard_clip()` |
| `core/event_queue.py` | Events at trigger_turn, handler registry | schemas.delta_schema | world_model | — | `process_events_for_turn()`, `register_event_handler()` |
| `core/rule_engine.py` | Condition/effect rules from scenario | — | simulation.loop | — | `run_rules()`, `register_condition()`, `register_effect()` |
| `core/action_interpreter.py` | action_spec → Delta | config, schemas.delta_schema | — | — | `interpret_action_spec_with_world()` |
| `core/ontology_manager.py` | Attribute registry, ontology suggestions | core.llm_client | simulation.loop | `OntologyManager` | `register_attribute()`, `suggest_attribute_from_text()` |
| `core/agent_constructor.py` | Build agents from scenario (LLM or rule-based) | — | agents.agents | — | `construct_agents_from_scenario()`, `allowed_actions_from_variables()` |
| `core/agent_generator.py` | LLM agent definitions from scenario | — | main | — | `generate_agents_from_scenario()` |
| `core/scenario_compiler.py` | Multi-stage LLM scenario compilation | — | scenario_parser | — | `compile_scenario()` |
| `core/prompt_builder.py` | Decision prompt template | — | agents.agents | — | `build_decision_prompt()` |
| `core/strategic_prompt.py` | Strategic format prompt | — | agents.agents | — | `build_strategic_prompt()` |
| `core/narrative_builder.py` | Trace → narrative prose; Layer 1 facts + Layer 2 weaving | core.narrative_synthesizer, summarization.facts, summarization.lang, summarization.llm_narrator, summarization.renderer, summarization.validators | main, ui | — | `build_narrative()`, `build_structured_summary()` |
| `core/narrative_synthesizer.py` | Structured narrative phases, turning points, pattern classification | — | narrative_builder | — | `build_structured_narrative_summary()`, `format_structured_summary_prose()`, `infer_agent_display_names()` |
| `core/option_selector.py` | Select from 3 options (rule-based or LLM) | schemas.meta_schema | option_set_builder, simulation.loop | — | `select_option_rule_based()`, `_select_via_llm()` |
| `core/option_set_builder.py` | Build OptionSet (max 3) from actions, capability/availability filter | core.option_selector, core.action_definitions_store | simulation.loop | — | `build_option_set()` |
| `core/phase_detector.py` | Importance scoring, phase detection, regime shifts | — | narrative_builder, narrative_synthesizer | — | Phase detection from turn_records |
| `core/action_definitions_store.py` | Action definitions from scenario, delta_vector per action | schemas | simulation.loop | — | `build_action_definitions_from_scenario()`, `get_delta_vector()` |
| `core/delta_attribution.py` | Merge delta_raw, compute self_effect per agent | — | simulation.loop | — | `merge_delta_raw()`, `compute_self_effect_per_agent()` |
| `core/attribution_layer.py` | Human-readable attribution sentences (action → variable change) | — | scenario_analysis_output | — | `build_attribution_sentences()` |
| `core/delta_aggregation.py` | Aggregate per-turn deltas, action impact summary | — | scenario_analysis_output | — | `compute_global_delta()`, `compute_action_impact_summary()`, `summarize_action_impact_by_action_id()` |
| `core/convergence_analysis.py` | Convergence/oscillation analysis from provenance | — | scenario_analysis_output | — | `analyze_convergence()` |
| `core/scenario_analysis_output.py` | Logic Core (JSON) and Executive Summary | attribution_layer, delta_aggregation, convergence_analysis | main | — | `build_scenario_analysis_output()`, `build_logic_core()` |
| `core/proposal_normalizer.py` | Qualitative proposal → numeric delta (magnitude/direction) | — | world_model_agent, simulation | — | Normalize creative proposals |
| `core/creative_proposal_validator.py` | Validate proposed new actions/events (no unknown vars, qualitative only) | — | simulation.loop, governance | — | Validate meta/creative proposals |
| `core/narrative_firewall.py` | Two-layer narrative: facts only → narrator | summarization | core.narrative_builder | — | Firewall between trace and prose |
| `core/registry_validator.py` | Validate condition/effect keys against rule engine registry | core.rule_engine | scenario_parser, scenario_compiler | — | Registry validation for rules |
| `core/observation.py` | Noisy observation | — | agents.memory | — | `observe()` |

## 2.5 World

| File | Responsibility | Depends On | Used By | Key Classes | Key Functions |
|------|----------------|------------|---------|-------------|---------------|
| `world/world_state.py` | `clone_snapshot()` helper | — | — | — | `clone_snapshot()` |
| `world/delayed_events.py` | Delayed effects at trigger_turn | schemas.delta_schema | world_model | `DelayedEvent` | `apply_delayed_events_for_turn()` |

## 2.6 Schemas

| File | Responsibility | Depends On | Used By | Key Classes | Key Functions |
|------|----------------|------------|---------|-------------|---------------|
| `schemas/delta_schema.py` | Delta structure | pydantic | core, agents, simulation | `Delta` | `to_dict()`, `from_dict()` |
| `schemas/proposal_schema.py` | Proposal structure | pydantic | agents | `Proposal` | `to_dict()`, `from_dict()` |
| `schemas/scenario_schema.py` | Scenario validation | — | main, scenario_parser | — | `validate_scenario()`, `normalize_scenario()` |
| `schemas/llm_action_schema.py` | LLM action block | pydantic | llm_action_guard | `LLMActionBlock`, `DeltaEntry` | — |
| `schemas/strategic_action_schema.py` | Strategic response | pydantic | llm_action_guard | `StrategicActionResponse` | — |
| `schemas/meta_schema.py` | Meta proposals, events, options | pydantic | environment_agent, option_selector | `NewEventProposal`, `OptionSet`, etc. | — |
| `schemas/memory_schema.py` | Agent memory / long-term memory structures | pydantic | agents.memory | — | — |

## 2.7 V2 Modules (Generalized Engine)

| Module | Responsibility | Key exports |
|--------|----------------|-------------|
| `model/valuespec.py` | ValueSpec (numeric/ordinal/categorical/text), clamp, to_scalar_for_utility | ValueSpec, clamp_value, value_spec_from_legacy |
| `model/causal_graph.py` | Structural causal links only; edge_model; no action logs | structural_causal_links, get_weight_for_propagation, get_delay |
| `model/state.py` | Versioned snapshots, world_state/belief_state shapes | create_versioned_snapshot, commit_snapshot |
| `policy/action_dsl.py` | Universal DSL: intervene, allocate, communicate, probe, etc. → delta_raw | interpret_dsl, dsl_to_delta_raw |
| `dynamics/propagation.py` | Propagation with edge_model adapters, delay=0 only | propagate_variable_changes, propagate_with_edge_models |
| `governance/constraints.py` | Hard/soft constraints; ValueSpec adapter | apply_all_constraints, variable_specs_from_valuespecs |
| `trace_log/action_trace.py` | action_trace[] (never in causal_links) | append_action_trace_entry, ActionTraceEntry |
| `epistemic/beliefs.py` | Belief update with ValueSpec | observe_and_update_beliefs, belief_state_from_observation |
| `learning/adaptive_kernel.py` | Strategy weight update; bounded; objectives fixed | update_strategy_weights |
| `shocks/shock_engine.py` | Optional shocks; disabled ⇒ deterministic | apply_shocks_if_enabled, ShockSpec |
| `summarization/narrative.py` | Token substitution {{var:ID}}/{{delta:ID}}, lang re-export | substitute_narrative_tokens |
| `summarization/facts.py` | NarrativeFacts from trace/snapshots (opening_context, turning_points, tradeoff, ending_state) | — | core.narrative_builder | — | `build_narrative_facts()` |
| `summarization/lang.py` | Opening phrase, language detection from scenario | — | core.narrative_builder, narrative_firewall | — | `detect_narrative_language_from_scenario()`, `opening_phrase()` |
| `summarization/bucketing.py` | Qualitative/ordinal bucketing for narrative | — | renderer, validators | — | — |
| `summarization/renderer.py` | Deterministic narrative renderer from NarrativeFacts | summarization.facts, summarization.lang | core.narrative_builder | — | `render_narrative()` |
| `summarization/validators.py` | Reject digits, banned artifacts, wrong opening; retry/fallback | — | core.narrative_builder | — | `validate_narrative()` |
| `summarization/llm_narrator.py` | Optional LLM prose from NarrativeFacts | core.llm_client, summarization.validators | core.narrative_builder | — | `build_llm_prompt()`, `invoke_llm_narrator()` |

## 2.8 Pipeline (Scenario → JSON)

| File | Responsibility | Depends On | Used By | Key exports |
|------|----------------|------------|---------|-------------|
| `pipeline/orchestrator.py` | Run 5-stage pipeline | entity_extractor, variable_discovery, causal_graph_builder, incentive_modeler, objective_validator, action_discovery, model_serializer, errors | scenario_parser, main, ui | `run_pipeline()`, `PipelineError` |
| `pipeline/errors.py` | Pipeline exception type | — | orchestrator, entity_extractor, variable_discovery, causal_graph_builder, incentive_modeler, action_discovery | `PipelineError` |
| `pipeline/entity_extractor.py` | Extract named actors from scenario text | core.llm_client | orchestrator | `EntityExtractor` |
| `pipeline/variable_discovery.py` | Discover systemic/relational/internal variables | — | orchestrator | `VariableDiscoveryEngine` |
| `pipeline/causal_graph_builder.py` | Build causal graph (from, to, polarity, strength) | — | orchestrator | `CausalGraphBuilder` |
| `pipeline/incentive_modeler.py` | Objectives, trade-offs, capabilities, risk_tolerance | — | orchestrator | `IncentiveModeler` |
| `pipeline/action_space_deriver.py` | Derive action space (variable-driven fallback) | — | action_discovery, simulation.loop | `ActionSpaceDeriver.derive()` |
| `pipeline/objective_validator.py` | Validate and normalize incentives (sign-safe, no contradictions) | — | orchestrator | `validate_and_normalize_incentives()` |
| `pipeline/action_discovery.py` | LLM-based action discovery (effect, capability tags) | — | orchestrator | `ActionDiscoveryEngine` |
| `pipeline/model_serializer.py` | Pipeline output → scenario JSON | — | orchestrator | `ModelSerializer` |

**Pipeline stages (order):** Scenario Text → Entity Extraction → Variable Discovery → Causal Graph → Incentive Modeling → Incentive Validation (objective_validator) → Action Discovery → JSON Generation.

## 2.9 Utils & Config

| File | Responsibility | Used By |
|------|----------------|---------|
| `config/settings.py` | OWE_* env, SCENARIO_PATH, DRY_RUN, MAX_DELTA, LANG, ALLOW_NUMBERS, ENABLE_SHOCKS, RANDOM_SEED, MAX_LLM_CALLS_PER_TURN, ENABLE_ENVIRONMENT_AGENT, ENABLE_META_ACTIONS, etc. | simulation, core, agents, main, ui |
| `utils/id_generator.py` | Unique ID generation | core, schemas |
| `utils/logging.py` | Logging setup | — |

**V2 turn pipeline (deterministic):** (1) collect delta_raw (2) propagate (3) constraints (4) merge (5) delayed effects (6) clamp (7) commit snapshot (8) observe (9) belief update (10) diagnostics. **Invariants:** causal_links structural only; beliefs vs world_state; action_trace separate; lang=auto, no hardcoded Persian except when lang==fa.

---

# 3. Execution Flow Reconstruction

## One Full Simulation Cycle (step)

```
1. loop.step()
   │
   ├─► 2. agent.decay_memory() for all agents
   │
   ├─► 3. snapshot = world.snapshot()
   │
   ├─► 4. [if EnvironmentAgent] env_agent.propose(snapshot)
   │       │ LLM or rule-based: 0–2 events
   │       └─► world.events.append(ev) for each proposed
   │
   ├─► 5. stability, dissatisfaction = _compute_stability_and_dissatisfaction(snapshot, scenario)
   │       snapshot["derived"]
   │
   ├─► 6. summary_text = world_summarize(snapshot)  [deterministic]
   │
   ├─► 7. base_agent_input = snapshot | {strategic: True, snapshot, scenario} | summary
   │
   └─► 8. FOR EACH agent:
         │
         ├─► 8a. [if LLM planning] agent_input["get_delta"] = lambda action: world_model_agent.normalize_proposal(Proposal(action_type=action), snapshot)
         │
         ├─► 8b. agent_output = agent.propose(agent_input)
         │       │
         │       ├─ strategic: LLM → raw string
         │       ├─ dict (snapshot): BaseAgent.propose → plan_depth2 or plan_depth2_with_callback → Proposal → formatted string
         │       └─ str (summary): LLM → raw string
         │
         ├─► 8c. raw_json = guard.extract_json(agent_output)
         │       validated_json = guard.validate(raw_json)
         │       sanitized = guard.sanitize(validated_json, snapshot)
         │
         ├─► 8d. delta = Delta(numeric_updates=..., entity_updates=..., ...)
         │
         ├─► 8e. [if delta.delay_turns] → delayed_events.append(DelayedEvent(...)); continue
         │
         ├─► 8f. ok, warnings, modified_delta = governance.validate_delta(delta, world)
         │       [auto-repair: inject tradeoffs, never reject]
         │
         ├─► 8g. merged_numeric += delta.numeric_updates
         │       causal_edges_this_step.append(...)
         │
         └─► 8h. [if delta is None] _turn_degraded = True; rule_based_fallback_count += 1
         │
   ├─► 9. merged_numeric = _ensure_minimum_delta(merged_numeric)  [systemic drift if no changes]
   │
   ├─► 10. merged_numeric = apply_all_constraints(variables, variable_specs, merged_numeric, change_budget)
   │
   ├─► 11. previous_state = world.snapshot()
   │
   ├─► 12. combined_delta = Delta(numeric_updates=merged_numeric, ...)
   │       world.causal_links.extend(causal_edges_this_step)
   │
   ├─► 13. outcome = world.apply_delta(combined_delta, action_type=...)
   │       │
   │       ├─ primary effect: variables[primary] += direct_changes[primary]
   │       ├─ propagate_variable_changes() → secondary_effects
   │       ├─ variables[var] += secondary_effects[var]
   │       ├─ _apply_final_noise() [if ENABLE_UNCERTAINTY]
   │       ├─ entity_updates, new_entities, relation_updates
   │       └─ narrative.append(...)
   │
   ├─► 14. world.turn += 1
   │
   ├─► 15. events_triggered = world.process_delayed_events()
   │       │ apply_delayed_events_for_turn() + process_events_for_turn()
   │
   ├─► 16. rule_activations = run_rules(snap, world, rules)
   │
   ├─► 17. _provenance.append(...)
   │
   ├─► 18. FOR EACH agent: memory.add_event(), update_beliefs(), update_long_term_memory()
   │
   └─► 19. agent.reflect(provenance[-1:], snap_after)
```

## Arrow Diagram (Text)

```
main.py / ui.py
    │
    └──► SimulationLoop(scenario_path, scenario_data, dry_run)
              │
              ├── WorldModel(initial_state, causal_links, relations, events)
              ├── OntologyManager()
              ├── Governance()
              ├── get_agents_from_scenario() → [RoleAgent, ...]
              ├── WorldModelAgent(llm_wrapper)
              ├── [optional] EnvironmentAgent(llm_wrapper)
              └── LLMActionGuard(allowed_actions, strategic_format, max_delta)
              │
              └── loop.run(steps)
                    │
                    └── for i in range(steps): loop.step()
                          │
                          ├── world.snapshot()
                          ├── EnvironmentAgent.propose() ──► world.events
                          ├── world_summarize()
                          ├── agent.propose()
                          │     ├── BaseAgent.propose
                          │     │     ├── generate_candidate_actions() [LLM or rule]
                          │     │     ├── plan_depth2() | plan_depth2_with_callback()
                          │     │     │     ├── clone_world_state()
                          │     │     │     ├── apply_delta_to_state()
                          │     │     │     ├── get_delta() [WorldModelAgent]
                          │     │     │     └── utility_function()
                          │     │     └── Proposal
                          │     └── RoleAgent: _proposal_to_reasoning_action_string | LLM
                          │
                          ├── guard.extract_json()
                          ├── guard.validate()
                          ├── guard.sanitize()
                          ├── governance.validate_delta()
                          ├── merge deltas
                          ├── apply_all_constraints()
                          ├── world.apply_delta()
                          │     ├── primary effect
                          │     ├── propagate_variable_changes()
                          │     ├── _apply_final_noise()
                          │     └── entity/relation updates
                          │
                          ├── process_delayed_events()
                          ├── run_rules()
                          └── memory.add_event(), update_beliefs(), reflect()
```

---

# 4. State Model

## Snapshot Structure

```python
{
    "entities": dict[str, dict],
    "relations": list[dict],
    "variables": dict[str, float],      # primary store
    "global_state": dict[str, float],    # alias of variables
    "causal_links": list[dict],
    "narrative": list[str],
    "ontology": dict,
    "version": int,
    "turn": int,
    "delayed_events": list[DelayedEvent],
    "events": list[dict],
    "derived": dict,  # optional: instability_mode, system_stability, dissatisfaction
}
```

## World State Schema (WorldModel)

- **Mutable:** `variables`, `entities`, `relations`, `causal_links`, `narrative`, `delayed_events`, `events`, `version`, `turn`
- **Immutable:** `ontology` (updated by meta_proposals, not by apply_delta)

## Agent State Schema

```python
{
    "memory": AgentMemory.to_dict(),
    "beliefs": {"variables": {...}, "confidence": {...}},
    "long_term_goals": list[str],
    "short_term_goals": list[str],
    "long_term_memory": list[dict],
    "last_actions": list[str],
    "strategy_class_weights": dict[str, float],
}
```

## AgentMemory (Mutable)

- `episodic_memory`: list of {turn, action, outcome, world_delta}
- `beliefs`: {variables, confidence}
- `semantic_memory`: {global_state_summary, last_turn, last_version}
- `last_action_outcomes`: last 3

## Cloning

- **planning:** `agents/planner.clone_world_state()` — deep copy of entities, relations, global_state, narrative, ontology, version, turn. No causal_links.
- **world/world_state.clone_snapshot():** includes causal_links.
- **core/world_state.WorldState:** `clone()` returns new WorldState with deep-copied fields.

## Delta Application

- **Planning:** `planner.apply_delta_to_state(state, delta)` — in-place on `state["global_state"]`, entities, relations.
- **Execution:** `WorldModel.apply_delta(delta)` — applies to `self.variables`, entities, relations, narrative; calls propagation.

---

# 5. Delta Lifecycle

## Proposal → Validation → Planning Simulation → Final Apply

### 1. Proposal

- **Source:** Agent output (string with ### ACTION_JSON) or rule-based `rule_based_deltas_for_snapshot()`.
- **Format:** `{action, actor, deltas: [{variable, change}]}` or strategic `{chosen_action, primary_variable, expected_effect}`.

### 2. Extraction

- `LLMActionGuard.extract_json()` — parses JSON after ### ACTION_JSON, strip markdown.

### 3. Validation

- `LLMActionGuard.validate()` — schema check (LLMActionBlock or StrategicActionResponse), allowed_actions, allowed variables.

### 4. Sanitization

- `LLMActionGuard.sanitize()` — cap magnitude, clamp non-negative variables, drop unknown vars, reject NaN/Inf.

### 5. Governance

- `Governance.validate_delta()` — policy rules (no_negative_resources, entity_refs, require_tradeoffs). Auto-repair: inject cost variables, never reject.

### 6. Merge

- Loop sums `merged_numeric[k] += v` for all agents.

### 7. Soft Constraints

- `apply_all_constraints()` — rate_limit, change_budget, diminishing returns, hard clip.

### 8. Final Apply

- `WorldModel.apply_delta()` — primary effect, propagation, noise, entity/relation updates.

## Planning vs Execution

| Aspect | Planning | Execution |
|--------|----------|-----------|
| **Logic** | `apply_delta_to_state()` (planner) or `WorldState.apply_delta()` | `WorldModel.apply_delta()` |
| **Propagation** | None | `propagate_variable_changes()` |
| **Noise** | None | `_apply_final_noise()` (if ENABLE_UNCERTAINTY) |
| **Governance** | None | `Governance.validate_delta()` |
| **Soft constraints** | None | `apply_all_constraints()` |

**Planning and execution use different logic.** Planning uses a simple additive delta on a cloned state; execution uses primary/secondary propagation, noise, and governance.

---

# 6. LLM Integration Map

| File | Function | Purpose | Input | Output | Deterministic | Fallback |
|------|----------|---------|-------|--------|---------------|----------|
| `core/llm_client.py` | `call_llm()` | Main LLM entry | prompt, system, as_json | str or dict | No | sim_app → OpenAI fallback |
| `core/llm_service.py` | `call_llm()` | Schema validation, retry, cache | prompt, system, schema, client_fn | dict or str | No (cached) | None on failure |
| `agents/agents.py` | `RoleAgent.propose()` (strategic) | Strategic action | {strategic, snapshot, scenario} | raw string | No | — |
| `agents/agents.py` | `RoleAgent.propose()` (text) | Decision from summary | summary string | raw string | No | — |
| `agents/agents.py` | `RoleAgent.generate_candidate_actions()` | 2–4 candidates | world_snapshot | list[str] | No | allowed_actions[:4] |
| `agents/agents.py` | `_get_agents_llm_first()` | Agent definitions | scenario | list[dict] | No | _demo_fallback_agents |
| `agents/world_model_agent.py` | `normalize_proposal()` | Proposal → Delta | Proposal, snapshot | Delta or None | No | None (no rule fallback) |
| `agents/environment_agent.py` | `propose()` | 0–2 events | snapshot | list[dict] | No | _rule_based_propose |
| `scenario_parser.py` | `parse_scenario_text()` | Text → scenario JSON | text | dict | No | _default_scenario |
| `core/scenario_compiler.py` | `_run_stage()` | Multi-stage compile | stages | dict | No | raise ScenarioCompilationError |
| `core/agent_generator.py` | `generate_agents_from_scenario()` | Agent definitions | scenario | list[dict] | No | _fallback_agents |
| `core/agent_constructor.py` | `_llm_extract_agents()` | Extract agents | description, variables | list or None | No | None |
| `core/ontology_manager.py` | `suggest_attribute_from_text()` | Ontology suggestion | text | str | No | — |
| `core/narrative_builder.py` | `build_narrative()` | Narrative prose | trace, final, agents | str | No | — |
| `core/option_selector.py` | `_select_via_llm()` | Option selection | options, snapshot | SelectedAction | No | select_option_rule_based |

## Input/Output Schemas (Selected)

- **Strategic response:** `{chosen_action, primary_variable, probability, justification, causal_chain, expected_effect, relation_updates}`
- **Legacy action:** `{action, actor, deltas: [{variable, change}]}`
- **Delta normalizer:** `{numeric_updates, entity_updates, new_entities, relation_updates, meta_proposals, rationale, effects_duration, mitigation}`

---

# 7. Static vs Dynamic Components

## Hardcoded Rules

- `RULE_BASED_DELTAS` in `base_agent.py` — empty dict; extended by `rule_based_deltas_for_snapshot()` from `increase_X`/`decrease_X`.
- `NON_NEGATIVE_KEYWORDS` in `llm_action_guard.py` — population, count, resource, cash, etc.
- `_PROTECTED_KEYWORDS` in `world_model_agent.py` — population, people, resource, cash, count.
- `DEFAULT_EVENT_PALETTE` in `environment_agent.py` — incident, negotiation_round, deconfliction, external_shock.
- `DEFAULT_NORM_RANGES` in `utility.py` — growth, cash, runway_months, population, etc.
- `STEADY_ACTION = "steady_finance"` in `planner.py` — second-step action for depth-2.

## Fixed Action Spaces

- `allowed_actions` from scenario or `allowed_actions_from_variables()` — variable-driven `increase_X`, `decrease_X`, `adjust_variable`.
- Meta actions when `enable_meta_actions`: `propose_new_action`, `propose_new_variable`, `propose_new_causal_link`, `propose_new_event`.

## Deterministic Utilities

- `world_summarize()` — string building.
- `utility_function()` — weighted sum of normalized values.
- `evaluate_short_term_goals()` — derived from long_term_goals and state.
- `propagate_variable_changes()` — deterministic.
- `apply_all_constraints()` — deterministic.
- `select_option_rule_based()` — deterministic scoring.

## Static Event Palettes

- `DEFAULT_EVENT_PALETTE` in `environment_agent.py` — used only in dry-run.

## Rule-Based

- `plan_depth2()` — rule-based deltas.
- `run_rules()` — condition/effect from scenario registry.
- `_register_default_handlers()` in `event_queue.py` — incident, negotiation_round, deconfliction, external_shock.

---

# 8. Constraint & Safety Mechanisms

## Value Bounds

- **LLMActionGuard.sanitize:** `SAFE_NUMERIC_MIN/MAX` = ±1e12; magnitude cap via `max_delta` or `delta_magnitude_cap`.
- **Non-negative:** `_is_non_negative_variable()` — keywords in var name; clamp so `current + change >= 0`.
- **Soft constraints:** `variable_specs` with `rate_limit`, `soft_max`, `softness`, `min`, `max`, `clip`.
- **Change budget:** `apply_all_constraints()` scales deltas if total magnitude exceeds budget.
- **Hard clip:** `apply_hard_clip()` enforces min/max.

## Schema Validation

- `validate_scenario()` — scenario schema.
- `LLMActionGuard.validate()` — schema check.
- `llm_service._validate_schema()` — required keys, types.
- Pydantic models: `Delta`, `Proposal`, `LLMActionBlock`, `StrategicActionResponse`, etc.

## Negative States

- Governance `no_negative_resources` rule.
- LLMActionGuard: clamp non-negative vars.
- WorldModelAgent `_validate_delta`: reject if protected vars become negative.

## Infinite Growth

- `variable_specs` with `soft_max` or `max` can limit growth.
- No global hard cap on variables; `change_budget` limits per-turn total magnitude.

---

# 9. Architectural Inconsistencies

## 1. Planning vs Execution Model Divergence

- Planning: `apply_delta_to_state()` — additive only, no propagation.
- Execution: `WorldModel.apply_delta()` — primary/secondary propagation, noise.
- **Impact:** Planner scores may not match execution outcomes.

## 2. Duplicate Cloning Logic

- `agents/planner.clone_world_state()` — no causal_links.
- `world/world_state.clone_snapshot()` — includes causal_links.
- Planner does not use `world/world_state.clone_snapshot()`.

## 3. Competing Delta Sources

- Agent output: `guard.extract_json` → Delta.
- `action_spec` + `interpret_action_spec_with_world` — not used in main loop.
- `action_spec` path exists in Proposal schema but is not wired in loop.

## 4. Rule Engine Registry

- `run_rules()` uses `_condition_registry` and `_effect_registry`.
- Scenario rules reference `condition_key` and `effect_key`; registry may be empty if no domain loader registers them.

## 5. Event Queue vs Delayed Events

- `world.events` — list of dicts with `trigger_turn`, `event_type`, `params`.
- `world.delayed_events` — list of `DelayedEvent` with `trigger_turn`, `delta`, `source_action`.
- `process_events_for_turn` mutates `events` (pop); `apply_delayed_events_for_turn` mutates `delayed_events` (pop).

## 6. Ambiguous `process_events_for_turn` Call

- `WorldModel.process_delayed_events()` calls both `apply_delayed_events_for_turn` and `process_events_for_turn`.
- Environment events are appended with `trigger_turn = world.turn + 1`; they fire at the next turn.

---

# 10. Cognitive Model Classification

**Classification: Hybrid**

**Deterministic:**

- Propagation, utility, constraints, rule-based planning, dry-run agents.

**Stochastic:**

- LLM outputs, `random.gauss()` in noise, `random.random()` in event probability, instability mode (20% random action).

**LLM-Assisted:**

- Agent generation, proposal, delta normalization, scenario parsing, narrative.

**Fully Generative:**

- No — actions are always bounded by `allowed_actions` and validated schema.

**Hybrid:**

- Rule-based planning with optional LLM for candidates/delta; strategic format for direct LLM output; governance and constraints enforce safety.

---

# 11. Refactor Sensitivity Map

## Make fully LLM-native

- **Impact:** `agents/planner.py` (plan_depth2, rule_based), `agents/base_agent.py` (rule_based_deltas_for_snapshot), `agents/utility.py` (utility_function for planning).
- **Low impact:** `core/world_model.py`, `core/propagation.py`, `core/governance.py`.

## Remove rule-based planning

- **Impact:** `agents/planner.py`, `agents/base_agent.py` (rule_based_deltas_for_snapshot), `agents/utility.py` (utility_function).
- **Dependency:** `world_model_agent.normalize_proposal` must be used for all planning paths.

## Make world fully dynamic

- **Impact:** `core/world_model.py` (variable schema), `core/propagation.py` (causal_links structure), `schemas/delta_schema.py`, `core/llm_action_guard.py` (allowed_vars).
- **Scenario:** `initial_state`, `causal_links`, `variable_specs` currently static.

---

# 12. Appendices

## A. Import Graph (Text)

```
main.py
  ├── config.settings
  ├── schemas.scenario_schema
  ├── simulation.loop
  ├── core.narrative_builder
  ├── core.scenario_analysis_output
  ├── core.narrative_firewall
  ├── core.phase_detector
  ├── core.registry_validator
  └── core.llm_client

ui.py
  ├── flask
  ├── scenario_parser
  ├── schemas
  ├── simulation
  ├── core
  └── visualization

simulation/loop.py
  ├── config.settings
  ├── core.llm_client
  ├── core.world_model
  ├── core.ontology_manager
  ├── core.rule_engine
  ├── core.action_interpreter
  ├── core.governance
  ├── core.world_summarizer
  ├── core.llm_action_guard
  ├── core.soft_constraints
  ├── core.action_definitions_store
  ├── core.delta_attribution
  ├── schemas.delta_schema, proposal_schema, scenario_schema
  ├── agents.agents
  ├── agents.world_model_agent
  └── agents.environment_agent

agents/base_agent.py
  ├── schemas.proposal_schema
  ├── agents.memory
  ├── agents.planner
  └── agents.utility

agents/agents.py
  ├── schemas.proposal_schema
  ├── agents.base_agent
  ├── agents.memory
  ├── core.agent_constructor
  ├── core.llm_service
  ├── core.prompt_builder
  └── core.strategic_prompt

agents/planner.py
  ├── agents.utility
  └── core.world_state

core/world_model.py
  ├── schemas.delta_schema
  ├── core.propagation
  ├── world.delayed_events
  └── core.event_queue

core/narrative_builder.py
  ├── core.narrative_synthesizer
  ├── summarization.facts
  ├── summarization.lang
  ├── summarization.llm_narrator
  ├── summarization.renderer
  └── summarization.validators

pipeline/orchestrator.py
  ├── pipeline.errors
  ├── pipeline.entity_extractor
  ├── pipeline.variable_discovery
  ├── pipeline.causal_graph_builder
  ├── pipeline.incentive_modeler
  ├── pipeline.action_space_deriver
  ├── pipeline.objective_validator
  ├── pipeline.action_discovery
  └── pipeline.model_serializer
```

## B. Call Graph (Text)

```
main() → SimulationLoop() → loop.run()
  loop.run() → loop.step() [loop]
  loop.step()

  loop.step() → world.snapshot()
  loop.step() → env_agent.propose()
  loop.step() → world_summarize()
  loop.step() → agent.propose() [per agent]
  loop.step() → guard.extract_json()
  loop.step() → guard.validate()
  loop.step() → guard.sanitize()
  loop.step() → governance.validate_delta()
  loop.step() → apply_all_constraints()
  loop.step() → world.apply_delta()
  loop.step() → world.process_delayed_events()
  loop.step() → run_rules()
  loop.step() → agent.memory.add_event()
  loop.step() → agent.memory.update_beliefs()
  loop.step() → agent.reflect()

  agent.propose() → BaseAgent.propose()
  BaseAgent.propose() → memory.update_beliefs()
  BaseAgent.propose() → evaluate_short_term_goals()
  BaseAgent.propose() → generate_candidate_actions()
  BaseAgent.propose() → plan_depth2() | plan_depth2_with_callback()
  BaseAgent.propose() → get_delta() [WorldModelAgent.normalize_proposal]

  plan_depth2() → clone_world_state()
  plan_depth2() → delta_from_rule_based()
  plan_depth2() → apply_delta_to_state()
  plan_depth2() → utility_function()

  world.apply_delta() → propagate_variable_changes()
  world.apply_delta() → _apply_final_noise()
  world.process_delayed_events() → apply_delayed_events_for_turn()
  world.process_delayed_events() → process_events_for_turn()
```

## C. Data Flow Diagram (Text)

```
[Scenario JSON]
  → normalize_scenario()
  → WorldModel(initial_state, causal_links, relations, events)
  → get_agents_from_scenario() → [RoleAgent]

[Snapshot]
  → world_summarize() → summary_text
  → agent.propose(summary | snapshot | {strategic: ...})
  → agent_output (raw string)

[agent_output]
  → extract_json() → raw_json
  → validate() → validated_json
  → sanitize() → sanitized
  → Delta(numeric_updates, ...)

[Delta]
  → governance.validate_delta() → modified_delta
  → merge (sum numeric_updates)
  → apply_all_constraints()
  → combined_delta

[combined_delta]
  → world.apply_delta()
  → primary effect + propagation + noise
  → entity/relation updates
  → world.variables

[world.variables]
  → snapshot()
  → next step
```

---

*End of Architecture Dossier*
