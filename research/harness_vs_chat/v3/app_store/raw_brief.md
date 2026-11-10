Answer the question below by playing the situation forward 5 stages, as realistically as you can.

فرض کن در نوامبر ۲۰۲۶ کمیسیون اروپا اعلام می‌کند کارمزد ۱۵٪ اپل برای هدایت کاربر به وب و کارمزد ۵٪ آن برای توزیع بیرون از App Store با قانون بازارهای دیجیتال سازگار نیست و به اپل ۶۰ روز مهلت می‌دهد آن‌ها را حذف کند، وگرنه جریمهٔ روزانه می‌شود. چه می‌شود؟

Each stage lasts: دو ماه

Actors:
- apple: شرکت اپل
- european_commission: کمیسیون اروپا
- epic_and_large_developers: Epic و ائتلاف توسعه‌دهندگان بزرگ
- google: شرکت Google

Variables to track (0 to 100):
- apple_eu_take_rate: سهم مؤثر اپل از خریدهای دیجیتال کاربران iOS در اتحادیه اروپا؛ ۰ یعنی اپل هیچ کارمزدی نمی‌گیرد و ۱۰۰ یعنی سطح پیش از DMA (حدود ۳۰٪) (start: 72)
- steering_freedom: آزادی و سهولت توسعه‌دهندگان در هدایت کاربر به خرید بیرون از App Store؛ ۰ یعنی عملاً ممنوع و ۱۰۰ یعنی رایگان و بدون اصطکاک یا صفحه هشدار (start: 40)
- alt_distribution_share: سهم نصب اپ‌های iOS در اتحادیه اروپا که از فروشگاه‌های جایگزین یا وب انجام می‌شود؛ ۰ یعنی تقریباً هیچ و ۱۰۰ یعنی هم‌اندازه App Store (start: 5)
- commission_enforcement_credibility: باور شرکت‌ها و دولت‌ها به اینکه کمیسیون DMA را واقعاً اجرا می‌کند؛ ۰ یعنی تهدیدهایش جدی گرفته نمی‌شود و ۱۰۰ یعنی همه انتظار اجرای کامل و سریع دارند (start: 45)
- eu_us_trade_tension: تنش تجاری اروپا و آمریکا بر سر قواعد دیجیتال؛ ۰ یعنی آرام و ۱۰۰ یعنی تعرفه‌ها و اقدام تلافی‌جویانه رسمی (start: 50)
- eu_feature_parity: برابری امکانات iPhone و Android در اروپا با بقیه جهان؛ ۰ یعنی بسیاری از امکانات تازه در اروپا عرضه نمی‌شوند و ۱۰۰ یعنی برابری کامل (start: 60)
- ios_user_trust: اعتماد کاربران اروپایی به امنیت خرید و نصب اپ روی iPhone؛ ۰ یعنی کلاهبرداری و بدافزار گسترده و ۱۰۰ یعنی هیچ حادثه جدی (start: 80)
- legal_certainty: روشنی و ثبات قواعد کارمزد اپ‌استورها در اروپا؛ ۰ یعنی هیچ‌کس نمی‌داند قاعده نهایی چیست و ۱۰۰ یعنی موضوع حل‌شده و پایدار است (start: 30)

Outside events, already fixed by a draw (use exactly these, add no others):
- stage 1: هیچ
- stage 2: parliament_enforcement_resolution: پارلمان اروپا با اکثریت بالا قطعنامه‌ای تصویب می‌کند که از کمیسیون اجرای فوری و بدون مصالحه DMA را می‌خواهد. (عقب‌نشینی را برای کمیسیون از نظر سیاسی پرهزینه‌تر می‌کند و موضع ائتلاف توسعه‌دهندگان را تقویت می‌کند.)
- stage 3: parliament_enforcement_resolution: پارلمان اروپا با اکثریت بالا قطعنامه‌ای تصویب می‌کند که از کمیسیون اجرای فوری و بدون مصالحه DMA را می‌خواهد. (عقب‌نشینی را برای کمیسیون از نظر سیاسی پرهزینه‌تر می‌کند و موضع ائتلاف توسعه‌دهندگان را تقویت می‌کند.)
- stage 4: هیچ
- stage 5: other_regulator_moves: یک تنظیم‌گر خارجی مانند CMA بریتانیا یا JFTC ژاپن دستور مشابهی درباره کارمزد هدایت صادر می‌کند. (خطر سرایت جهانی را برای اپل و Google بیشتر می‌کند و موضع کمیسیون را مشروع‌تر نشان می‌دهد.)

Limits:
- Every variable stays within 0 to 100 and moves at most 25 points in one stage.
- In each stage every actor takes ONE action, written as short free text of at most 15 words (Persian).
- Actors may exchange private messages: at most two per actor per stage, at most 30 words each; a message
  is read by its recipient at the start of the next stage.

Write your answer as one JSON object (UTF-8, no BOM, no markdown fence, nothing else) to the answer path you
were given. Persian text fields in Persian. Shape:
{"stages": [ {"actions": {"<actor name>": {"chosen_action": "...", "justification": "<the actor's real reason, at most 40 words>"}, ... all four actors ...},
              "messages": [{"from": "<actor>", "to": "<actor>", "text": "..."}, ...],
              "summary": "<what publicly happened in this stage, at most 60 words>",
              "state": {"<variable>": <number>, ... every variable ...}}, ... 5 stages ... ]}

Actor names: apple, european_commission, epic_and_large_developers, google
Variable names: apple_eu_take_rate, steering_freedom, alt_distribution_share, commission_enforcement_credibility, eu_us_trade_tension, eu_feature_parity, ios_user_trust, legal_certainty
