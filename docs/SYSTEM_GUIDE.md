# Open World Engine — System Guide



Practical reference for running the engine, the **Enterprise Operations Decision Simulator** product path, configuration, and APIs.



For core architecture, see [ARCHITECTURE.md](ARCHITECTURE.md). For module-level detail, see [ARCHITECTURE_DOSSIER.md](ARCHITECTURE_DOSSIER.md).



---



## Quick start



```bash

pip install -r requirements.txt

python ui.py

```



Open **http://127.0.0.1:5081** — the home page runs without an API key (`dry_run=true` by default on the operations path).



CLI (engine only):



```bash

python main.py --dry-run --steps 5

python main.py --scenario config/scenarios/demo_scenario.json --steps 10

```



---



## Two scenario paths



| Path | When | How scenario is built | LLM required? |

|------|------|----------------------|---------------|

| **Operations product** | `POST /api/brief` with `ops_profile` + `decision_id` | `adapters/ops_scenario_builder.build_scenario()` | No (default `dry_run=true`) |

| **Text / advanced** | Free text, `decision_input`, or raw JSON on `/advanced` | `parse_scenario_text()` → pipeline, or direct JSON | Optional (`use_llm`, `dry_run`) |



**Invariant:** If `ops_profile` is present, `parse_scenario_text()` is never called. Tests enforce this in `tests/test_ops_path_guard.py`.



---



## Operations product flow



### 1. Profile (`ops_profile`)



Validated by `schemas/ops_schema.py`.



| Field | Required | Notes |

|-------|----------|-------|

| `business_unit_type` | yes | `manufacturing`, `distribution`, `retail`, `multi_echelon`, `contract_manufacturing`, `general_ops` |

| `inventory_on_hand`, `weekly_demand` | recommended | Non-negative numbers |

| `safety_stock`, `lead_time_days`, `unit_cost`, `holding_cost_pct` | optional | Derived defaults applied when omitted |

| `fill_rate`, `supplier_risk`, `capacity_utilization` | optional | 0–1 |

| `planning_horizon_weeks` | optional | `4`, `8`, `12`, or `26` (default `8`) |

| `site_name`, `product_family`, `primary_constraint`, `planning_goal` | optional | Display / context fields |



Demo presets: `GET /api/ops_presets` → `config/ops_presets.json` (tagged `outlook`: stable / strained / uncertain).



### 2. Decision template (`decision_id`)



Loaded from `config/ops_decisions.json` via `GET /api/ops_decisions`.



Each template includes labels, `move`, `actors`, `horizon_weeks`, `tradeoff_hint`, `primary_risks`, and optional `editable_assumptions`. Examples: `increase_safety_stock`, `expedite_reorder`, `switch_supplier`, `reallocate_demand`.



### 3. Scenario build



`adapters/ops_scenario_builder.py` merges:



- Profile → `initial_state` (inventory, demand, fill rate, lead time, holding cost, supplier risk, …)

- Business unit type → `causal_links` (e.g. lead time → fill rate, safety stock → stockout risk)

- Decision template → `decision_input`, featured action tradeoffs, allowed actions

- Base agents: VP Operations, Supply Chain Director, Planning Manager



### 4. Simulation + brief



```json

POST /api/brief

{

  "ops_profile": {

    "business_unit_type": "distribution",

    "inventory_on_hand": 8200,

    "weekly_demand": 1100,

    "fill_rate": 0.89,

    "lead_time_days": 16

  },

  "decision_id": "increase_safety_stock",

  "compare_decision_id": "expedite_reorder",

  "steps": 6,

  "dry_run": true,

  "save_snapshot": true

}

```



Response fields (partial):



| Field | Source module |

|-------|---------------|

| `outcomes` | `ui/ops_outcomes.py` — verdict, service/cost/risk headlines, next steps |

| `brief` | `ui/decision_brief.py` — drivers, second-order effects, kill criteria |

| `turn_trace` | `ui/turn_trace.py` — per-turn variable deltas |

| `comparison` | Second run when `compare_decision_id` is set |

| `graph_url` | Link to `/graph` impact map |

| `decision_id` | Journal record id when saved |



---



## Decision journal



When `enable_decision_journal` is true in config (or `OWE_ENABLE_DECISION_JOURNAL=1`):



- Records saved to `output/decisions/<id>.json` via `core/decision_journal.py`

- UI: `/journal`, `GET /api/journal`, `POST /api/journal/<id>/annotate`



Each record stores `ops_profile`, `decision_template_id`, `brief`, and optional `annotation` (what actually happened).



---



## Text → JSON pipeline (advanced path)



Used by `scenario_parser.parse_scenario_text()` and `/advanced`:



