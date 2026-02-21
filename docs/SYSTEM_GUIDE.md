# Open World Engine 2 — System Guide

This guide describes how the **open_world_engine2** scenario engine processes text inputs into executable simulations, how actions are derived, how variables interact, and how emergent behavior arises.

---

## 1. Pipeline Overview

When you provide scenario text, the engine runs a 5-stage pipeline (`pipeline/orchestrator.py`):

```
Scenario Text
    → Stage 1: Entity Extraction (real named actors)
    → Stage 2: Variable Discovery (systemic, relational, internal variables)
    → Stage 3: Causal Graph Construction (from, to, polarity, strength)
    → Stage 4: Strategic Incentive Modeling (objectives, capabilities, trade-offs)
    → Incentive Validation (validate_and_normalize_incentives via objective_validator)
    → Action Discovery (LLM-based; fallback: ActionSpaceDeriver)
    → Stage 5: JSON Generation (ModelSerializer)
```

Each stage receives only the output of the previous stage. No stage is skipped.

**Pipeline modules:** `entity_extractor`, `variable_discovery`, `causal_graph_builder`, `incentive_modeler`, `objective_validator`, `action_discovery`, `model_serializer`, `errors` (PipelineError).

---

## 2. How Actions Are Derived Dynamically

Actions are **not** pre-defined. They are discovered from the scenario text via an LLM-based stage.

- **Input:** Scenario text, entities, variables, causal graph, incentives
- **Output:** A list of scenario-specific actions (e.g. `deescalate`, `propose_ceasefire`, `activate_hotline`)
- **Per action:** Effect (which variables change and by how much), capability tags, strategy class, optional availability conditions

**Capability-based filtering:** Each agent has `capabilities` (e.g. `diplomatic`, `military`, `mediator`). Actions specify which capability tags can perform them. An agent can only use actions whose tags match their capabilities. If no tags match, the agent gets all actions.

**Fallback:** If the LLM stage fails, the engine falls back to variable-driven actions (`increase_X`, `decrease_X`) derived from the discovered variables.

---

## 3. How Variables Interact

**Causal graph:** Variables are linked by directed edges with `from`, `to`, `polarity` (positive/negative), and `strength` (0–1).

- **Positive:** An increase in `from` increases `to`
- **Negative:** An increase in `from` decreases `to`
- **Strength:** Magnitude of the effect (used as `weight` for propagation)

**Propagation:** When an action changes a variable, the engine propagates effects along the causal graph. Secondary effects are computed deterministically: `delta_target += delta_source * weight`.

**Variable tradeoffs:** The `variable_tradeoffs` map encodes secondary effects when a variable changes (e.g. when `tension` changes, `stability` is affected by -0.2).

---

## 4. How Agents' Strategic Incentives Are Calculated

Each agent has:

- **objectives:** Weighted preferences over variables (e.g. `{"increase_stability": 0.6, "decrease_tension": 0.4}`)
- **trade_offs:** List of trade-offs (e.g. willing to sacrifice growth for stability)
- **capabilities:** Tags used for action filtering
- **risk_tolerance:** 0–1 (affects decision prompt)
- **aggressiveness:** 0–1 (affects decision prompt)
- **strategic_constraints:** Optional constraints (e.g. cannot escalate if trust &lt; 30)

The utility function scores world states using these objectives. Planning and action selection use this scoring.

---

## 5. How Emergent Behavior Arises

- **Constraints:** `variable_specs` (min, max, rate_limit) and governance rules limit what can happen.
- **Events:** The engine can define events (e.g. `crisis_if_tension_above_80`) that trigger when conditions are met.
- **Feedback loops:** The causal graph can contain cycles; propagation iterates to compute cascading effects.
- **Interactions:** Agents' actions affect shared variables; propagation and tradeoffs create indirect effects.
- **Strategic incentives:** Different objectives and capabilities lead to different action choices and outcomes.

---

## 6. Schema Overview

