# Enterprise Operations Decision Simulator — Product Guide

**Simulate one operational decision before you make it.**

Decision support for VP Operations, supply chain directors, production planning managers, demand/inventory planning teams, and risk & business continuity leaders.

---

## Who it is for

| Persona | Typical question |
|---------|------------------|
| VP Operations | Should we add capacity or hold inventory given demand volatility? |
| Supply Chain Director | What happens if we switch supplier mix during a lead-time spike? |
| Production Planning Manager | Can we absorb a demand spike without missing service targets? |
| Demand / Inventory Planning | Safety stock up, or expedite reorder — which is better this week? |
| Risk / Business Continuity | What are walk-away signals if service level keeps falling? |

---

## 30-second demo (no API key)

```bash
pip install -r requirements.txt
python ui.py
```

Open **http://127.0.0.1:5081**

1. **Load scenario** — Click **Strained — demand spike, capacity tight** (★ recommended first demo).
2. **Pick a decision** — **Increase safety stock** (pre-selected).
3. **Compare** — Select **Expedite reorder** in the comparison dropdown.
4. **Simulate** — Click **Simulate this decision**.
5. **Review** — One-line verdict, service/cost/risk/delay impact, best & worst case, walk-away signals, next action.
6. **Evidence (optional)** — Open **View impact map** for the causal model behind the numbers.

---

## What you get

| Output | Purpose |
|--------|---------|
| One-line verdict | Decision-ready headline for a planning meeting |
| Service / cost / risk / delay impact | Directional tradeoffs in business language |
| Best & worst case | Bounds for discussion, not forecasts |
| Key drivers & second-order effects | Explain *why* the recommendation holds |
| Walk-away signals | When to stop pursuing this path |
| Next best action | Concrete follow-up for the team |
| Side-by-side comparison | Two decisions on the same operations context |
| Confidence label | How much to trust the directional read |

---

## What it is / is not

**Is:**

- Pre-decision risk and planning support for weekly S&OP-style conversations
- Deterministic, explainable scenario analysis from your inputs
- A memo you can copy, PDF-export, or save to the decision journal

**Is not:**

- A demand forecast or ERP replacement
- Statistical safety-stock optimization (EOQ, MRP, IBP)
- A multi-agent AI demo — the engine runs a causal decision model under the hood

---

## Weekly planning meeting workflow

1. **Before the meeting** — Load a preset matching this week's constraint (supplier delay, demand spike, margin pressure).
2. **During the meeting** — Simulate the top two levers under debate; use comparison cards to frame the tradeoff.
3. **After the meeting** — Save to journal; export PDF for the record; schedule a 30-day check-in.
4. **Follow-up** — Annotate what actually happened in `/journal` to build organizational learning.

---

## Configuration (product path)

| File | Role |
|------|------|
| `config/ops_presets.json` | Demo operations contexts (stable / strained / uncertain) |
| `config/ops_decisions.json` | 12 decision templates (inventory, supplier, capacity, allocation) |
| `adapters/ops_scenario_builder.py` | Builds deterministic scenarios — no LLM on `/` |
| `ui/ops_outcomes.py` | Screenshot-ready verdict and impact copy |

API keys are **not required** for the home-page demo (`dry_run=true` by default).

---

## Related docs

- [README](../README.md) — Install and API reference
- [ADVISOR_PILOT.md](ADVISOR_PILOT.md) — Consultant / advisor white-label workflow
- [ENGINE_INTERNALS.md](ENGINE_INTERNALS.md) — Engineering mode and simulation engine (not buyer-facing)
