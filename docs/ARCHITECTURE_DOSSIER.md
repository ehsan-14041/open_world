# Open World Engine — Architecture Dossier

**Document Version:** 2.0  
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
    → for each agent: agent.propose(agent_input) [optional MC+RL: get_planner_scores, run_mc_evaluation, softmax_select] → extract/validate/sanitize → Delta
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
| `agents/base_agent.py` | Memory, goals, utility, planning flow | schemas.proposal_schema, agents.memory, agents.planner, agents.utility | agents.agents | `BaseAgent` | `propose()`, `reflect()`, `rule_based_deltas_for_snapshot()`; sets `_last_planning_delta` (rule-based path via `delta_from_rule_based`) for provenance |
| `agents/agents.py` | RoleAgent, agent construction from scenario | proposal_schema, base_agent, memory, agent_constructor, llm_service | simulation.loop | `RoleAgent` | `propose()`, `generate_candidate_actions()`, `get_agents_from_scenario()` |
| `agents/planner.py` | Depth-2 planning, clone/apply for simulation | agents.utility, core.world_state, world.world_state | base_agent | — | `plan_depth2()`, `plan_depth2_with_callback()`, `clone_world_state()`, `apply_delta_to_state()`, `delta_from_rule_based()` |
| `agents/world_model_agent.py` | Proposal → Delta via LLM | core.llm_service, schemas | simulation.loop (get_delta callback) | `WorldModelAgent` | `normalize_proposal()` |
| `agents/environment_agent.py` | Propose 0–2 events per turn | core.llm_service, schemas.meta_schema | simulation.loop | `EnvironmentAgent` | `propose()` |
| `agents/memory.py` | Episodic memory, beliefs, beliefs update | core.observation | base_agent, agents | `AgentMemory` | `add_event()`, `update_beliefs()`, `get_relevant_context()` |
| `agents/utility.py` | Utility scoring, goals from objectives | — | planner, base_agent | — | `utility_function()`, `evaluate_short_term_goals()`, `goals_from_objectives()` |
| `agents/action_evaluation.py` | Monte Carlo evaluation, planner scores, softmax action selection (LLM + MC + RL) | agents.utility, agents.planner, world.world_state | base_agent | — | `run_mc_evaluation()`, `get_planner_scores()`, `softmax_select()` |
| `agents/belief_model.py` | BeliefState, belief update, belief_alignment, belief_entropy_aggregate (optional layer) | — | base_agent (when ENABLE_BELIEF_LAYER), dashboard_payload | `BeliefState` | `belief_state_from_memory_beliefs()`, `update_belief_state()`, `belief_alignment()`, `belief_entropy_aggregate()`, `dominant_belief()` |

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
| `core/scenario_analysis_output.py` | Logic Core, Executive Summary, Strategic Analysis envelope | attribution_layer, delta_aggregation, convergence_analysis | main, ui | — | `build_scenario_analysis_output()`, `build_logic_core()`, `build_executive_summary()`, `build_strategic_analysis()` |
| `core/proposal_normalizer.py` | Qualitative proposal → numeric delta (magnitude/direction) | — | world_model_agent, simulation | — | Normalize creative proposals |
| `core/creative_proposal_validator.py` | Validate proposed new actions/events (no unknown vars, qualitative only) | — | simulation.loop, governance | — | Validate meta/creative proposals |
| `core/narrative_firewall.py` | Two-layer narrative: facts only → narrator | summarization | core.narrative_builder | — | Firewall between trace and prose |
| `core/registry_validator.py` | Validate condition/effect keys against rule engine registry | core.rule_engine | scenario_parser, scenario_compiler | — | Registry validation for rules |
| `core/observation.py` | Noisy observation | — | agents.memory | — | `observe()` |
| `core/dashboard_payload.py` | Build dashboard JSON (state_snapshot, risk_report, calibration_metrics, selected_action, explanation, assumption_summary, edition, belief_alignment, shock, oracle_analysis) | core.attribution_layer (optional), enterprise.positioning (optional), agents.belief_model (optional), core.risk_assessment | ui.dashboard, simulation.loop | — | `build_dashboard_payload()`, `compute_calibration_from_provenance()` |
| `core/calibration.py` | Recalibration trigger (periodic/drift), apply_recalibration_action, calibration_event for provenance | core.dashboard_payload (compute_calibration_from_provenance) | simulation.loop | — | `check_recalibration_trigger()`, `apply_recalibration_action()`, `set_last_recalibration_turn()`, `get_recalibration_state()` |
| `core/risk_assessment.py` | Agent behavior summary, next_turn_risk_score, optional tail_risk_from_mc | — | core.dashboard_payload | — | `agent_behavior_summary()`, `next_turn_risk_score()`, `tail_risk_from_mc()` |
| `core/rule_learner.py` | Offline suggest governance strictness/rule updates from (delta, outcome) history | — | External / human review | — | `suggest_rule_updates()` |
| `core/simulation_mode.py` | Runtime state: simulation_mode, enable_shocks, enable_uncertainty; get/set without restart | config.settings (lazy) | simulation.loop, API consumers | — | `get_simulation_mode()`, `set_simulation_mode()`, `get_enable_shocks()`, `set_enable_shocks()`, `get_enable_uncertainty()`, `set_enable_uncertainty()`, `get_mode_state()` |
| `core/oracle.py` | LLM Advisor: advisory-only analysis of proposed action (Confidence, Risk Factors, Alternative Scenarios); no state change | core.llm_service, core.world_summarizer | simulation.loop (when ENABLE_ORACLE), dashboard_payload | — | `summarize_history_for_oracle()`, `analyze_action()` |
| `core/narrative_templates.py` | Domain-agnostic narrative templates (relational, state_transition, trajectory) | — | core.narrative_builder | — | `template()` |
| `core/mental_simulation.py` | Light mental simulation for planner: apply_delta with propagation (bounded hops, decay), no noise | core.propagation | agents.planner | — | `apply_delta_light()`, `run_mental_simulation()` |
| `core/surprise_analysis.py` | Compare predicted_delta_light vs actual outcome; deviation beyond threshold | — | simulation.loop | — | `run_surprise_analysis()` |
| `core/synthesizer.py` | Action diversity (min options by score), expected_utility | — | agents.base_agent | — | `ensure_action_diversity()`, `expected_utility()` |
| `core/causal_learning.py` | Suggest causal link from trace patterns; apply_belief_drift for edge confidence | — | core.oracle (optional) | — | `suggest_causal_link_from_trace()`, `apply_belief_drift()` |
| `core/trace_compression.py` | Compress provenance to Causal Event Chain for long-trace analysis; optional SLM | — | External / optional | — | `compress_trace_to_causal_chain()` |

