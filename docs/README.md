# Enterprise Operations Decision Simulator — Documentation

Product-first docs for operations decision support. Engine internals are secondary.

## Product docs

| Document | Description |
|----------|-------------|
| [PRODUCT_GUIDE.md](PRODUCT_GUIDE.md) | Buyer guide: personas, 30s demo, planning workflow |
| [ADVISOR_PILOT.md](ADVISOR_PILOT.md) | Consultant / S&OP advisor pilot |
| [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md) | Operations API, journal, config |

## Engine docs (engineering)

| Document | Description |
|----------|-------------|
| [ENGINE_INTERNALS.md](ENGINE_INTERNALS.md) | When engineering mode applies; index to engine docs |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Causal graph, beliefs, rules, trace, narrative |
| [ARCHITECTURE_DOSSIER.md](ARCHITECTURE_DOSSIER.md) | Full architecture dossier |
| [HYBRID_ENGINE.md](HYBRID_ENGINE.md) | MC+RL, stochastic gating (not used on product demo) |
| [engine_contracts.md](engine_contracts.md) | Typed contracts |
| [migration_notes.md](migration_notes.md) | Migration notes |



## مسیرهای کلیدی



### محصول (Operations-facing)



- **ورودی وب:** `ui.py` — `/` (Enterprise Operations Decision Simulator)، `/journal`، `/graph`، `/advanced` (غیرفعال در `product_mode`)

- **ساخت سناریو (بدون LLM):** `adapters/ops_scenario_builder.py` — profile + decision template → scenario JSON

- **اسکیما:** `schemas/ops_schema.py`، `schemas/decision_schema.py`

- **خروجی محصول:** `ui/ops_outcomes.py` (verdict، service/cost/risk headlines)، `ui/decision_brief.py`، `ui/turn_trace.py`

- **Journal:** `core/decision_journal.py` — `output/decisions/<id>.json`

- **Config:** `config/ops_presets.json`، `config/ops_decisions.json`



### موتور (Engine)



- **ورودی:** `main.py` (CLI)، `ui.py` (وب — مسیر `/advanced` و APIهای مهندسی)

- **شبیه‌سازی:** `simulation/loop.py`

- **ارزیابی اقدام (MC + RL):** `agents/action_evaluation.py` — امتیاز planner، ارزیابی مونت‌کارلو، انتخاب softmax

- **لایهٔ باور (اختیاری):** `agents/belief_model.py` — BeliefState، به‌روزرسانی باور، belief_alignment، belief_entropy_aggregate؛ فعال با `ENABLE_BELIEF_LAYER`

- **موتور شوک (اختیاری):** `simulation/shock_engine.py` — شوک‌های ماکرو (supply_chain، financial، political، information_warfare)؛ فعال با `SIMULATION_MODE=shock_global`

- **داشبورد زنده:** `ui/dashboard.py` — رویداد هر نوبت، SSE، APIهای `/api/dashboard/*`؛ payload از `ui/dashboard_payload.py` (state_snapshot، risk_report، calibration_metrics، belief_alignment، shock، oracle_analysis، narrative / turn_intelligence، actor_ranking، causal_story، hidden_costs، longitudinal_story)

- **لایهٔ Oracle (مشاور LLM):** `core/oracle.py` — تحلیل مشورتی اقدام پیشنهادی (Confidence، Risk Factors، Alternative Scenarios)؛ فقط برای نمایش و بررسی انسانی؛ فعال با `ENABLE_ORACLE`

- **قالب‌های روایت:** `core/narrative_templates.py` — قالب‌های جهت‌دار برای روایت (relational، state_transition، trajectory)؛ استفاده در `core/narrative_builder.py`

- **پوزیشن‌سازی سازمانی:** `enterprise/positioning.py` — سطوح (Research Edition، Enterprise Core، Enterprise Pro، Government)، feature_flags و ماژول‌های داشبورد به‌ازای هر سطح

- **خروجی تحقیق:** `research/paper_draft.py` — تولید پیش‌نویس markdown از provenance (Abstract، Methodology، Model Architecture، Calibration، Results، Limitations)

- **کالیبراسیون:** `core/calibration.py` — تشخیص نیاز به recalibration (دوره‌ای یا drift)، `apply_recalibration_action()` و ثبت `calibration_event` در provenance/dashboard

