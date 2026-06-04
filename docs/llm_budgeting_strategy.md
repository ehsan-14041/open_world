## LLM Budgeting Strategy – Open World Engine

This document describes how the engine uses LLMs, how to keep LLM usage efficient under a bounded compute budget, and how new features should integrate with the existing LLM stack.

### 1. LLM layers and responsibilities

- **Engine LLM client (`core/llm_client.py`)**
  - Single low-level integration point for HTTP / SDK calls.
  - Handles provider selection (`LLM_PROVIDER`, AvalAI, Groq, OpenAI-compatible), timeouts, and JSON/text modes.
  - Adds lightweight logging for UI inspection (`get_llm_logs`), never logs secrets.

- **Schema-first gateway (`core/llm_service.py`)**
  - Wraps `core.llm_client.call_llm`.
  - Provides:
    - Schema-aware JSON parsing and repair-once behavior.
    - Lightweight validation (required keys, basic type checks).
    - In-memory cache keyed by an explicit `cache_key` (LRU, TTL).
  - Callers pass a `client_fn` when they already have a wrapped client and want to reuse the same transport.

- **Call-site patterns**
  - **World-model normalization (`WorldModelAgent.normalize_proposal`)**
    - Hot-path normalization from `Proposal` → `Delta`.
    - Uses `DELTA_SCHEMA` and `llm_service.call_llm` with `as_json=True`.
    - Call sites are encouraged to pass a `cache_key` derived from `(agent, action, snapshot_fingerprint)` via `llm_service.make_cache_key`.
  - **Role agents (`agents/agents.py`)**
    - Use `llm_service` for:
      - Candidate action generation.
      - Scenario-driven agent construction when not provided explicitly.
    - These are per-turn but typically lower frequency than proposal normalization.
  - **Environment agent (`agents/environment_agent.py`)**
    - Optionally uses `llm_service` to generate a small set of environment events per turn, with JSON schema and repair-once.
  - **Oracle advisor (`core/oracle.py`)**
    - Uses LLM once per significant turn for advisory analysis only, gated by impact and stability thresholds.
  - **Authoring / research utilities**
    - Pipelines (`pipeline/_llm_utils.py`), scenario parsing, and ontology inference use `llm_service` off the hot-path.

### 2. Budget model and rate limits

Engine-level configuration (in `config/settings.py`) defines the main guardrails:

- **Turn-level caps**
  - `MAX_LLM_CALLS_PER_TURN`: hard cap on total LLM calls per simulation turn.
  - `MAX_LLM_CALLS_PER_AGENT_PER_TURN`: per-agent cap for planning / proposal calls.
  - `COMPUTE_BUDGET_PER_TURN`: generic compute budget counter (incremented for each LLM call in hot paths).

- **Budget semantics**
  - Calls that **must** respect the budget:
    - Agent planning and `get_delta` normalization during `SimulationLoop.step`.
    - Environment agent event proposals when running in LLM mode.
    - Oracle advisor when `ORACLE_TIERING_MODE` allows full evaluation.
  - Calls that **typically sit outside the tight budget**:
    - Scenario authoring, ontology suggestions, offline pipeline stages.
    - Optional LLM narration when rendering post-hoc reports from structured facts.

When the per-agent or per-turn budget is exhausted, planning logic should degrade gracefully to deterministic fallbacks (rule-based deltas, fixed strategies, or no-op actions) instead of attempting additional LLM calls.

### 3. Schema-first, not free-form

All LLM calls that influence the engine’s internal state must:

- Prefer **schema-first design**:
  - Define required fields and basic types (e.g., `DELTA_SCHEMA` in `WorldModelAgent`).
  - Normalize commonly returned list shapes into dicts under a clear key (e.g., `{"events": [...]}`).
- Keep prompts focused on:
  - The minimal subset of state required for the decision.
  - Allowed action sets and safety constraints.
  - Short, explicit instructions for JSON-only output (no markdown, no explanations).

Avoid asking the LLM to:

- Infer physics or numeric constraints that can instead be enforced deterministically.
- Produce long natural-language summaries inside hot loops.
- Operate on raw, unconstrained traces when structured variables and deltas are available.

### 4. Caching and idempotent patterns

The cache in `core.llm_service` is **opt-in** per call site via the `cache_key` parameter.

- **When to cache**
  - When the inputs are **purely a function of structured state plus a small configuration** and:
    - The same request is likely to be made multiple times within a turn (e.g., repeated planning calls for the same `(agent, action, snapshot)` tuple).
    - The downstream consumer does not require fresh randomness.
  - Examples:
    - `WorldModelAgent.normalize_proposal` from the same snapshot and action type inside a planner’s internal rollouts.

