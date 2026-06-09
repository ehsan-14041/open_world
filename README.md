# Enterprise Operations Decision Simulator

**Simulate one operational decision before you make it.**

For VP Operations, supply chain directors, and planning leaders: should you increase inventory, switch suppliers, add capacity, or reallocate demand — given lead-time uncertainty, demand shifts, and service targets?

The product delivers a **decision-support recommendation** in under 30 seconds: cost impact, service level impact, risk, walk-away signals, and next best action. No API key required for the demo. The causal impact map at `/graph` is supporting evidence only.

**Built for:** VP Operations · Supply Chain Director · Production Planning Manager · Demand / Inventory Planning · Risk & Business Continuity teams.

For engine architecture, see [Architecture](docs/ARCHITECTURE.md).

---

## 30-second demo (no API key)

```bash
pip install -r requirements.txt
python ui.py
```

Open **http://127.0.0.1:5081**

1. Load **Strained — demand spike, capacity tight** (or pick another operations preset)
2. Select **Increase safety stock** — compare with **Expedite reorder**
3. Click **Simulate this decision**

You immediately get:

- **One-line verdict** — e.g. "Increase buffer cautiously — service gain must justify holding cost"
- **Service / cost / risk headlines** — fill rate change, weekly holding cost, stockout risk
- **Best and worst case**, **key drivers**, **walk-away signals**, **next best action**
- **Side-by-side comparison** between two decisions
- **Impact map** at `/graph` as supporting evidence only

**Demo presets** (`config/ops_presets.json`) are tagged by operational outlook:

| Outlook | Example | What it shows |
|---------|---------|----------------|
| **stable** | Balanced regional DC | Healthy buffer, predictable demand |
| **strained** | Demand spike + tight capacity | Service level at risk |
| **uncertain** | Supplier delay + margin pressure | Lead time and cost volatility |

The product path **always** builds scenarios via `adapters/ops_scenario_builder.py` (deterministic, no LLM). API keys are not required for the home-page demo.

| Route | Purpose |
|-------|---------|
| `/` | Enterprise Operations Decision Simulator (product home) |
| `/graph` | Causal impact map (evidence) |
| `/journal` | Decision history |
| `/advanced` | Engine tools (debug, disabled in product mode) |

**API (operations product path):**

```json
POST /api/brief
{
  "ops_profile": {
    "business_unit_type": "distribution",
    "inventory_on_hand": 8200,
    "weekly_demand": 1100,
    "fill_rate": 0.89,
    "lead_time_days": 16,
    ...
  },
  "decision_id": "increase_safety_stock",
  "compare_decision_id": "expedite_reorder",
  "steps": 6,
  "dry_run": true,
  "save_snapshot": true
}
```

`decision_id` is **required** with `ops_profile`. The adapter builds the scenario; `parse_scenario_text()` is never called on this path.

| Endpoint | Purpose |
|----------|---------|
| `GET /api/ops_presets` | Operations scenario presets (`outlook`: stable / strained / uncertain) |
| `GET /api/ops_decisions` | 12 decision templates (inventory, supplier, capacity, allocation, …) |
| `GET /api/decision_presets` | Legacy chips (`legacy/startup/config/`, not used by product home) |

Config: `config/ops_presets.json`, `config/ops_decisions.json`. Adapter: `adapters/ops_scenario_builder.py`. Outcome copy: `ui/ops_outcomes.py`.

---

## Product features

- **Operations Decision Simulator** — Home (`/`): operations profile + decision → verdict, cost/service/risk impact, comparison (`adapters/ops_scenario_builder.py`, `ui/ops_outcomes.py`).
- **Decision Brief** — Structured exploration: likely outcomes, drivers, second-order effects, walk-away signals (`ui/decision_brief.py`).
- **Decision Journal** — Persist and annotate past decisions for S&OP learning loops (`core/decision_journal.py`).
- **Causal impact map** — Visual evidence of variable propagation (`/graph`).

## Engineering mode

The product demo does not require API keys or LLM calls. For the underlying simulation engine (multi-agent paths, free-text scenarios, dashboard), see [Engine internals](docs/ENGINE_INTERNALS.md). Buyer-facing guide: [Product Guide](docs/PRODUCT_GUIDE.md).

