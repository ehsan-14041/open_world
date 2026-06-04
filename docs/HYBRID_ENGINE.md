# Hybrid Simulation Engine

This document describes the Hybrid Simulation Engine: LLM-driven agents plus rule-based deterministic systems, stochastic gating, and governance.

## Generativity Policy

- **LLM freedom:** The LLM may propose novel actions, variables, or events. Domain-specific assumptions are not hardcoded; the engine allows creative proposals.
- **Pruning only when necessary:** Proposals are pruned or filtered only when they violate governance/safety rules or exceed the configured compute budget. Otherwise they are normalized and validated (with optional auto-repair), not rejected for being "unknown."
- **Selection preserves diversity:** Action selection uses probabilistic mechanisms (softmax with non-zero temperature). Temperature is clamped to a minimum (e.g. `MC_RL_TEMPERATURE_MIN`) so that selection never collapses to pure argmax. This preserves exploration and creativity.

## Stochastic Components and Gating

Stochastic behavior is controlled by explicit flags so that runs can be deterministic when needed.

| Flag | Purpose |
|------|---------|
| `ENABLE_UNCERTAINTY` | When true, Gaussian noise is applied after deterministic propagation (per variable, magnitude capped e.g. 20% of primary delta). When false (and `ENABLE_SHOCKS` false and fixed `RANDOM_SEED`), runs are deterministic. |
| `ENABLE_SHOCKS` | When true and `SIMULATION_MODE=shock_global`, the shock engine may apply macro shocks. When false or mode is `standard`, no shock sampling. |
| `ENABLE_STOCHASTIC_EVENTS` | When true, delayed/env events with a `probability` field are sampled. When false (deterministic mode), treat probability as 1.0 or 0.0 by threshold. |

- **Noise model:** Gaussian per variable; magnitude capped (e.g. 20% of primary delta); gated by `ENABLE_UNCERTAINTY`. Implemented in `core/world_model.py` `_apply_final_noise()`.
- **Effect on agents:** Observation noise (if any) affects the belief snapshot passed to agents; world noise is applied after deterministic propagation so propagation remains reproducible when uncertainty is off.
- **Shock engine:** `simulation/shock_engine.py`; active only when `SIMULATION_MODE=shock_global` (and typically `ENABLE_SHOCKS` true).

## Dashboard Data Independence

Dashboard payload is produced in **`core/dashboard_payload`** from `(snapshot, provenance_entry, scenario, agents_list, provenance_history)`. This module has **no UI dependency**; it performs only lightweight arithmetic and dict building. The payload is JSON-serializable and suitable for API or external consumers. It includes core metrics (state_snapshot, risk_report, calibration_metrics, selected_action, etc.) and, when narrative is enabled, **narrative payload** (narrative, turn_intelligence, actor_ranking, causal_story, hidden_costs, longitudinal_story) from `core/narrative_engine` and `core/narrative_memory`. The UI layer (`ui/dashboard`) and simulation loop call `build_dashboard_payload(...)` and pass the result to the front-end; external systems can call the same function with the same inputs.

## Feature Toggles

| Toggle | Default | Effect |
|--------|---------|--------|
| `ENABLE_MC_RL` / `MC_RL_ENABLED` | True | When true, action selection uses MC evaluation + RL weights + softmax. When false, use planner-only (e.g. plan_depth2) path. |
| `ENABLE_BELIEF_LAYER` | False | When true, belief state and belief alignment are updated and can influence scoring. |
| `ENABLE_SHOCKS` | False | When true, shock engine can be active if `SIMULATION_MODE=shock_global`. |
| `ENABLE_UNCERTAINTY` | False | When true, apply Gaussian noise after propagation. |
| `ENABLE_STOCHASTIC_EVENTS` | follows uncertainty | When true, event probability sampling for delayed/env events. |
| `CHECKPOINT_ENABLED` | False | When true, push checkpoints each step and allow rollback_to_turn / rollback_last_step. |
| `ENABLE_ORACLE` | False | When true, each turn an LLM advisory (Oracle) analyzes the selected action and produces Confidence, Risk Factors, Alternative Scenarios; output is for dashboard and human review only—no state change. See `core/oracle.py`. |

## Deterministic Physics and Calibration

- **Deterministic physics core (`core/physics_core.py`):** MC evaluation (`run_mc_evaluation`)، امتیازدهی planner (`get_planner_scores`) و depth‑2 planning همگی از `apply_delta_deterministic()` روی snapshotهای کپی‌شده استفاده می‌کنند. این مسیر فقط `numeric_updates` و propagation را اعمال می‌کند (بدون نویز و governance) و باعث می‌شود وقتی `ENABLE_UNCERTAINTY=False` است، مدار عددی که در planning/MC دیده می‌شود با اجرای واقعی سازگار بماند.
- **کالیبراسیون پیش‌بینی (`core/prediction_calibration.py`):** برای هر عامل، MSE و bias تجمعی بین `delta_raw_per_agent` و `self_effect_per_agent` را نگه می‌دارد و از آن یک `calibration_weight` محدودشده می‌سازد. این وزن در MC+RL برای نرم‌کردن/تقویت امتیازهای LLM/MC استفاده می‌شود و در داشبورد به‌صورت `per_agent_calibration` نمایش داده می‌شود.
- **هم‌ترازسازی Hybrid Engine:** با ترکیب physics قطعی، MC+RL، belief layer اختیاری و کالیبراسیون پیش‌بینی، سیستم هم‌زمان (۱) خلاقیت LLM، (۲) رفتار قابل توضیح و (۳) پایداری عددی را حفظ می‌کند.

## Performance and Resource Limits

- **MC_N_SIMS:** Default 3, max 5 (used for MC evaluation).
- **MC_KEY_VARS:** Default 5 (number of key variables for MC/risk).
- **MAX_LLM_CALLS_PER_AGENT_PER_TURN:** Default 2; per-agent cap to avoid runaway LLM use.
- **