# World Model Library

Reusable, composable **world modules**. Each module is one JSON file describing a small
slice of a domain: its variables (with units, ranges and dynamics) and its causal edges
(with polarity, effect range, lag and **evidence provenance**).

```
world_models/
    supply_chain/     port_disruption.json      ← the first vertical slice
    economy/
    energy/
    infrastructure/
    disasters/
    trade/
    society/
```

The design goal is a **library of small composable modules, not a model of the world**.
A run instantiates a `WorldSlice` from one or more modules (`event_sim/world_builder.py`)
and records what it excluded.

## File contract

```jsonc
{
  "id": "port_disruption",
  "domain": "supply_chain",
  "time_unit": "weeks",
  "variables": [
    {
      "id": "shipping_delay",
      "unit": "days",
      "baseline": 4.0,          // the undisturbed level
      "scale": 10.0,            // 1.0 deviation unit = 10 days
      "range": {"min": 0, "max": 60},
      "dynamics": {"response": 0.5},   // fraction of the gap to causal pressure closed per turn
      "observability": "measured",
      "status": "expert_assumption"
    }
  ],
  "edges": [
    {
      "source": "port_capacity",
      "target": "shipping_delay",
      "polarity": "negative",
      "effect": {"low": 0.6, "central": 0.9, "high": 1.3},   // magnitude; polarity carries the sign
      "lag": {"min": 0, "max": 1, "unit": "weeks"},
      "evidence": [],                       // empty ⇒ status may not exceed 'expert_assumption'
      "geography": ["global"],
      "confidence": "medium",
      "status": "expert_assumption",
      "axis": "alternative_capacity"        // which uncertain assumption selects this edge's effect point
    }
  ],
  "axes": [ /* named uncertain dimensions swept to produce trajectories */ ],
  "interventions": [ /* actions the engine can apply — never applied by an LLM directly */ ]
}
```

## Evidence rules (enforced by `event_sim/evidence.py`)

- `status` is **required** on every edge. There is no default meaning "established fact".
- `observed`, `empirical`, `literature_backed` and `historically_calibrated` require at
  least one `evidence` record. Loading fails otherwise.
- `expert_assumption`, `user_assumption` and `ai_hypothesis` are honest defaults, and are
  counted against the module in the evidence-coverage panel.

**No citation in this library was fabricated.** Modules shipped today carry
`expert_assumption` edges with empty evidence lists, and the coverage panel reports that
plainly. Attaching real sources — or fitting coefficients with `core/data_fitting.py` and
promoting edges to `empirical` — is a data task, tracked in `docs/DATA_REQUIREMENTS.md`.
