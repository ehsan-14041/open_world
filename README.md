# Open World Engine

موتور شبیه‌سازی چندعاملی (multi-agent) با WorldModelAgent، RoleAgents، حاکمیت و هستان‌شناسی. گراف متغیرهای علّی با انتشار، حالت باور عامل (مشاهده نویزی)، قوانین و رویدادهای تعریف‌شده در سناریو، مفسر اقدام و روایت ساخته‌شده از ردیابی شبیه‌سازی پشتیبانی می‌شود. جزئیات: [Architecture](docs/ARCHITECTURE.md).

## Requirements

- Python **3.10+**
- وابستگی‌ها: **pydantic**, **openai**, **flask** (مشاهده `requirements.txt`)

## Install

```bash
cd open_world_engine2
pip install -r requirements.txt
```

Using a virtual environment (recommended):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py --dry-run --steps 3
```

## Configuration

تنظیمات از **`config/settings.json`** (اختیاری) خوانده می‌شوند و سپس با متغیرهای محیطی بازنویسی می‌شوند.

- **فایل config:** برای مسیر دیگر `OWE_CONFIG` را تنظیم کنید (مثلاً `OWE_CONFIG=/path/to/settings.json`).
- **سناریو:** `scenario_path` در config یا `OWE_SCENARIO_PATH` در env. پیش‌فرض: `config/scenarios/demo_scenario.json`.
- **Dry run:** `dry_run` در config یا `OWE_DRY_RUN=true` در env.
- **Snapshot:** `snapshot_path` در config یا `OWE_SNAPSHOT_PATH` در env.
- **LLM provider:** `llm_provider` در config (`avalai` یا `groq`) یا متغیر محیطی `LLM_PROVIDER`. پیش‌فرض: `avalai`.
- **تنظیمات پراوایدر:** برای هر پراوایدر در config می‌توانید بلوک `avalai` یا `groq` تعریف کنید: `api_key`, `base_url`, `model`, `temperature`, `max_tokens`, `timeout`.
- **سایر گزینه‌ها:** `max_llm_calls_per_turn`, `enable_uncertainty`, `debug_llm`, `delta_magnitude_cap`, `random_seed`, `meta_proposal_auto_approve_max_agents`, `enable_environment_agent`, `enable_meta_actions`, `max_delta`, `obs_noise_scale`, `proposal_throttle_turns`, `propagation_max_iter`, `propagation_epsilon`, `propagation_damping`, `phase_top_k_turns`, `allow_numbers`, `enable_shocks`, `lang` (در config یا با پیشوند `OWE_*` در env). لیست کامل: `config/settings.py`.

## API key

- **با sim_app:** موتور می‌تواند از کلاینت LLM موجود استفاده کند. `GROQ_API_KEY` یا `AVALAI_API_KEY` را در محیط یا در `sim_app/settings.json` تنظیم کنید. [INTEGRATION_NOTES.md](INTEGRATION_NOTES.md).
- **Standalone:** کلید API را در `config/settings.json` در `avalai.api_key`, `groq.api_key` یا `openai.api_key` قرار دهید، یا از env: `AVALAI_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`. برای endpoint سازگار با OpenAI: `OPENAI_BASE_URL`, `OPENAI_MODEL` (پیش‌فرض: `https://api.openai.com/v1`, `gpt-4o-mini`).

اجرای بدون کلید API (فقط قطعی و مبتنی بر قانون):

```bash
python main.py --dry-run --steps 3
```

## Run

از پوشه `open_world_engine2`:

```bash
python main.py
python main.py --steps 10
python main.py --dry-run --steps 5
python main.py --snapshot /tmp/out.json --steps 5
python main.py --scenario config/scenarios/startup_competitive.json --steps 5
python main.py --narrative --steps 3
python main.py --summary --dry-run --steps 5
python main.py --scenario-text "استارتاپ با بنیان‌گذار و سرمایه‌گذار؛ ۱۰۰هزار نقد، ۱۸ ماه runway" --use-llm-for-agents --steps 5
```