## 2.5 World

| File | Responsibility | Depends On | Used By | Key Classes | Key Functions |
|------|----------------|------------|---------|-------------|---------------|
| `world/world_state.py` | Canonical clone and snapshot helper (single source of truth for cloning) | — | agents.planner, world, simulation.loop (via world) | — | `clone_world_state(snapshot, include_causal_links=...)`, `clone_snapshot()` |
| `world/delayed_events.py` | Delayed effects at trigger_turn | schemas.delta_schema | world_model | `DelayedEvent` | `apply_delayed_events_for_turn()` |

## 2.5a Simulation (shock engine, checkpoints)

| File | Responsibility | Depends On | Used By | Key Classes | Key Functions |
|------|----------------|------------|---------|-------------|---------------|
| `simulation/shock_engine.py` | Macro shocks (supply_chain, financial, political, information_warfare); apply impact_delta when SIMULATION_MODE=shock_global | — | simulation.loop | — | `step_shock_engine()` |
| `simulation/checkpoints.py` | Bounded checkpoints (turn, snapshot, provenance_slice, action_trace_slice); rollback to turn or last step | — | simulation.loop | `CheckpointStore` | `push()`, `get_for_turn()`, `rollback_to_turn()`, `rollback_last_step()` |

## 2.5b UI (dashboard)