```

Scenario text

  → pipeline/orchestrator.run_pipeline()

      1. Entity extraction

      2. Variable discovery

      3. Causal graph builder

      4. Incentive modeler

      5. Objective validator

      6. Action discovery

      7. Model serializer → scenario JSON

  → schemas/scenario_schema.validate_scenario()

  → normalize_scenario()

```



Stages raise `pipeline.errors.PipelineError` on failure.



Structured decisions can bypass free-form parsing by rendering `decision_input` to text via `schemas/decision_schema.decision_to_scenario_text()`.



---



## Scenario JSON format



Required keys: `description`, `initial_agents`, `initial_state`, `relations`, `allowed_actions`.



Common extensions:



| Key | Purpose |

|-----|---------|

| `causal_links` | Weighted propagation edges |

| `action_tradeoffs` | Direct numeric effects per action |

| `variable_tradeoffs` | Cross-variable coupling |

| `variable_specs` | Rate limits, soft max, min/max |

| `rules`, `events` | Rule engine and event queue |

| `decision_input` | Structured move context (product layer) |



Bundled examples: `config/scenarios/*.json`.



---



## Actions and variables



- **Allowed actions:** From scenario or derived (`increase_X`, `decrease_X`, `adjust_variable`).

- **Action tradeoffs:** Map action id → `{variable: delta}` applied before propagation.

- **Propagation:** `core/propagation.py` — secondary effects along `causal_links`.

- **Abstract actions:** `action_spec` → `core/action_interpreter.py` → Delta (V2 DSL in `policy/action_dsl.py`).



The operations product uses deterministic tradeoffs in `ops_scenario_builder` rather than LLM-discovered actions.



---



## Configuration



Settings load from `config/settings.json` (optional) and `OWE_*` environment variables. See `config/settings.py` for the full list.



| Setting | Config key | Env | Notes |

|---------|------------|-----|-------|

| Dry run | `dry_run` | `OWE_DRY_RUN` | Rule-based agents, no LLM |

| Product mode | `product_mode` | `OWE_PRODUCT_MODE` | Hides `/advanced`, engineering APIs |

| Decision journal | `enable_decision_journal` | `OWE_ENABLE_DECISION_JOURNAL` | Persist `/api/brief` runs |

| Language | `lang` | `OWE_LANG` | Narrative presentation only |

| Dashboard | `dashboard_enabled` | `OWE_DASHBOARD_ENABLED` | Live SSE dashboard |

| MC + RL | `mc_rl_enabled` | `OWE_MC_RL_ENABLED` | Hybrid action selection |

| Belief layer | `enable_belief_layer` | `OWE_ENABLE_BELIEF_LAYER` | Advanced belief model |

| Oracle | `enable_oracle` | `OWE_ENABLE_ORACLE` | LLM advisory per turn |



Product-specific config files (not in `settings.json`):



- `config/ops_presets.json`

- `config/ops_decisions.json`

- `config/decision_presets.json` (legacy chips)



---



## Web routes



### Product



| Route | Method | Purpose |

|-------|--------|---------|

| `/` | GET | Enterprise Operations Decision Simulator |

| `/graph` | GET | Causal impact map |

| `/journal` | GET | Decision history UI |

| `/health` | GET | Health check (`service`: `enterprise_ops_decision_simulator`) |

| `/api/brief` | POST | Simulate + brief |

| `/api/ops_presets` | GET | Preset library |

| `/api/ops_decisions` | GET | Decision templates |

| `/api/journal` | GET | List journal entries |

| `/api/journal/<id>` | GET | Fetch one entry |

| `/api/journal/<id>/annotate` | POST | Add outcome annotation |



### Engineering (`/advanced`)



Disabled when `product_mode=true`.



| Route | Method | Purpose |

|-------|--------|---------|

| `/advanced` | GET | Raw scenario tools |

| `/api/submit_scenario` | POST | Parse/validate text |

| `/api/run_simulation` | POST | Batch run |

| `/api/run_simulation_stream` | POST | SSE stream |

| `/api/snapshot` | GET | Last snapshot |

| `/api/narrative` | GET | Narrative for last run |

| `/viewer` | GET | Run viewer |

| `/dashboard` | GET | Live dashboard (when enabled) |



---



## Tests



```bash

pytest tests/ -v

pytest tests/test_ops_*.py tests/test_ops_language.py tests/test_ui_routes.py -v

```



Key product tests: ops schema validation, scenario builder, path guard (no LLM on ops path), operations language (no jargon), E2E brief API.



---



## Related docs



| Document | Contents |

|----------|----------|

| [ARCHITECTURE.md](ARCHITECTURE.md) | Causal graph, beliefs, narrative, V2, product layer overview |

| [HYBRID_ENGINE.md](HYBRID_ENGINE.md) | MC+RL, stochastic gating, feature toggles |

| [engine_contracts.md](engine_contracts.md) | Typed contracts |

| [migration_notes.md](migration_notes.md) | Breaking changes (e.g. `ui/dashboard_payload`) |