| Option | Description |
|--------|-------------|
| `--steps N` | تعداد گام‌های شبیه‌سازی (پیش‌فرض: 5). |
| `--dry-run` | غیرفعال کردن LLM؛ فقط پیشنهادها و دلتاهای مبتنی بر قانون. |
| `--snapshot path` | ذخیره اسنپ‌شات نهایی جهان به صورت JSON در مسیر داده‌شده. |
| `--scenario path` | مسیر فایل سناریو JSON (پیش‌فرض: `config/scenarios/demo_scenario.json`). |
| `--scenario-text "..."` | متن آزاد سناریو؛ با LLM به JSON تبدیل شده و سپس شبیه‌سازی اجرا می‌شود. |
| `--use-llm-for-agents` | همراه با `--scenario-text`: تولید تعریف عامل‌ها (شخصیت، متغیرهای اولیه) با LLM. |
| `--narrative` | چاپ روایت نهایی ساخته‌شده از provenance و حالت جهان. |
| `--summary` | چاپ فقط خلاصهٔ ساخت‌یافتهٔ یک‌پاراگرافی جهان. |

## Project structure

```
open_world_engine2/
├── main.py              # CLI entry
├── ui.py                # Web UI server
├── scenario_parser.py   # Free-text → scenario JSON (LLM or rule-based)
├── config/
│   ├── settings.py      # Loads config/settings.json + env
│   ├── settings.json    # Optional config file (api_key حساس است؛ در repo واقعی commit نکنید)
│   └── scenarios/       # demo_scenario.json, startup_competitive.json, goal_driven_delayed.json, variable_only_scenario.json, iran_us_standoff.json, gulf_standoff.json
├── simulation/
│   └── loop.py          # SimulationLoop
├── agents/              # base_agent, world_model_agent, RoleAgents (agents.py), memory, planner, utility
├── core/                # llm_client, llm_action_guard, world_summarizer, governance, world_model, ontology_manager,
│                        # agent_constructor, agent_generator, prompt_builder, propagation, rule_engine, event_queue,
│                        # action_interpreter, observation, narrative_builder
├── world/               # world_state, delayed_events
├── schemas/             # scenario_schema, proposal_schema, delta_schema, llm_action_schema, memory_schema
├── utils/               # id_generator, logging
├── docs/
│   ├── README.md        # فهرست اسناد
│   ├── SYSTEM_GUIDE.md  # Pipeline، actions، variables، narrative، config
│   ├── ARCHITECTURE.md  # Causal graph، beliefs، rules، events، trace، narrative
│   └── ARCHITECTURE_DOSSIER.md  # دوسیهٔ معماری کامل
├── data/snapshots/      # last_snapshot.json (written by runs)
├── templates/           # Flask templates for Web UI (index.html, graph.html, run_viewer.html)
├── static/              # Static assets for Web UI (CSS, JS)
├── visualization/       # Graph visualization (graph_viewer.py, impact_data.py)
└── tests/               # test_uncertainty.py, test_text_first.py
```

## Web UI

رابط وب ساده برای وارد کردن سناریو به صورت متن آزاد، تبدیل به JSON سناریو (با scenario parser + LLM) و اجرای شبیه‌سازی با نتایج زنده.

1. **اجرای UI** (از پوشه `open_world_engine2`):

   ```bash
   pip install -r requirements.txt   # includes Flask
   python ui.py
   ```

   سپس در مرورگر **http://127.0.0.1:5000** را باز کنید. سرور به‌طور پیش‌فرض به `0.0.0.0` متصل می‌شود. اختیاری: `python ui.py --port 8080`, `--host 127.0.0.1` (فقط لوکال), یا `--debug` (حالت دیباگ Flask).

2. **Submit Scenario** – توضیح کوتاه سناریو را وارد کنید (مثلاً *"استارتاپ با بنیان‌گذار و سرمایه‌گذار؛ ۱۰۰هزار نقد، ۱۸ ماه runway"*)، در صورت تمایل «Use LLM to convert to JSON» را بزنید و **Submit Scenario** را کلیک کنید. JSON سناریوی پارس‌شده (اعتبارسنجی با schema) در ناحیه نتیجه نمایش داده می‌شود.

