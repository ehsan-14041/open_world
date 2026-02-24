#!/usr/bin/env python3
"""Call submit_scenario logic in-process (no server). Single short scenario."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Short scenario to avoid long runs
SHORT = """تنش ایران و آمریکا. مذاکرات هسته‌ای در ژنو. دو بازیگر: ایران و آمریکا. متغیرها: پیشرفت مذاکرات، فشار نظامی."""

def main():
    from scenario_parser import parse_scenario_text
    print("Parse short scenario (use_llm=True)...")
    try:
        s = parse_scenario_text(SHORT, use_llm=True)
        print("OK. Keys:", list(s.keys()))
        return 0
    except Exception as e:
        print("FAIL:", type(e).__name__, str(e))
        return 1

if __name__ == "__main__":
    sys.exit(main())