| File | Responsibility | Depends On | Used By | Key Classes | Key Functions |
|------|----------------|------------|---------|-------------|---------------|
| `ui/dashboard.py` | Live dashboard buffer, SSE, routes /dashboard, /api/dashboard/*, research_draft export | config.settings, core.dashboard_payload | ui (Flask app) | — | `on_turn_complete()`, `get_latest_payload()`, `get_history_payloads()`, `register_routes()` |

## 2.5c Enterprise & Research

| File | Responsibility | Depends On | Used By | Key exports |
|------|----------------|------------|---------|-------------|
| `enterprise/positioning.py` | Tier labels and profiles (Research, Enterprise Core/Pro, Government); feature_flags, dashboard_modules_enabled | config.settings (ENTERPRISE_TIER) | dashboard_payload, ui.dashboard | `get_current_tier()`, `get_enterprise_profile()` |
| `research/paper_draft.py` | Research draft markdown from provenance | — | ui.dashboard (api_dashboard_research_draft) | `generate_research_draft()` |

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
| `config/settings.py` | OWE_* env, SCENARIO_PATH, DRY_RUN, MAX_DELTA, LANG, ALLOW_NUMBERS, ENABLE_SHOCKS, RANDOM_SEED, MAX_LLM_CALLS_PER_TURN, ENABLE_ENVIRONMENT_AGENT, ENABLE_META_ACTIONS, MC_RL_*, PROPOSAL_THROTTLE_TURNS, PROPAGATION_*, PHASE_TOP_K_TURNS, DASHBOARD_ENABLED, DASHBOARD_HISTORY_SIZE, ENTERPRISE_TIER, SIMULATION_MODE, SHOCK_*, ENABLE_BELIEF_LAYER, BELIEF_WEIGHT, ENABLE_RESEARCH_EXPORT, CHECKPOINT_*, CALIBRATION_*, ASSUMPTION_HIGH_IMPACT_THRESHOLD, ENABLE_ORACLE, ORACLE_HISTORY_TURNS, ORACLE_MAX_TOKENS, etc. | simulation, core, agents, ui, enterprise, main |
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
         │       ├─ dict (snapshot): BaseAgent.propose →
         │       │     [if MC_RL_ENABLED] get_planner_scores(), run_mc_evaluation(), softmax_select() → best_action
         │       │     [else] plan_depth2 or plan_depth2_with_callback → best_action
         │       │     → Proposal (formatted string)
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
   ├─► 15a. [if CHECKPOINT_ENABLED] checkpoint_store.push(turn_before, snapshot, provenance_slice, action_trace_slice)  [optional, before apply]
   │
   ├─► 15b. [if SIMULATION_MODE=shock_global] step_shock_engine(world, turn) → shock_result; apply impact_delta to world; provenance["shock"] = shock_result
   │
   ├─► 15c. [recalibration] check_recalibration_trigger(provenance_history); if true → apply_recalibration_action(), set_last_recalibration_turn(), provenance_entry["turn_record"]["calibration_event"] = {reason}
   │
   ├─► 16. rule_activations = run_rules(snap, world, rules)
   │
   ├─► 17. predicted_deltas = [each agent's _last_planning_delta] (for strategic analysis)
   │
   ├─► 18. _provenance.append(..., predicted_deltas=..., shock=..., oracle_analysis=...)
   │
   ├─► 18a. [if ENABLE_ORACLE] summarize_history_for_oracle(provenance_history), analyze_action(...) → oracle_analysis; store in provenance_entry
   │
   ├─► 18b. [if DASHBOARD_ENABLED] build_dashboard_payload(snapshot, provenance_entry, ...) → on_turn_complete(payload)
   │
   ├─► 19. FOR EACH agent: memory.add_event(), update_beliefs(); [if ENABLE_BELIEF_LAYER] belief_model.update_belief_state(..., shock_active=...)
   │
   └─► 20. agent.reflect(provenance[-1:], snap_after)
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
                          │     │     ├── [MC_RL] get_planner_scores(), run_mc_evaluation(), softmax_select() | plan_depth2() | plan_depth2_with_callback()
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

## Cloning (canonical)

- **Single canonical API:** `world/world_state.clone_world_state(snapshot, *, include_causal_links: bool = False)`. Use this for all world-state cloning; avoid other deep copies of world state.
- **Planning:** Call with `include_causal_links=False` — deep copy of entities, relations, global_state/variables, narrative, ontology, version, turn; **no** causal_links.
- **Execution / full state:** Call with `include_causal_links=True` (or use `world/world_state.clone_snapshot(snapshot)`, which is a thin wrapper).
- **Planner:** `agents/planner.clone_world_state(snapshot, include_causal_links=False)` delegates to `world.world_state.clone_world_state()`; planning never includes causal_links.
- **core/world_state.WorldState:** `clone()` returns new WorldState with deep-copied fields (for planning adapter).

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

**Delta path (canonical):** All world state changes are expressed as **Delta** and applied **only** through `WorldModel.apply_delta()`. Legacy formats (JSON action block, Strategic response, action_spec) are converted internally to Delta; rule effects and delayed events also apply via `WorldModel.apply_delta()`.

## Planning vs Execution

| Aspect | Planning | Execution |
|--------|----------|-----------|
| **Logic** | `apply_delta_to_state()` (planner) or `WorldState.apply_delta()` | `WorldModel.apply_delta()` |
| **Propagation** | None | `propagate_variable_changes()` |
| **Noise** | None | `_apply_final_noise()` (if ENABLE_UNCERTAINTY) |
| **Governance** | None | `Governance.validate_delta()` |
| **Soft constraints** | None | `apply_all_constraints()` |

**Planning and execution use different logic.** Planning uses a simple additive delta on a cloned state (no propagation, no noise, no delayed events); execution uses primary/secondary propagation, noise, and governance. Same delta application formula (additive numeric_updates); execution adds propagation and optional stochastic effects.

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

## Input processing

- **Scenario input:** Accepted as (1) natural language via `parse_scenario_text()` → pipeline → scenario JSON, or (2) structured JSON (scenario dict) directly. Pipeline extracts agents, variables, causal links; model is generic (no hardcoded industries/countries).

## Strategic analysis output

- **Envelope:** `build_strategic_analysis()` (in `core/scenario_analysis_output.py`) returns: `agents`, `variables`, `causal_links` (structural only), `predicted_changes` (global_delta + per_turn_predicted_deltas from provenance), `agent_actions`, `causal_explanations`, `confidence_scores`, `strategic_decisions`, plus `logic_core` and `executive_summary`. Provenance entries include `predicted_deltas` (from each agent's `_last_planning_delta`, populated in rule-based path via `delta_from_rule_based()`). Main CLI prints Strategic Decisions when present.

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

## 2. Cloning (resolved)

- **Canonical:** `world/world_state.clone_world_state(snapshot, include_causal_links=False|True)`. Planning uses `False`; full clone (e.g. for propagation) uses `True`. `clone_snapshot(snapshot)` is a thin wrapper with `include_causal_links=True`. Planner delegates to the canonical function.

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

- LLM outputs, `random.gauss()` in noise, `random.random()` in event probability, instability mode (20% random action), MC+RL softmax action selection (`softmax_select` in `action_evaluation.py`).

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
  ├── core.scenario_analysis_output (build_scenario_analysis_output, build_strategic_analysis)
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
  ├── ui.dashboard (register_routes, on_turn_complete)
  └── visualization

simulation/loop.py
  ├── config.settings
  ├── core.simulation_mode (get_simulation_mode, get_enable_shocks)
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
  ├── core.dashboard_payload (build_dashboard_payload when DASHBOARD_ENABLED)
  ├── core.calibration (check_recalibration_trigger, apply_recalibration_action, set_last_recalibration_turn when recalibrate)
  ├── core.oracle (summarize_history_for_oracle, analyze_action when ENABLE_ORACLE)
  ├── ui.dashboard (on_turn_complete when DASHBOARD_ENABLED)
  ├── simulation.shock_engine (step_shock_engine when SIMULATION_MODE=shock_global)
  ├── simulation.checkpoints (CheckpointStore when CHECKPOINT_ENABLED; rollback_to_turn, rollback_last_step)
  ├── agents.belief_model (update_belief_state when ENABLE_BELIEF_LAYER)
  ├── schemas.delta_schema, proposal_schema, scenario_schema
  ├── agents.agents
  ├── agents.world_model_agent
  └── agents.environment_agent

agents/base_agent.py
  ├── schemas.proposal_schema
  ├── agents.memory
  ├── agents.planner
  ├── agents.utility
  └── agents.action_evaluation (lazy: run_mc_evaluation, get_planner_scores, softmax_select)

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
  ├── core.world_state
  └── world.world_state

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