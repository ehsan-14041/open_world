# Open World Engine

A multi-agent simulation engine with causal variable graphs, belief states, governance, and narrative intelligence. Agents propose actions, the world model applies and propagates numeric deltas, rules and events fire from scenario definitions, and a full provenance trace drives structured narratives and decision briefs.

For deeper design notes, see [Architecture](docs/ARCHITECTURE.md).

---

## Features

- **Causal world model** — Variables linked by weighted causal edges; changes propagate deterministically (`core/propagation.py`).
- **Multi-agent simulation** — Role-based agents (Founder, Investor, CommunityLeader, etc.) with goals, planning, and optional LLM reasoning.
- **Belief layer** — Agents observe a noisy world and decide from beliefs, not ground truth (`core/observation.py`).
- **Rules & events** — Scenario-defined conditions and effects; delayed events and event queue (`core/rule_engine.py`, `core/event_queue.py`).
- **Action interpreter** — Abstract action specs map to generic deltas (`core/action_interpreter.py`).
- **Narrative intelligence** — Turn-by-turn narrative, actor ranking, causal chains, regime detection (`core/narrative_engine.py`).
- **Decision Brief** — Structured exploration of a decision: likely outcomes, drivers, second-order effects, kill criteria (`ui/decision_brief.py`).
- **Decision Journal** — Persist and annotate past decisions for a learning loop (`core/decision_journal.py`).
- **Scenario pipeline** — Free-text scenarios converted to validated JSON via LLM (`scenario_parser.py`, `pipeline/`).
- **Web UI & dashboard** — Submit scenarios, run simulations, view graphs, snapshots, and live turn intelligence (`ui.py`).

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

**Standalone:**

- Set keys in `config/settings.json` under `avalai.api_key`, `groq.api_key`, or `openai.api_key`, **or**
- Export environment variables: `AVALAI_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`
- For any OpenAI-compatible endpoint: `OPENAI_BASE_URL`, `OPENAI_MODEL` (defaults: `https://api.openai.com/v1`, `gpt-4o-mini`)

**With sim_app (same repo):** The engine can reuse an existing LLM client. Set `GROQ_API_KEY` or `AVALAI_API_KEY` in the environment or in `sim_app/settings.json`. See [INTEGRATION_NOTES.md](INTEGRATION_NOTES.md).

**Run without an API key** (deterministic, rule-based only):

```bash
python main.py --dry-run --steps 3
```

---

## CLI Usage

From the project root:

```bash
python main.py
python main.py --steps 10
python main.py --dry-run --steps 5
python main.py --snapshot /tmp/out.json --steps 5
python main.py --scenario config/scenarios/startup_competitive.json --steps 5
python main.py --narrative --steps 3
python main.py --summary --dry-run --steps 5
python main.py --scenario-text "A startup with founder and investor; 100k cash, 18 month runway" --use-llm-for-agents --steps 5
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

A Flask-based interface for submitting scenarios, running simulations, and viewing results.

### Start the server

```bash
pip install -r requirements.txt
python ui.py
```

Open **http://127.0.0.1:5081** in your browser (default port **5081**).

Options:

```bash
python ui.py --port 8080
python ui.py --host 127.0.0.1    # local only
python ui.py --debug             # Flask debug mode
```

### Main workflows

1. **Submit Scenario** — Enter a short scenario description (e.g. *"Startup with founder and investor; 100k cash, 18 month runway"*). Optionally enable LLM conversion to JSON. Parsed scenario is validated against the schema and displayed.

2. **Run Simulation** — Run the engine with the last submitted scenario. Configure **Steps** and **Dry run**. Step-by-step results and the final snapshot are shown.

3. **View Snapshot** — Load the last saved snapshot from the most recent run.

4. **Graph / Impact View** — After a run, open the graph view to see the causal variable graph and impact analysis (initial vs final state, top drivers, active edges).

5. **Decision Brief** (`POST /api/brief`) — Submit a structured decision (move, actors, constraints, horizon) and receive a brief with likely outcomes, top drivers, second-order effects, hidden assumptions, and kill criteria.

6. **Decision Journal** (`/journal`) — Browse saved decisions, view briefs, and annotate what actually happened.

Snapshots are also written to `data/snapshots/last_snapshot.json`.

### API endpoints (summary)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check (`{"status":"ok"}`) |
| `/api/submit_scenario` | POST | Parse and validate scenario text |
| `/api/run_simulation` | POST | Run simulation |
| `/api/run_simulation_stream` | POST | Stream turn-by-turn results (SSE) |
| `/api/brief` | POST | Build decision brief |
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
   Expected: `{"status":"ok"}`

3. **Behind Nginx:** Simulations and narrative generation can take a long time. Increase timeouts:
   ```nginx
   proxy_read_timeout 300s;
   proxy_send_timeout 300s;
   ```

---

## Scenario Format

Scenarios are JSON files validated by `schemas/scenario_schema.py`.

**Required keys:** `description`, `initial_agents`, `initial_state`, `relations`, `allowed_actions`

**Example** (`config/scenarios/demo_scenario.json`):

```json
{
  "description": "Demo startup: founder and investor with cash and runway.",
  "initial_agents": [
    {"name": "founder", "role": "Founder", "objectives": {"growth": 0.6, "conserve_cash": 0.4}},
    {"name": "investor", "role": "Investor", "objectives": {"runway": 0.5, "governance": 0.5}}
  ],
  "initial_state": {"cash": 100000, "runway_months": 18, "growth": 10, "population": 100},
  "relations": [
    {"from": "founder", "to": "investor", "type": "reports_to"}
  ],
  "allowed_actions": ["launch_discount_campaign", "request_investment", "steady_finance"]
}
```

**Optional extensions:** `causal_links`, `rules`, `events`, `variable_specs`, `action_tradeoffs`, `variable_tradeoffs`, governance fields.

**Bundled scenarios** in `config/scenarios/`:

| File | Description |
|------|-------------|
| `demo_scenario.json` | Startup with founder, investor, community leader |
| `startup_competitive.json` | Competitive startup dynamics |
| `goal_driven_delayed.json` | Goal-driven agents with delayed effects |
| `variable_only_scenario.json` | Variables without named agents |
| `iran_us_standoff.json` | Geopolitical standoff scenario |
| `gulf_standoff.json` | Gulf region standoff scenario |

Free-text scenarios are parsed by `scenario_parser.py` using the configured LLM provider, then validated and normalized.

---

## Architecture (Summary)

```
┌─────────────┐     propose      ┌──────────────────┐
│   Agents    │ ───────────────► │ WorldModelAgent  │
│ (beliefs)   │                  │  (normalize)     │
└─────────────┘                  └────────┬─────────┘
       ▲                                  │ delta
       │ observe (noisy)                  ▼
       │                          ┌──────────────────┐
       │                          │   Governance     │
       │                          └────────┬─────────┘
       │                                   │ apply
       │                                   ▼
       │                          ┌──────────────────┐
       └──────────────────────────│   World Model    │
                                  │ (variables +     │
                                  │  propagation)    │
                                  └────────┬─────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
             Rule engine            Event queue            Provenance trace
                    │                      │                      │
                    └──────────────────────┴──────────────────────┘
                                           │
                                           ▼
                              Narrative engine / Decision brief