- **How to build cache keys**
  - Use `core.llm_service.make_cache_key(action: str, snapshot_hash: str)` for planner/normalizer calls.
  - Compute a **domain-agnostic snapshot fingerprint** in the orchestrator (e.g., `SimulationLoop.step`) from:
    - The current turn index.
    - The numeric variable map (`variables` / `global_state`).
  - Pass the resulting key into `llm_service.call_llm` via `cache_key=...`.

- **When NOT to cache**
  - When stochastic variation is desired (e.g., environment events designed to be probabilistic).
  - When prompts include transient or non-deterministic content (timestamps, random seeds, or logs).
  - When outputs are tied to per-call randomness that should not be de-duplicated.

### 5. Deterministic fallbacks

Every critical LLM-assisted step should have a deterministic fallback path:

- **WorldModelAgent**
  - Uses `DELTA_SCHEMA` and a single repair attempt.
  - If parsing or validation fails, returns `None`; callers treat this as a null delta and rely on:
    - Governance escalation and stricter validation for future turns.
    - Rule-based or deterministic deltas where available.

- **RoleAgent planning**
  - When no LLM client is available or budgets are exhausted:
    - Falls back to rule-based deltas (`rule_based_deltas_for_snapshot`) or simple variable-driven heuristics.

- **EnvironmentAgent**
  - In dry-run or when no LLM client is supplied:
    - Uses a small rule-based palette (`DEFAULT_EVENT_PALETTE`) for deterministic event generation.

- **Oracle advisor**
  - When thresholds are not met, or errors occur:
    - Provides a lightweight, heuristic advisory message or no analysis at all.
    - Never blocks or breaks the core physics path.

For new functionality, treat LLM output as **advisory** or **proposal-like** whenever possible, with hard constraints and safety implemented in typed Python code.

### 6. Good vs bad LLM use in this engine

- **Good use cases**
  - **Scenario compilation**:
    - Mapping natural-language scenario descriptions into structured agents, objectives, and allowed actions (one-time or offline).
  - **Candidate action priors**:
    - Suggesting candidate actions for agents from compact world summaries, when run under explicit budgets.
  - **Proposal normalization**:
    - Helping transform high-level proposals into structured deltas under strict schemas, with validation and caps.
  - **Advisory/oracle analysis**:
    - Providing additional analysis or risk commentary on a chosen action and predicted delta.
  - **Narrative rendering**:
    - Turning structured NarrativeFacts into human-readable prose via a constrained narrator.
  - **Ontology suggestions (off the hot-path)**:
    - Proposing variable names or causal hypotheses for reviewers to accept or reject.

- **Discouraged/bad use cases**
  - Repeated low-value summarization of state that can be obtained from:
    - `core/world_summarizer`, `core/narrative_engine`, or existing metrics.
  - Implementing domain physics, invariants, or constraints that should be expressed in:
    - `variable_specs`, propagation rules, or governance logic.
  - Calling the LLM repeatedly inside tight inner loops when:
    - A cached response or deterministic approximation would suffice.
  - Letting LLMs directly operate on raw logs or traces instead of:
    - Structured facts, tags, and narrative inputs.

### 7. Guidelines for new LLM integrations

When adding a new LLM-backed feature:

1. **Decide if the feature truly needs an LLM**
   - If the output can be expressed deterministically over structured state, prefer a typed implementation.
2. **Define a schema-first contract**
   - Specify required keys and basic types, and express them in code (dict-based schema or pydantic model).
3. **Use the shared gateway**
   - Route calls through `core.llm_service.call_llm` with:
     - `schema=...` for JSON outputs.
     - `cache_key=...` if safe and beneficial.
     - `client_fn=...` only when you already have a wrapped client in scope.
4. **Be explicit about budgets**
   - Annotate in code whether the call is:
     - Hot-path runtime.
     - Per-turn but gated.
     - Setup-time or offline.
   - Respect the relevant caps and, where necessary, add additional guards.
5. **Add deterministic fallbacks**
   - Ensure that failure to call the LLM (or invalid outputs) leads to:
     - A safe, deterministic alternative.
     - Graceful degradation rather than crashes.
6. **Test with fakes**
   - For unit tests, inject a fake `llm_client` or `client_fn` that:
     - Returns canned outputs.
     - Counts invocations so that tests can assert budget and caching behavior.

By following these principles, the engine keeps LLM usage focused on high-leverage tasks, remains robust under tight compute budgets, and preserves explainability through structured, typed mechanics.

