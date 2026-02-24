#!/usr/bin/env python3
"""Test only Incentive Modeling stage: call LLM and print raw response (no parse)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main():
    from core.llm_client import call_llm
    # Minimal input as would be passed to IncentiveModeler after stages 1–3
    entities = [{"name": "iran", "role": "state"}, {"name": "usa", "role": "state"}]
    variables = {"negotiation_progress": 50.0, "military_pressure": 50.0, "domestic_pressure": 50.0}
    scenario_snippet = "تنش ایران و آمریکا، مذاکرات هسته‌ای، فشار نظامی."

    import json
    actors_json = json.dumps([{"name": e.get("name"), "role": e.get("role")} for e in entities], ensure_ascii=False)
    variables_json = json.dumps(variables, ensure_ascii=False)
    user = f"""Actors:
{actors_json}

World Variables:
{variables_json}

Scenario context:
{scenario_snippet}"""

    system = """You are designing autonomous strategic agents.
For each actor, define a strategic model with:
- objectives: weighted preferences over variables (e.g. {"increase_stability": 0.6, "decrease_tension": 0.4})
- trade_offs: optional list of trade-offs
- capabilities: list of capability tags (e.g. ["diplomatic", "military"])
- risk_tolerance: float 0-1 (default 0.5)
- aggressiveness: float 0-1 (default 0.5)
- strategic_constraints: optional list

Return JSON object only:
{"actor_name": {"objectives": {"increase_X": weight}, "trade_offs": [], "capabilities": [], "risk_tolerance": 0.5, "aggressiveness": 0.5, "strategic_constraints": []}}
Each objective must reference an existing world variable. Output JSON only."""

    print("Calling LLM (as_json=True) for Incentive Modeling...")
    try:
        out = call_llm(user, system=system, as_json=True)
        print("Type:", type(out))
        print("Response:", out if isinstance(out, dict) else repr(out)[:500])
        if isinstance(out, dict):
            print("Keys:", list(out.keys()))
        return 0
    except Exception as e:
        print("Error:", type(e).__name__, str(e))
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
