# Integration notes

## Reused files (when run from repo)

When the engine is run from the same repository that contains `sim_app`, the following are reused:

- **`sim_app/llm_client.py`** – `generate_json`, `generate_text` (OpenAI-compatible API).
- **`sim_app/config.py`** – `get_llm_provider_config(provider)` for base_url, api_key, model, etc.

The engine adds `sim_app` to `sys.path` and calls these so that a single API key (e.g. Groq or AvalAI) can be used for both sim_app and open_world_engine.

## How to swap in the real LLM client

1. **Use sim_app from repo:** Run from the repo root or ensure the repo root is on `PYTHONPATH`, and that `sim_app` is the directory containing `llm_client.py` and `config.py`. The engine will detect and use them automatically.

2. **Replace the wrapper:** To force a different client, edit `core/llm_client.py`:
   - Either change `_call_llm_sim_app` to call your client (e.g. direct `from sim_app.llm_client import generate_json` and build messages the same way),
   - Or replace the body of `call_llm` with a single call to your API (e.g. `your_client.chat(prompt, system=system, json_mode=as_json)`).

3. **Standalone:** If `sim_app` is not present or not on path, the engine uses the fallback in `core/llm_client.py` that reads `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` from `config/settings.py` (or env) and uses the `openai` package.

No other files in `sim_app` or the rest of the repo are modified; all new code lives under `open_world_engine2/`.