- **ارزیابی ریسک:** `core/risk_assessment.py` — خلاصه رفتار عامل‌ها، امتیاز ریسک نوبت بعد، اختیاری tail_risk_from_mc؛ خروجی در `risk_report` داشبورد

- **یادگیر قوانین (offline):** `core/rule_learner.py` — پیشنهاد تغییر سطح strictness یا قوانین governance از تاریخچه (delta, outcome)؛ خروجی برای بررسی انسانی

- **حالت شبیه‌سازی در زمان اجرا:** `core/simulation_mode.py` — وضعیت mutable برای simulation_mode، enable_shocks، enable_uncertainty؛ APIهای get/set برای override بدون ری‌استارت

- **Checkpoint و Rollback:** `simulation/checkpoints.py` — `CheckpointStore` برای نگهداری محدود (turn, snapshot, provenance_slice)؛ `rollback_to_turn()` و `rollback_last_step()` برای بازگردانی

- **فیزیک قطعی مشترک:** `core/physics_core.py` — اعمال delta به‌صورت عددی + propagation بدون نویز و governance؛ استفاده‌شده در MC evaluation و planning برای هم‌تراز شدن با اجرای واقعی وقتی `ENABLE_UNCERTAINTY=False`

- **کالیبراسیون پیش‌بینی عامل‌ها:** `core/prediction_calibration.py` — نگه‌داری MSE و bias تجمعی به‌ازای هر agent و تولید `calibration_weight` برای MC+RL و داشبورد (`per_agent_calibration`)

- **Pipeline سناریو:** `pipeline/orchestrator.py` (مراحل: entity_extractor → variable_discovery → causal_graph_builder → incentive_modeler → objective_validator → action_discovery → model_serializer)

- **تحلیل خروجی:** `core/scenario_analysis_output.py` (Logic Core، Executive Summary، Strategic Analysis با `build_strategic_analysis()`؛ provenance شامل `predicted_deltas`)

- **کلون وضعیت جهان (canonical):** `world/world_state.py` — `clone_world_state()`, `clone_snapshot()`

- **خطاهای Pipeline:** `pipeline/errors.py`

- **شبیه‌سازی ذهنی (Unified Physics):** `core/mental_simulation.py` — اعمال delta با propagation سبک در planner وقتی `causal_links` موجود است؛ استفاده در `agents/planner.py`

- **تحلیل غافلگیری:** `core/surprise_analysis.py` — مقایسهٔ predicted_delta_light با outcome واقعی؛ خروجی در provenance به‌عنوان `surprise_analysis`

- **سنتزگر (تنوع اقدام):** `core/synthesizer.py` — `ensure_action_diversity()` برای حفظ حداقل گزینه در انتخاب اقدام؛ `expected_utility()` برای EU

- **یادگیری علّی (Oracle):** `core/causal_learning.py` — پیشنهاد لینک علّی از الگوی مکرر؛ `apply_belief_drift()` برای به‌روزرسانی اطمینان یال؛ خروجی اختیاری در Oracle به‌صورت `causal_learning_suggestion`

- **فشرده‌سازی trace:** `core/trace_compression.py` — تبدیل provenance به زنجیرهٔ رویداد علّی (Causal Event Chain) برای تحلیل طولانی؛ اختیاری با SLM

- **لایهٔ روایت نوبت‌به‌نوبت (Narrative-Aware Intelligence):** `core/narrative_engine.py` — `generate_turn_narrative()`: خلاصه نوبت، تحلیل بازیگر (هدف‌همسویی، اثر خالص، امتیاز تشدید، طبقه Stabilizer/Escalator)، زنجیره علّی، طبقه‌بندی نتیجه (Strategic Success / Tactical Gain / Mixed / Deterioration)، تفسیر رژیم، یادداشت اطمینان/کالیبراسیون؛ بدون متن دامنهٔ ثابت

- **حافظه روایت:** `core/narrative_memory.py` — ذخیره روایت ساخت‌یافته هر نوبت؛ `append_narrative()`، `generate_longitudinal_story(last_n_turns)` برای «داستان تا اینجا» در داشبورد

- **تشخیص رژیم:** `core/regime_detector.py` — `detect_regime()`: NORMAL / FRAGILE / CRISIS از اشباع متغیرها، رشد آنتروپی و (اختیاری) میانگین کالیبراسیون عامل‌ها؛ برای فیزیک رژیم‌آگاه و داشبورد