---

## Requirements

- Python **3.10+**
- Dependencies: **pydantic**, **openai**, **flask** (see `requirements.txt`)

---

## Install

```bash
cd owe
pip install -r requirements.txt
```

Using a virtual environment (recommended):

```bash
python3 -m venv .venv

# Linux / macOS
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py --dry-run --steps 3

# Windows
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py --dry-run --steps 3
```

---

## Configuration

Settings are loaded from **`config/settings.json`** (optional) and overridden by environment variables.

| Setting | Config key | Environment variable |
|---------|------------|----------------------|
| Config file path | — | `OWE_CONFIG` |
| Scenario file | `scenario_path` | `OWE_SCENARIO_PATH` |
| Dry run (no LLM) | `dry_run` | `OWE_DRY_RUN=true` |
| Snapshot output | `snapshot_path` | `OWE_SNAPSHOT_PATH` |
| LLM provider | `llm_provider` (`avalai`, `groq`, or OpenAI-compatible) | `LLM_PROVIDER` |
| Decision journal | `enable_decision_journal` | `OWE_ENABLE_DECISION_JOURNAL` |
| Language | `lang` (`auto`, `en`, `fa`, …) | `OWE_LANG` |

**Provider blocks** in `config/settings.json`:

```json
{
  "llm_provider": "groq",
  "avalai": {
    "api_key": "",
    "base_url": "https://api.avalai.ir/v1",
    "model": "gpt-4o",
    "temperature": 0.2,
    "max_tokens": 4096,
    "timeout": 120
  },
  "groq": {
    "api_key": "",
    "base_url": "https://api.groq.com/openai/v1",
    "model": "llama-3.3-70b-versatile",
    "temperature": 0.2,
    "max_tokens": 2048,
    "timeout": 60
  }
}
```

Additional options (config or `OWE_*` env): `max_llm_calls_per_turn`, `enable_uncertainty`, `debug_llm`, `delta_magnitude_cap`, `random_seed`, `enable_environment_agent`, `enable_meta_actions`, `enable_shocks`, `enable_belief_layer`, `propagation_max_iter`, `propagation_epsilon`, `propagation_damping`, and more. Full list: `config/settings.py`.

> **Security:** Do not commit real API keys. Use environment variables or a local `settings.json` that is gitignored.

---

## API Keys

**Not required** for the operations product demo at `/` (`dry_run=true` by default).

API keys are only needed for engineering paths: free-text scenario parsing, LLM agent reasoning, and narrative generation. Configure via `config/settings.json` or `GROQ_API_KEY` / `OPENAI_API_KEY` env vars. See [Engine internals](docs/ENGINE_INTERNALS.md).

---

## CLI Usage

From the project root:

```bash
python main.py
python main.py --steps 10
python main.py --dry-run --steps 5
python main.py --snapshot /tmp/out.json --steps 5
python main.py --narrative --steps 3
python main.py --summary --dry-run --steps 5
python main.py --scenario-text "Regional DC: 8200 units on hand, 1100 weekly demand, 89% fill rate; weighing safety stock vs expedited reorder" --dry-run --steps 5
```

| Option | Description |
|--------|-------------|
| `--steps N` | Number of simulation turns (default: 5) |
| `--dry-run` | Disable LLM; use rule-based proposals and deltas only |
| `--snapshot path` | Save final world snapshot as JSON |
| `--scenario path` | Path to scenario JSON (default: `config/scenarios/demo_scenario.json`) |
| `--scenario-text "..."` | Free-form scenario text; parsed to JSON via LLM, then simulated |
| `--use-llm-for-agents` | With `--scenario-text`: generate agent definitions (personality, initial variables) via LLM |
| `--narrative` | Print final narrative built from provenance and world state |
| `--summary` | Print structured one-paragraph world summary only |

---

## Web UI

Flask interface with two surfaces:

| URL | Audience | Purpose |
|-----|----------|---------|
| **`/`** | Operations leaders | **Enterprise Operations Decision Simulator** — profile, decision, simulate, results |
| **`/advanced`** | Engineers | Raw scenario JSON, LLM logs, streaming runs (debug; disabled in `product_mode`) |
| **`/graph`** | Both | Causal impact map after a run |
| **`/journal`** | Operations leaders | Decision history and outcome annotations |

