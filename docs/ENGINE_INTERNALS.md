# Engine internals (engineering only)

The **Enterprise Operations Decision Simulator** product at `/` does **not** use the features below. The demo path is:

`ops_profile` + `decision_id` → `adapters/ops_scenario_builder.py` → `SimulationLoop(dry_run=True)` → `ui/ops_outcomes.py`

No LLM, MC+RL, belief layer, or free-text scenario parsing runs on that path.

---

## Open World Engine

The repository includes **Open World Engine** — a causal variable graph with optional multi-agent simulation, used for engineering and research workflows (`/advanced`, CLI, API with free-text scenarios).

| Topic | Document |
|-------|----------|
| Architecture overview | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Full dossier | [ARCHITECTURE_DOSSIER.md](ARCHITECTURE_DOSSIER.md) |
| Hybrid MC+RL, stochastic gating | [HYBRID_ENGINE.md](HYBRID_ENGINE.md) |
| System guide (pipelines, config) | [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md) |

## When to use engineering mode

- Custom scenario JSON or free-text → LLM pipeline
- Live dashboard / SSE streaming
- Narrative intelligence, actor ranking, research export
- Belief layer, shocks, MC+RL action selection

Set `product_mode: false` in `config/settings.json` to expose `/advanced` from the product server.
