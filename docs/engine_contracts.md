# Engine contracts

Canonical typed contracts for the Open World Engine. All types support `from_dict` / `to_dict` and optional adapters from legacy dict shapes.

## Contract table

| Contract | Module | Description | Main fields |
|----------|--------|-------------|-------------|
| **SimulationSpec** | `schemas/contracts` | Typed run config from scenario | description, initial_state, relations, allowed_actions, governance, causal_links, rules, events, action_tradeoffs, variable_tradeoffs, strategy_classes, variable_specs, enable_meta_actions, agent_response_format, initial_agents |
| **State** | `schemas/contracts` | World state snapshot | variables, global_state, causal_links, entities, relations, version, turn, narrative, ontology |
| **ValueSpec** | `model/valuespec` | Variable schema (existing) | type, scale, ordinal_labels, categories, clamp, rate_limit, soft_max, behavior_type, etc. |
| **ActionSpec** | `schemas/contracts` | Abstract action for interpreter | type, target/variable, magnitude, variance, success_probability, direction, effect |
| **Delta** | `schemas/delta_schema` | World change | numeric_updates, entity_updates, new_entities, relation_updates, rationale, primary_variable, action_type, ... |
| **EventSpec** | `schemas/contracts` | Scenario-defined event | event_type, trigger_turn, params, priority, origin, metadata |
| **ConstraintSpec** | `schemas/contracts` | Variable-level constraints | min, max, rate_limit, soft_max, softness, non_negative, protected |
| **TraceEntry** | `schemas/contracts` | Action trace entry | turn, agent_id, action, delta_raw, delta_applied, expected_utility, realized_utility, belief_basis |
| **TransitionResult** | `schemas/contracts` | One-step result (optional) | state_before, state_after, delta_applied, events_fired, trace_entries, governance_rejects |

## Adapters (dict ↔ typed)

- **simulation_spec_from_scenario(scenario)** → SimulationSpec. Use after `normalize_scenario()`.
- **state_from_dict(snapshot)** → State.
- **action_spec_from_dict(d)** → ActionSpec | None. Lenient for Proposal.action_spec.
- **event_spec_from_dict(d)** → EventSpec.
- **constraint_spec_from_variable_spec(var_spec)** → ConstraintSpec from legacy variable_specs or ValueSpec-like dict.
- **trace_entry_from_dict(d)** → TraceEntry.

## Where contracts are produced/consumed

| Contract | Produced by | Consumed by |
|----------|-------------|-------------|
| SimulationSpec | scenario + normalize_scenario → simulation_spec_from_scenario | Optional: loop, tests |
| State | WorldModel.snapshot(), WorldState.to_snapshot(), state_from_dict | Optional: tests, future loop |
| ActionSpec | Proposal.action_spec, action_spec_from_dict | action_interpreter (when used in loop in Phase 2) |
| Delta | action_interpreter, loop (from JSON), get_delta_vector, WorldModel.apply_delta | world_model, governance, loop, physics_core |
| EventSpec | scenario.events → event_spec_from_dict | event_queue (as dict in current code) |
| ConstraintSpec | variable_specs → constraint_spec_from_variable_spec | llm_action_guard, governance (non_negative/protected) |
| TraceEntry | trace_log, trace_entry_from_dict | action_trace list, tests |
| TransitionResult | Optional step helper | Tests, future loop |

## Package boundaries

- **Core:** No imports from `ui/` or `dashboard`. May use `schemas`, `model`, `world`, `governance`, `config`.
- **Simulation:** Imports core, agents, schemas; does not import dashboard payload builder; may accept callback from UI.
- **UI/Dashboard:** Imports core (e.g. calibration_metrics, narrative_engine), builds payload; provides `build_dashboard_payload` and optional `build_turn_payload` callback for the loop.
