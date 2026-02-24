# Open World Engine 2 — Documentation

مستندات موتور شبیه‌سازی چندعاملی Open World Engine 2.

## فهرست اسناد

| سند | توضیح |
|-----|-------|
| [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md) | راهنمای سیستم: pipeline، نحوه استخراج اقدامات، تعامل متغیرها، انگیزه‌های استراتژیک، رفتارهای نوظهور، schema، OptionSet، propagation، narrative firewall، config، Live Dashboard، Research Export، Calibration، Risk، Checkpoints |
| [ARCHITECTURE.md](ARCHITECTURE.md) | معماری هسته: گراف علّی، حالت باور، لایهٔ باور پیشرفته، rule engine، صف رویداد، قرارداد اقدام، trace، narrative، ماژول‌های V2، Live Dashboard، Enterprise، Research، Calibration، Risk، Checkpoints |
| [ARCHITECTURE_DOSSIER.md](ARCHITECTURE_DOSSIER.md) | دوسیهٔ معماری: گراف ماژول‌ها، جریان اجرا، مدل state، چرخهٔ delta، نقشهٔ LLM، اجزای ثابت/پویا، محدودیت‌ها، ناسازگاری‌ها |
| [HYBRID_ENGINE.md](HYBRID_ENGINE.md) | موتور هیبرید: سیاست generativity، اجزای تصادفی و گیت‌ها، داشبورد، feature toggles، محدودیت منابع، checkpoint و calibration |

## مسیرهای کلیدی

- **ورودی:** `main.py` (CLI)، `ui.py` (وب)
- **شبیه‌سازی:** `simulation/loop.py`
- **ارزیابی اقدام (MC + RL):** `agents/action_evaluation.py` — امتیاز planner، ارزیابی مونت‌کارلو، انتخاب softmax
- **لایهٔ باور (اختیاری):** `agents/belief_model.py` — BeliefState، به‌روزرسانی باور، belief_alignment، belief_entropy_aggregate؛ فعال با `ENABLE_BELIEF_LAYER`
- **موتور شوک (اختیاری):** `simulation/shock_engine.py` — شوک‌های ماکرو (supply_chain، financial، political، information_warfare)؛ فعال با `SIMULATION_MODE=shock_global`
- **داشبورد زنده:** `ui/dashboard.py` — رویداد هر نوبت، SSE، APIهای `/api/dashboard/*`؛ payload از `core/dashboard_payload.py` (state_snapshot، risk_report، calibration_metrics، belief_alignment، shock، oracle_analysis)
- **لایهٔ Oracle (مشاور LLM):** `core/oracle.py` — تحلیل مشورتی اقدام پیشنهادی (Confidence، Risk Factors، Alternative Scenarios)؛ فقط برای نمایش و بررسی انسانی؛ فعال با `ENABLE_ORACLE`
- **قالب‌های روایت:** `core/narrative_templates.py` — قالب‌های جهت‌دار برای روایت (relational، state_transition، trajectory)؛ استفاده در `core/narrative_builder.py`
- **پوزیشن‌سازی سازمانی:** `enterprise/positioning.py` — سطوح (Research Edition، Enterprise Core، Enterprise Pro، Government)، feature_flags و ماژول‌های داشبورد به‌ازای هر سطح
- **خروجی تحقیق:** `research/paper_draft.py` — تولید پیش‌نویس markdown از provenance (Abstract، Methodology، Model Architecture، Calibration، Results، Limitations)
- **کالیبراسیون:** `core/calibration.py` — تشخیص نیاز به recalibration (دوره‌ای یا drift)، `apply_recalibration_action()` و ثبت `calibration_event` در provenance/dashboard
- **ارزیابی ریسک:** `core/risk_assessment.py` — خلاصه رفتار عامل‌ها، امتیاز ریسک نوبت بعد، اختیاری tail_risk_from_mc؛ خروجی در `risk_report` داشبورد
- **یادگیر قوانین (offline):** `core/rule_learner.py` — پیشنهاد تغییر سطح strictness یا قوانین governance از تاریخچه (delta, outcome)؛ خروجی برای بررسی انسانی
- **حالت شبیه‌سازی در زمان اجرا:** `core/simulation_mode.py` — وضعیت mutable برای simulation_mode، enable_shocks، enable_uncertainty؛ APIهای get/set برای override بدون ری‌استارت
- **Checkpoint و Rollback:** `simulation/checkpoints.py` — `CheckpointStore` برای نگهداری محدود (turn, snapshot, provenance_slice)؛ `rollback_to_turn()` و `rollback_last_step()` برای بازگردانی
- **Pipeline سناریو:** `pipeline/orchestrator.py` (مراحل: entity_extractor → variable_discovery → causal_graph_builder → incentive_modeler → objective_validator → action_discovery → model_serializer)
- **تحلیل خروجی:** `core/scenario_analysis_output.py` (Logic Core، Executive Summary، Strategic Analysis با `build_strategic_analysis()`؛ provenance شامل `predicted_deltas`)
- **کلون وضعیت جهان (canonical):** `world/world_state.py` — `clone_world_state()`, `clone_snapshot()`
- **خطاهای Pipeline:** `pipeline/errors.py`
- **شبیه‌سازی ذهنی (Unified Physics):** `core/mental_simulation.py` — اعمال delta با propagation سبک در planner وقتی `causal_links` موجود است؛ استفاده در `agents/planner.py`
- **تحلیل غافلگیری:** `core/surprise_analysis.py` — مقایسهٔ predicted_delta_light با outcome واقعی؛ خروجی در provenance به‌عنوان `surprise_analysis`
- **سنتزگر (تنوع اقدام):** `core/synthesizer.py` — `ensure_action_diversity()` برای حفظ حداقل گزینه در انتخاب اقدام؛ `expected_utility()` برای EU
- **یادگیری علّی (Oracle):** `core/causal_learning.py` — پیشنهاد لینک علّی از الگوی مکرر؛ `apply_belief_drift()` برای به‌روزرسانی اطمینان یال؛ خروجی اختیاری در Oracle به‌صورت `causal_learning_suggestion`
- **فشرده‌سازی trace:** `core/trace_compression.py` — تبدیل provenance به زنجیرهٔ رویداد علّی (Causal Event Chain) برای تحلیل طولانی؛ اختیاری با SLM