| Field | Description |
|-------|-------------|
| `description` | Text summary of the scenario |
| `initial_agents` | Agents with name, role, objectives, capabilities, optional `allowed_actions` |
| `initial_state` | Variables and initial values |
| `relations` | Entity relations (e.g. conflicts_with) |
| `allowed_actions` | Global list of action names |
| `action_tradeoffs` | Action → variable deltas (e.g. `deescalate` → `{tension: -5, stability: 2}`) |
| `variable_tradeoffs` | Variable → variable secondary effects |
| `variable_specs` | Per-variable min, max, clip, rate_limit |
| `strategy_classes` | Action → strategy class (e.g. diplomatic, escalatory) |
| `rules` | Condition/effect rules |
| `events` | Potential emergent events with triggers |
| `causal_links` | Causal graph edges (from, to, polarity, strength, weight). V2: structural only; edge_model (type, params, delay, decay) |

---

## 7. Per-Agent Actions

When the pipeline produces per-agent action sets (from capability matching), each `initial_agents` entry may include `allowed_actions`: the subset of actions that agent can perform. The guard validates each agent's output against that subset.

---

## 8. Controlled Creativity (Weak-Model Hardening)

To remain robust under weak language models, the engine separates **creative proposal** from **deterministic execution**.

**Model output (primary):** `{ "chosen_action": "<action_id>" }` — the model selects from a deterministic OptionSet only. It never outputs numeric deltas.

**Creative proposal (optional, throttled):** The model may propose new actions, events, or rules with qualitative effects only:
- `magnitude` ∈ {tiny, small, medium, large}
- `direction` ∈ {up, down}
- Must include `capability_tags`, `strategy_class`, `rationale`
- May include `availability_conditions` as boolean expressions over known variables

Proposals are validated (no unknown variables, no numeric literals). On failure, the engine falls back to a safe action. Throttle: at most 1 proposal per agent every N turns (configurable, default 3).

**Deterministic normalization:** Qualitative effects are converted to numeric `delta_vector` by the engine using `variable_specs.rate_limit` and a fixed mapping (tiny=0.15×, small=0.35×, medium=0.70×, large=1.00×).

---

## 9. Deterministic OptionSet (Max 3)

At each turn, each agent receives an OptionSet of at most 3 actions. The engine never falls back to the full action list.

**Filtering:**
- By `capability_tags`: if match → keep; if no match → only actions tagged `general` or `stabilize`
- By `availability_conditions`: deterministic evaluation on current state

**Scoring (no LLM):**
```
score(a) = dot(objectives_signed, delta_vector(a))
           - risk_penalty(risk_tolerance, instability_like_change)
           + strategy_bias(strategy_class_weights)
```

**Selection:** Top-2 by score + 1 safe stabilizer (minimize total |delta| or reduce most volatility-driving variable). One creative slot: a newly accepted proposed action may occupy at most 1 slot.

**Fallback:** If the model chooses an action outside the OptionSet or outputs invalid JSON, the engine deterministically picks the best-scored safe action.

---

## 10. Delta Lifecycle and Attribution

**Per agent:** `delta_raw_per_agent[agent] = action_definitions[chosen_action].delta_vector`

**Merge:** `delta_after_merge[var] = Σ delta_raw_per_agent[*][var]`

**Constraints:** `delta_applied = apply_constraints(delta_after_merge, variable_specs, change_budget)`

**Attribution:** For each variable, the engine computes `self_effect_per_agent` (agent-attributed share of `delta_applied`):
- If `delta_after_merge[var] ≠ 0`: proportional share by `delta_raw[agent][var] / delta_after_merge[var]`
- If sign conflicts (cancellations): allocate by `abs(delta_raw) / Σ abs(contribs)`

All of `delta_raw_per_agent`, `delta_after_merge`, `delta_applied`, and `self_effect_per_agent` are stored in the TurnRecord.

---

## 11. Stable Propagation (Cycle-Safe)

Propagation uses only structural `causal_links` (`from`, `to`, `weight`). Action provenance is never mixed into causal_links.

**Cycle safety:**
- `max_iter` (configurable, default 5)
- Epsilon convergence stopping
- Damping factor (0 &lt; d &lt; 1, default 0.6)
- Per-iteration clamp proportional to `rate_limit(var)`

**Trace:** `propagation_trace` records each iteration: `{iter, from, to, weight, delta_source, delta_contrib}`.