```

- **World state:** Causal variable graph (`variables`, `causal_links`); propagation in `core/propagation.py`. Snapshots expose `global_state` for backward compatibility.
- **Agents:** Belief state with noisy observation; decisions use beliefs. Base agent, planner, utility; WorldModelAgent normalizes proposals.
- **Rules & events:** Scenario-defined rules and event queue, including delayed events.
- **Actions:** Abstract actions via `action_spec`; `core/action_interpreter.py` maps to deltas (`increase_variable`, `set_variable`, etc.).
- **Trace & narrative:** Each step appends to provenance; `core/narrative_builder.py` and `core/narrative_engine.py` build structured summaries and turn intelligence.
- **V2 engine:** Domain-agnostic models in `model/`, action DSL in `policy/`, epistemic beliefs in `epistemic/`, full turn pipeline documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## What to Expect

**Default demo agents:**

| Agent | Objectives |
|-------|------------|
| Founder | growth, conserve cash |
| Investor | runway, governance |
| CommunityLeader | engagement, trust |

**Example turn flow:**

1. Founder proposes `launch_discount_campaign`
2. WorldModelAgent normalizes to a numeric delta (e.g. cash −5000, growth +5)
3. Governance validates the delta
4. World model applies changes and propagates along causal links
5. Narrative and provenance are recorded

Each turn prints a compact world snapshot: variables, entities, relations, narrative, version, turn.

### Sample run log (3 turns, dry-run)

```
Running Open World Engine
  steps=3 dry_run=True scenario=.../config/scenarios/demo_scenario.json
--- Turn 1 ---
{
  "entities": {},
  "relations": [...],
  "global_state": { "cash": 100000, "runway_months": 18, "growth": 11, ... },
  "narrative": ["[v0] Rule-based fallback for steady_finance ..."],
  "version": 1,
  "turn": 1
}
...
--- Turn 3 ---
{ ... }
Done.
```

With LLM enabled, proposals and deltas vary; governance still enforces non-negative resources and population constraints.

---

## Project Structure

```
owe/
├── main.py                 # CLI entry point
├── ui.py                   # Web UI server
├── scenario_parser.py      # Free-text → scenario JSON (LLM or rule-based)
├── config/
│   ├── settings.py         # Loads config/settings.json + env
│   ├── settings.json       # Optional local config (do not commit secrets)
│   ├── decision_presets.json
│   └── scenarios/          # Bundled scenario JSON files
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
├── schemas/                # scenario, proposal, delta, decision, memory schemas
├── ui/                     # dashboard_payload, decision_brief
├── summarization/          # NarrativeFacts, renderer, LLM narrator
├── visualization/          # graph_viewer, impact_data
├── templates/              # Flask templates (index, brief, journal, graph, run_viewer)
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

Test coverage includes: determinism, dry-run environment, scenario compiler, pipeline stages, narrative synthesizer, decision schema/brief/presets, kill criteria, calibration, LLM budget, V2 engine, and more.

---

## Documentation

| Document | Contents |
|----------|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Causal graph, beliefs, rule engine, event queue, action contract, trace, narrative |
| [docs/ARCHITECTURE_DOSSIER.md](docs/ARCHITECTURE_DOSSIER.md) | Full architecture dossier |
| [docs/SYSTEM_GUIDE.md](docs/SYSTEM_GUIDE.md) | Pipeline, actions, variables, narrative, configuration |
| [docs/HYBRID_ENGINE.md](docs/HYBRID_ENGINE.md) | Hybrid MC + RL action evaluation |
| [INTEGRATION_NOTES.md](INTEGRATION_NOTES.md) | Reusing sim_app LLM client in the same repo |

---

## License

See repository license file if present.
