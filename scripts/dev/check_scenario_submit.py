#!/usr/bin/env python3
"""Test submit_scenario pipeline with a given scenario (uses config/settings.json)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCENARIO_TEXT = """در وضعیت فعلی تنش بین ایران و آمریکا، دو روند همزمان در حال پیشرفت است: از یک سو، گفتگوهای غیرمستقیم هسته‌ای بین دو طرف در ژنو ادامه دارد و قرار است دور سوم این مذاکرات برگزار شود، اگرچه ایران خواستار توافق سریع و نتیجه‌محور است و توافق‌های موقت را رد می‌کند، و اختلاف بر سر جزئیات همچنان باقی است. تهران همچنین نشان داده که «سطح قابل‌توجهی از انعطاف» در موضوع غنی‌سازی ارائه کرده تا از تشدید نظامی جلوگیری کند، اما واشنگتن خواستار محدودیت‌های بزرگ‌تر بر برنامه هسته‌ای است و تا زمانی که به نتایج ملموس نرسد، فشارها ادامه خواهد یافت.

همزمان ایالات متحده حضور نظامی قابل‌توجهی در خاورمیانه برقرار کرده است و مقام‌های واشنگتن تهدید به اقدام نظامی محدود یا شدید کرده‌اند، به‌حدی که دیپلمات‌های غیرضروری خود را از برخی کشورها مانند لبنان خارج می‌کند و تحلیل‌گران از افزایش احتمال درگیری ناخواسته صحبت می‌کنند. در داخل ایران نیز فشارهای سیاسی و اقتصادی، از جمله اعتراضات گسترده، به تصمیم‌گیری در مورد مذاکرات و استراتژی دفاعی تأثیر می‌گذارند. این هم‌پوشانی فشارهای دیپلماتیک، نظامی و داخلی نشان می‌دهد که پارامترهای کلیدی تعیین‌کننده آینده تنش شامل سطح پیشرفت مذاکرات، میزان حضور نظامی آمریکا در منطقه، واکنش‌های داخلی ایران و تحولات منطقه‌ای باشند — و هر کدام می‌توانند احتمال تشدید یا کاهش بحران را تغییر دهند."""

def main():
    from scenario_parser import parse_scenario_text
    print("Testing parse_scenario_text(use_llm=True) with Iran-US scenario...")
    print("(Config: config/settings.json, provider: avalai)")
    try:
        scenario = parse_scenario_text(SCENARIO_TEXT, use_llm=True)
        print("OK: scenario parsed successfully.")
        print("Keys:", list(scenario.keys()))
        if scenario.get("initial_agents"):
            print("Agents:", [a.get("name") for a in scenario["initial_agents"]])
        if scenario.get("initial_state"):
            print("State vars:", list(scenario["initial_state"].keys())[:8])
        return 0
    except Exception as e:
        print("FAIL:", type(e).__name__, str(e))
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