3. **Run Simulation** – **Run Simulation** را بزنید تا موتور با آخرین سناریوی ثبت‌شده اجرا شود. **Steps** و **Dry run** را تنظیم کنید. نتایج گام‌به‌گام و اسنپ‌شات نهایی نمایش داده می‌شود.

4. **View Snapshot** – **View Snapshot** را بزنید تا آخرین اسنپ‌شات ذخیره‌شده از آخرین اجرا نمایش داده شود.

5. **Graph / Impact View** – بعد از اجرا، **View Snapshot** را باز کنید و از نمای گراف برای دیدن گراف متغیرهای علّی و نمای impact (حالت اولیه در برابر نهایی، مهم‌ترین عوامل، یال‌های فعال) استفاده کنید.

اسنپ‌شاتها همچنین در `data/snapshots/last_snapshot.json` ذخیره می‌شوند.

### رفع خطای 503 (Service Unavailable)

خطای **503** معمولاً یعنی درخواست به پروکسی رسیده ولی **اپ Flask در دسترس نیست** یا **تایم‌اوت شده**.

1. **مطمئن شوید سرور روشن است:**
   ```bash
   cd open_world_engine2 && python ui.py --port 5080
   ```
   یا با systemd: `sudo systemctl start open-world-ui`

2. **تست سلامت:** `curl http://127.0.0.1:5080/health` باید `{"status":"ok"}` برگرداند.

3. **اگر پشت Nginx هستید:** شبیه‌سازی و خلاصه‌سازی ممکن است طولانی شود. در `location` مربوطه تایم‌اوت را افزایش دهید:
   ```nginx
   proxy_read_timeout 300s;
   proxy_send_timeout 300s;
   ```
   (خلاصه‌سازی `/api/narrative` هم برای traceهای بزرگ ممکن است چند ده ثانیه طول بکشد.)

## Scenario parser

سناریوهای متنی با `scenario_parser.py` و با استفاده از کلاینت LLM تنظیم‌شده (AvalAI، Groq یا OpenAI) به JSON سناریو تبدیل می‌شوند. خروجی با `schemas/scenario_schema.py` اعتبارسنجی می‌شود (کلیدهای الزامی: `description`, `initial_agents`, `initial_state`, `relations`, `allowed_actions`). برای شکل مورد انتظار JSON به فایل‌های سناریو در `config/scenarios/` مراجعه کنید.

## Architecture (summary)

- **World state:** Causal variable graph (`variables`, `causal_links`); propagation in `core/propagation.py`. Snapshot exposes `global_state` for backward compatibility.
- **Agents:** Belief state with noisy observation (`core/observation.py`); decisions use beliefs. Base agent, planner, utility; WorldModelAgent normalizes proposals.
- **Rules & events:** Scenario-defined rules (`core/rule_engine.py`) and event queue (`core/event_queue.py`), including delayed_events.
- **Actions:** Abstract actions via action_spec; `core/action_interpreter.py` maps to deltas (e.g. increase_variable, set_variable).
- **Trace & narrative:** Each step appends to trace; `core/narrative_builder.py` builds a structured summary (and optionally LLM narrative) from the trace.

Full details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## What to expect

- **Agents:** Founder (growth, conserve cash), Investor (runway, governance), CommunityLeader (engagement, trust).
- **Example flow:** Founder proposes e.g. `launch_discount_campaign` → WorldModelAgent normalizes to a numeric delta (e.g. cash -5000, growth +5) → Governance validates → World model updates (with propagation if causal_links exist); narrative and trace are recorded.
- Each turn prints a compact world snapshot (variables/global_state, entities, relations, narrative, version, turn).

## Sample run log (3 turns, dry-run)

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

With LLM enabled, proposals and deltas will vary; governance still enforces non-negative resources and population.

## Tests

از پوشه `open_world_engine2`:

```bash
pip install -r requirements.txt
pip install pytest
pytest tests/ -v
```

## See also

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — گراف علّی، باورها، rule engine، صف رویداد، قرارداد اقدام، trace و narrative.
- [INTEGRATION_NOTES.md](INTEGRATION_NOTES.md) — استفاده مجدد از کلاینت LLM مربوط به `sim_app` در همان مخزن.
