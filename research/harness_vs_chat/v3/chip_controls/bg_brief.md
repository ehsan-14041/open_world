Answer the question below by playing the situation forward 5 stages, as realistically as you can.

Situation and question: از اکتبر ۲۰۲۲ آمریکا فروش تراشه‌های پیشرفته هوش مصنوعی و ابزار ساخت آن‌ها به چین را محدود کرده است. در آوریل ۲۰۲۵ فروش H20 متوقف شد و Nvidia حدود ۴.۵ میلیارد دلار زیان ثبت کرد. در دسامبر ۲۰۲۵ دولت Trump فروش H200 را با سهم ۲۵ درصدی برای دولت مجاز کرد و در ژانویه ۲۰۲۶ اداره BIS بررسی موردی مجوز را جایگزین «فرض رد» کرد؛ اما گمرک چین ورود H200 را متوقف کرد و Nvidia در پیش‌بینی‌های ۲۰۲۶ خود هیچ درآمد مرکز داده از چین فرض نمی‌کند. آتش‌بس تجاری نوامبر ۲۰۲۵ که چین در آن کنترل‌های تازه بر عناصر خاکی نادر را معلق کرد، عمدتاً یک‌ساله بود و اکنون به پایان مهلت خود رسیده است. مجلس نمایندگان در ژانویه ۲۰۲۶ قانون امنیت دسترسی از راه دور را با ۳۶۹ رأی در برابر ۲۲ تصویب کرد و وزارت بازرگانی پیش‌نویس قاعده‌ای برای بستن اجاره پردازش از مراکز داده جنوب شرق آسیا تهیه کرده است. ماشه فرضی: در نوامبر ۲۰۲۶ دولت آمریکا اعلام می‌کند که H200 و تراشه‌های میان‌رده هوش مصنوعی بالاتر از یک آستانه پایین‌تر دوباره زیر «فرض رد» می‌روند و ارائه پردازش پیشرفته از طریق ابر به شرکت‌های چینی در هر کشوری، از ۶۰ روز بعد، ممنوع می‌شود. چه می‌شود؟

Each stage lasts: یک فصل (سه ماه)

Actors:
- us_government: دولت آمریکا (کاخ سفید و وزارت بازرگانی)
- china_government: دولت چین
- nvidia: Nvidia
- tsmc: TSMC

Variables to track (0 to 100):
- us_compute_lead: برتری آمریکا بر چین در توان پردازشی برای آموزش مدل‌های پیشرفته؛ ۰ یعنی برابری یا برتری چین، ۱۰۰ یعنی برتری کامل و پایدار آمریکا (start: 72)
- china_chip_self_reliance: میزان توانایی چین در تأمین تراشه‌های هوش مصنوعی و حافظه HBM از تولید داخلی؛ ۰ یعنی وابستگی کامل به خارج، ۱۰۰ یعنی خودکفایی کامل (start: 30)
- nvidia_china_access: دسترسی واقعی Nvidia به بازار چین (مستقیم و از راه ابر)؛ ۰ یعنی هیچ فروش و درآمدی، ۱۰۰ یعنی دسترسی کامل مانند پیش از ۲۰۲۲ (start: 12)
- trade_truce_stability: پایداری آتش‌بس تجاری آمریکا و چین؛ ۰ یعنی فروپاشی کامل و تعرفه و تحریم متقابل، ۱۰۰ یعنی توافق تمدیدشده و قابل اتکا (start: 50)
- critical_minerals_flow: جریان عناصر خاکی نادر، گالیم و ژرمانیم از چین به آمریکا و متحدانش؛ ۰ یعنی قطع کامل، ۱۰۰ یعنی صادرات عادی بدون مانع مجوز (start: 55)
- control_enforcement: اثربخشی اجرای کنترل‌ها در برابر قاچاق، شرکت‌های واسطه و اجاره ابری؛ ۰ یعنی نشت گسترده، ۱۰۰ یعنی بسته شدن تقریباً کامل راه‌های دور زدن (start: 40)
- tsmc_business_stability: ثبات کسب‌وکار TSMC از نظر مقررات، تعرفه و مشتریان؛ ۰ یعنی بحران جدی (جریمه، تعرفه، از دست دادن مشتری)، ۱۰۰ یعنی رشد بی‌دغدغه (start: 72)
- allied_alignment: میزان همراهی متحدان (هلند، ژاپن، کره، تایوان، سنگاپور، مالزی) با کنترل‌های آمریکا؛ ۰ یعنی هر کشور راه خود را می‌رود، ۱۰۰ یعنی هماهنگی کامل (start: 55)

Outside events, already fixed by a draw (use exactly these, add no others):
- stage 1: chinese_model_breakthrough: یک آزمایشگاه چینی مدلی هم‌سطح بهترین مدل‌های آمریکایی منتشر می‌کند که اعلام شده با تراشه‌های داخلی آموزش دیده است. (هم استدلال بی‌اثری کنترل‌ها و هم استدلال لزوم سخت‌گیری بیشتر را تقویت می‌کند و بازار سهام تراشه را تکان می‌دهد.)
- stage 2: smuggling_bust_southeast_asia: دادستان‌های آمریکا یا سنگاپور یک شبکه بزرگ قاچاق تراشه‌های Nvidia به چین را افشا می‌کنند. (فشار برای سخت‌گیری بیشتر بر واسطه‌ها و کشورهای ثالث را بالا می‌برد و شرکت‌های تراشه را زیر نگاه دقیق‌تر می‌برد.)
- stage 3: هیچ
- stage 4: smuggling_bust_southeast_asia: دادستان‌های آمریکا یا سنگاپور یک شبکه بزرگ قاچاق تراشه‌های Nvidia به چین را افشا می‌کنند. (فشار برای سخت‌گیری بیشتر بر واسطه‌ها و کشورهای ثالث را بالا می‌برد و شرکت‌های تراشه را زیر نگاه دقیق‌تر می‌برد.)
- stage 5: smuggling_bust_southeast_asia: دادستان‌های آمریکا یا سنگاپور یک شبکه بزرگ قاچاق تراشه‌های Nvidia به چین را افشا می‌کنند. (فشار برای سخت‌گیری بیشتر بر واسطه‌ها و کشورهای ثالث را بالا می‌برد و شرکت‌های تراشه را زیر نگاه دقیق‌تر می‌برد.)

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

Actor names: us_government, china_government, nvidia, tsmc
Variable names: us_compute_lead, china_chip_self_reliance, nvidia_china_access, trade_truce_stability, critical_minerals_flow, control_enforcement, tsmc_business_stability, allied_alignment