### Start the server

```bash
pip install -r requirements.txt
python ui.py
```

Open **http://127.0.0.1:5081** (default port **5081**).

Options:

```bash
python ui.py --port 8080
python ui.py --host 127.0.0.1    # local only
python ui.py --debug             # Flask debug mode
```

### Operations workflow (`/`)

1. **Operations profile** — Use a preset (Stable / Strained / Uncertain) or edit fields (inventory, demand, fill rate, lead time, supplier risk, …).
2. **Decision** — Pick from 12 templates (increase safety stock, expedite reorder, switch supplier, …). Optionally compare a second decision.
3. **Simulate** — Deterministic run (no API key). Results include outcome cards, service/cost/risk headlines, brief, and turn trace.
4. **Impact map** — Open `/graph` to inspect causal drivers.

Snapshots are written to `data/snapshots/snapshot_<id>.json` and `last_snapshot.json`.

### Engineering workflow (`/advanced`)

1. **Submit Scenario** — Free-text or JSON scenario; optional LLM conversion.
2. **Run Simulation** — Configure steps and dry-run; stream or batch results.
3. **Graph / Viewer / Dashboard** — Inspect JSON, causal graph, and turn intelligence.

Legacy free-text brief analysis is not exposed on `/`; use `/advanced` or the API with explicit `text` / `decision_input` if needed.

### API endpoints (summary)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check (`service`: `enterprise_ops_decision_simulator`) |
| `/api/brief` | POST | Simulate + brief (ops profile or legacy text/decision_input) |
| `/api/ops_presets` | GET | Operations scenario presets |
| `/api/ops_decisions` | GET | Decision template library |
| `/api/submit_scenario` | POST | Parse and validate scenario text (`/advanced`) |
| `/api/run_simulation` | POST | Run simulation |
| `/api/run_simulation_stream` | POST | Stream turn-by-turn results (SSE) |
| `/api/journal` | GET | List saved decisions |
| `/api/snapshot` | GET | Last run snapshot |
| `/api/narrative` | GET | Narrative for last run |
| `/graph` | GET | Causal graph visualization |
| `/viewer` | GET | Run viewer |

### Troubleshooting 503 (Service Unavailable)

A **503** usually means the reverse proxy reached the server but the Flask app is down or timed out.

1. **Confirm the server is running:**
   ```bash
   python ui.py --port 5081
   ```

2. **Health check:**
   ```bash
   curl http://127.0.0.1:5081/health
   ```
   Expected: `{"status":"ok","service":"enterprise_ops_decision_simulator"}`

3. **Behind Nginx:** Simulations and narrative generation can take a long time. Increase timeouts:
   ```nginx
   proxy_read_timeout 300s;
   proxy_send_timeout 300s;
   ```

---

## Operations scenario format (product path)

The product does not use hand-authored scenario JSON. It builds scenarios from:

- **Operations profile** — `schemas/ops_schema.py` (inventory, demand, fill rate, lead time, supplier risk, …)
- **Decision template** — `config/ops_decisions.json` (e.g. `increase_safety_stock`, `expedite_reorder`)

See `adapters/ops_scenario_builder.py`. Engineering scenarios (JSON files under `config/scenarios/`) are documented in [Engine internals](docs/ENGINE_INTERNALS.md).

---

## Architecture (product path)

```
ops_profile + decision_id
  → ops_scenario_builder (deterministic)
  → SimulationLoop (dry_run)
  → decision_brief + ops_outcomes
  → verdict, service/cost/risk/delay impact, comparison
```

Causal propagation powers second-order effects; the impact map at `/graph` is supporting evidence. Full engine architecture: [docs/ENGINE_INTERNALS.md](docs/ENGINE_INTERNALS.md).

---

## What to Expect (product demo)

**Default operations agents** (internal roles — not shown as "multi-agent" in the UI):

| Agent | Focus |
|-------|--------|
| ops_director | Service level vs cost |
| supply_chain_lead | Lead time, supplier risk |
| finance_controller | Holding cost, margin |
| planning_manager | Forecast accuracy, allocation |

