# گزارش‌های آزمون انجین روی صنعت بازی ایران

اکتشافی و اعتبارسنجی‌نشده. همهٔ ضرایب مدل فرض کارشناسی‌اند و استودیوها نمونه‌اند.

| فایل | چیست |
|---|---|
| [`REPORT.md`](REPORT.md) | گزارش متنی: داده‌های استخراج‌شده، مدل، نتیجه‌ها، محک با تاریخ، محدودیت‌ها |
| [`engine_game_report.html`](engine_game_report.html) | گزارش تصویری به زبان ساده: یک استودیو در جهش دلار و قطعی اینترنت چه کند |
| [`engine_game_report_technical.html`](engine_game_report_technical.html) | نسخهٔ اول و فنی همان گزارش: سازوکار شوک، مسیر نقدینگی، شمارش ۷۲۹ حالت، جدول تعیین‌کننده‌ها، محک |
| [`game_outlook.html`](game_outlook.html) | پیش‌بینی شرطی یک‌ساله (مهر ۱۴۰۵ تا مهر ۱۴۰۶) در پنج حالت |
| `results.json` | خروجی `study.py`: نتیجهٔ هشت وضعیت، شمارش ۷۲۹ ترکیب، آزمون برابری با انجین |
| `outlook.json` | خروجی `outlook.py`: پیش‌بینی یک‌ساله |
| `engine_game_report_data.json` | داده‌های نمودارهای گزارش تصویری |

صفحه‌های HTML بدون اینترنت هم باز می‌شوند؛ فقط فونت از Google Fonts می‌آید.

ساختن دوباره، از ریشهٔ مخزن:

```
python research/iran_game_studio/study.py
python research/iran_game_studio/outlook.py
python research/iran_game_studio/pages/build_pages.py
```

مدل و کدها در [`research/iran_game_studio/`](../../research/iran_game_studio/) هستند.
