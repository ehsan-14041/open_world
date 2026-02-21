# Open World Engine 2 — Documentation

مستندات موتور شبیه‌سازی چندعاملی Open World Engine 2.

## فهرست اسناد

| سند | توضیح |
|-----|-------|
| [SYSTEM_GUIDE.md](SYSTEM_GUIDE.md) | راهنمای سیستم: pipeline، نحوه استخراج اقدامات، تعامل متغیرها، انگیزه‌های استراتژیک، رفتارهای نوظهور، schema، OptionSet، propagation، narrative firewall، config |
| [ARCHITECTURE.md](ARCHITECTURE.md) | معماری هسته: گراف علّی، حالت باور، rule engine، صف رویداد، قرارداد اقدام، trace، narrative، ماژول‌های V2 |
| [ARCHITECTURE_DOSSIER.md](ARCHITECTURE_DOSSIER.md) | دوسیهٔ معماری: گراف ماژول‌ها، جریان اجرا، مدل state، چرخهٔ delta، نقشهٔ LLM، اجزای ثابت/پویا، محدودیت‌ها، ناسازگاری‌ها |

## مسیرهای کلیدی

- **ورودی:** `main.py` (CLI)، `ui.py` (وب)
- **شبیه‌سازی:** `simulation/loop.py`
- **Pipeline سناریو:** `pipeline/orchestrator.py` (مراحل: entity_extractor → variable_discovery → causal_graph_builder → incentive_modeler → objective_validator → action_discovery → model_serializer)
- **تحلیل خروجی:** `core/scenario_analysis_output.py`
- **خطاهای Pipeline:** `pipeline/errors.py`