---

## 12. Two-Layer Narrative Firewall

**Layer 1 — Facts (source of truth):** Deterministic fact extraction from run snapshots and turn_records produces **NarrativeFacts** only: `opening_context`, `key_actors`, `turning_points`, `tradeoff`, `ending_state`. No raw action logs or full state dumps are passed to Layer 2.

**Layer 2 — Weaving:** The narrator consumes only NarrativeFacts. Either (1) a deterministic renderer or (2) an optional LLM produces prose. Validators reject output that contains digits (when `allow_numbers=false`), banned artifacts (`Causal chain:`, `max_delta`, `Variable `, `Turn `), or a wrong opening prefix; on failure, retry once then fallback to the deterministic renderer.

**Language is presentation-only:** Language does **not** affect variable discovery, action discovery, governance, propagation, causal graph, scoring, shocks, or state updates. It is applied only inside summarization/formatting (opening phrase, prose language). Engine-core modules do not import `summarization` or `summarization.lang`.

**Domain-agnostic:** Narratives use no domain-specific keywords or templates; variable names appear only as generic humanized ids (e.g. snake_case to spaced words).

**No digits by default:** When `allow_numbers=false` (default), narrative output must contain no digits; use qualitative/ordinal labels from ValueSpec or bucketing.

**Placeholder substitution (allow_numbers=true):** When numbers are allowed, the LLM must output only placeholders: `{{PRE:var}}`, `{{POST:var}}`, `{{DELTA:var}}`, `{{EVENT:id}}`. The engine substitutes from snapshots/turn_records. Output is rejected if digits appear before substitution or if placeholders remain unresolved.

---

## 13. Phase Detection and Final Summary

**Importance score (per turn):** Magnitude of `delta_applied`, threshold crossings count, `events_fired` count, propagation cascade depth.

**Phase detection:** Rolling dominant strategy class trend; variable regime shifts; crisis triggers.

**Per phase:** Select top-k turns by importance (k=2 or 3). Build fact bullets with placeholders:
- Example: `"Turn {{TURN}}: {{AGENT}} chose {{ACTION}} causing {{DELTA:var}} on {{var}} and triggering {{EVENT:...}}."`

**Final summary:** At simulation end, the human-readable narrative is produced from `phase_summary_facts` only. The model connects bullets coherently with placeholders; the engine replaces them deterministically.

---

## 14. V2 Config and Trace

**Config flags (config/settings.py, env OWE_*):**
- **allow_numbers** (default false): Narrative qualitative by default (no digits); if true, LLM outputs only placeholders `{{PRE:var}}`, `{{POST:var}}`, `{{DELTA:var}}`, `{{EVENT:id}}` and engine substitutes from snapshot/turn_record.
- **enable_shocks** (default false): When false, no shock sampling; runs deterministic given seed.
- **lang** (default "auto"): Resolved from scenario for narrative (presentation only); fa → opening "در آغاز", en → "At the beginning".
- **random_seed**: Plumbed for propagation, observation, shocks, learning when set.
- **proposal_throttle_turns** (default 3): Max creative proposals per agent every N turns.
- **propagation_max_iter** (default 5), **propagation_epsilon** (default 1e-6), **propagation_damping** (default 0.6): Cycle-safe propagation.
- **phase_top_k_turns** (default 3): Top-k turns per phase for narrative facts.

**Action trace:** Separate from causal_links. Each run accumulates `action_trace[]`: turn, agent_id, action {op, args}, delta_raw, delta_applied, optional expected_utility/realized_utility. Returned with `return_provenance=True` as `result["action_trace"]`. Never merged into causal_links.

---

## 15. Scenario Analysis Output (Logic Core & Executive Summary)

After a run, `core/scenario_analysis_output.py` produces two-part output:

**Logic Core (JSON):** Technical summary built from:
- `core/delta_aggregation`: `global_delta`, `action_impact_summary`
- `core/attribution_layer`: human-readable attribution sentences (action → variable change)
- `core/convergence_analysis`: system convergence label (stable/oscillating/diverging), per-variable analysis

**Executive Summary:** Three paragraphs: what happened, why (causal), critical risk next turn.