**Example product flow:**

1. Load **demand spike + tight capacity** preset
2. Select **Increase safety stock**; compare with **Expedite reorder**
3. Simulate — ops_director executes the chosen decision on turn 1
4. Causal links propagate fill rate, holding cost, backlog, stockout risk
5. UI shows verdict, impact headlines, walk-away signals, and optional comparison cards

---

## Project Structure

```
owe/
├── main.py                 # CLI entry point
├── ui.py                   # Web UI server
├── scenario_parser.py      # Free-text → scenario JSON (LLM or rule-based)
├── config/
│   ├── settings.py         # Loads config/settings.json + env
│   ├── settings.json       # Optional local config (do not commit secrets; dry_run defaults true)
│   ├── ops_presets.json        # Operations demo presets (stable / strained / uncertain)
│   ├── ops_decisions.json      # 12 decision templates
│   └── scenarios/          # Engineering scenario JSON files
├── adapters/
│   └── ops_scenario_builder.py      # Profile + decision → engine scenario (product path)
├── legacy/
│   └── startup/            # Former founder SKU (not wired to ui.py)
├── simulation/
│   └── loop.py             # SimulationLoop — main turn loop
├── agents/                 # base_agent, world_model_agent, RoleAgents, memory, planner, utility
├── core/                   # propagation, rule_engine, event_queue, action_interpreter,
│                           # narrative_engine, narrative_builder, governance, llm_client, …
├── world/                  # world_state, delayed_events
├── model/                  # V2: valuespec, causal_graph, state
├── policy/                 # V2: action DSL
├── pipeline/               # Text → scenario JSON pipeline (orchestrator, entity extractor, …)
├── epistemic/              # Belief update models
├── schemas/                # scenario, proposal, delta, decision, ops schemas
├── ui/                     # dashboard_payload, decision_brief, ops_outcomes, turn_trace
├── summarization/          # NarrativeFacts, renderer, LLM narrator
├── visualization/          # graph_viewer, impact_data
├── templates/              # brief (product home), index (advanced), journal, graph, run_viewer
├── static/                 # CSS, JS for Web UI
├── data/snapshots/         # Written by runs (last_snapshot.json)
├── output/decisions/       # Decision journal records
├── docs/
│   ├── ARCHITECTURE.md     # Causal graph, beliefs, rules, trace, narrative
│   ├── ARCHITECTURE_DOSSIER.md
│   ├── SYSTEM_GUIDE.md     # Pipeline, actions, variables, config
│   └── HYBRID_ENGINE.md
└── tests/                  # pytest suite
```

---

## Tests

From the project root:

```bash
pip install -r requirements.txt
pip install pytest
pytest tests/ -v
```

Test coverage includes: determinism, dry-run environment, scenario compiler, pipeline stages, narrative synthesizer, **ops schema/builder/E2E path guard**, **operations outcome language**, decision schema/brief/presets, kill criteria, calibration, LLM budget, V2 engine, and more.

Operations product tests:

```bash
pytest tests/test_ops_*.py tests/test_ops_language.py tests/test_ui_routes.py -v
```

---

## Documentation

| Document | Contents |
|----------|----------|
| [docs/PRODUCT_GUIDE.md](docs/PRODUCT_GUIDE.md) | Buyer-facing product guide, demo script, planning workflow |
| [docs/ADVISOR_PILOT.md](docs/ADVISOR_PILOT.md) | Consultant / S&OP advisor pilot kit |
| [docs/SYSTEM_GUIDE.md](docs/SYSTEM_GUIDE.md) | Operations API, journal, config |
| [docs/ENGINE_INTERNALS.md](docs/ENGINE_INTERNALS.md) | Engineering mode, Open World Engine |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Engine architecture (advanced) |
| [docs/ARCHITECTURE_DOSSIER.md](docs/ARCHITECTURE_DOSSIER.md) | Full engine dossier (advanced) |
| [docs/HYBRID_ENGINE.md](docs/HYBRID_ENGINE.md) | MC+RL and stochastic gating (advanced) |

---

## License

See repository license file if present.
