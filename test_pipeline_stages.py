#!/usr/bin/env python3
"""Run pipeline and report which stage fails (if any)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCENARIO = """در وضعیت فعلی تنش بین ایران و آمریکا، دو روند همزمان در حال پیشرفت است: از یک سو، گفتگوهای غیرمستقیم هسته‌ای بین دو طرف در ژنو ادامه دارد و قرار است دور سوم این مذاکرات برگزار شود، اگرچه ایران خواستار توافق سریع و نتیجه‌محور است و توافق‌های موقت را رد می‌کند، و اختلاف بر سر جزئیات همچنان باقی است. تهران همچنین نشان داده که «سطح قابل‌توجهی از انعطاف» در موضوع غنی‌سازی ارائه کرده تا از تشدید نظامی جلوگیری کند، اما واشنگتن خواستار محدودیت‌های بزرگ‌تر بر برنامه هسته‌ای است و تا زمانی که به نتایج ملموس نرسد، فشارها ادامه خواهد یافت.

همزمان ایالات متحده حضور نظامی قابل‌توجهی در خاورمیانه برقرار کرده است و مقام‌های واشنگتن تهدید به اقدام نظامی محدود یا شدید کرده‌اند، به‌حدی که دیپلمات‌های غیرضروری خود را از برخی کشورها مانند لبنان خارج می‌کند و تحلیل‌گران از افزایش احتمال درگیری ناخواسته صحبت می‌کنند. در داخل ایران نیز فشارهای سیاسی و اقتصادی، از جمله اعتراضات گسترده، به تصمیم‌گیری در مورد مذاکرات و استراتژی دفاعی تأثیر می‌گذارند. این هم‌پوشانی فشارهای دیپلماتیک، نظامی و داخلی نشان می‌دهد که پارامترهای کلیدی تعیین‌کننده آینده تنش شامل سطح پیشرفت مذاکرات، میزان حضور نظامی آمریکا در منطقه، واکنش‌های داخلی ایران و تحولات منطقه‌ای باشند — و هر کدام می‌توانند احتمال تشدید یا کاهش بحران را تغییر دهند."""

def main():
    from core.llm_client import call_llm
    from pipeline.errors import PipelineError

    def llm_client(prompt: str, system: str | None = None, *, as_json: bool = False):
        return call_llm(prompt, system=system, as_json=as_json)

    config = {"debug_llm": True}
    try:
        from pipeline.orchestrator import run_pipeline
        print("Running full pipeline (5 stages)...")
        result = run_pipeline(SCENARIO, llm_client, config)
        print("OK. Scenario keys:", list(result.keys()))
        return 0
    except PipelineError as e:
        print("PipelineError:", e.stage_name, "|", e.message)
        return 1
    except Exception as e:
        print(type(e).__name__, str(e))
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
