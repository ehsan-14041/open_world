Answer the question below by playing the situation forward 5 stages, as realistically as you can.

Situation and question: از اواخر فوریه ۲۰۲۶ جنگ آمریکا و اسرائیل با ایران و بسته شدن تنگه هرمز بزرگ‌ترین بحران انرژی چند دهه اخیر را ساخت. امارات از اول مه ۲۰۲۶ از اوپک و اوپک‌پلاس خارج شد و هدف ظرفیت ۵ میلیون بشکه در روز تا ۲۰۲۷ را اعلام کرد. توافق موقت آمریکا و ایران در ژوئن تنگه را باز کرد، اما تولید هفت عضو اصلی اوپک‌پلاس در اوت هنوز حدود ۵ میلیون بشکه در روز زیر سطح پیش از جنگ بود. این هفت کشور سقف مجموع ۳۱.۰۱ میلیون بشکه در روز را برای اکتبر تا دسامبر ثابت نگه داشتند. برنت که بالای ۱۰۰ دلار بود، در هفته اول نوامبر حدود ۱۶ درصد افت کرد و به ۹۵ تا ۹۸ دلار رسید؛ تولید عربستان در اکتبر حدود ۹.۲ میلیون بشکه بود. نشست وزیران در ۲۹ نوامبر باید چارچوب تولید ۲۰۲۷ را تعیین کند. فرض این تمرین: آمریکا و ایران در نیمه نوامبر توافق جامع امضا می‌کنند، معافیت تحریم نفت ایران تمدید می‌شود، صادرات خلیج فارس تقریباً به سطح پیش از جنگ برمی‌گردد و برنت در دو هفته به حدود ۶۸ دلار سقوط می‌کند. پیش‌بینی‌ها مازاد ۲ تا ۳ میلیون بشکه در روز برای ۲۰۲۷ نشان می‌دهند و اوپک‌پلاس باید تصمیم بگیرد دوباره تولید را کم کند یا برای سهم بازار بجنگد. چه می‌شود؟

Each stage lasts: یک ماه

Actors:
- saudi_arabia: دولت عربستان سعودی (وزارت انرژی و آرامکو)
- russia: دولت روسیه (معاون نخست‌وزیر Alexander Novak و وزارت انرژی)
- uae: دولت امارات متحده عربی (وزارت انرژی و ADNOC)
- us_government: دولت آمریکا (کاخ سفید، وزارت انرژی و وزارت خزانه‌داری)

Variables to track (0 to 100):
- brent_price_level: سطح قیمت نفت برنت؛ ۰ یعنی ۵۰ دلار یا کمتر، ۱۰۰ یعنی ۱۱۰ دلار یا بیشتر (start: 30)
- opec_plus_cohesion: انسجام و پایبندی اعضای اوپک‌پلاس به سهمیه‌ها؛ ۰ یعنی فروپاشی و جنگ قیمت، ۱۰۰ یعنی اجرای کامل و هماهنگ (start: 55)
- saudi_fiscal_space: فضای مالی عربستان؛ ۰ یعنی کسری شدید و توقف پروژه‌های چشم‌انداز ۲۰۳۰، ۱۰۰ یعنی بودجه متوازن و دست باز (start: 40)
- russia_oil_revenue: درآمد صادرات نفت روسیه؛ ۰ یعنی فروپاشی درآمد و برداشت سنگین از صندوق ثروت ملی، ۱۰۰ یعنی رکورد درآمد (start: 55)
- uae_market_share: سهم امارات از بازار جهانی و فروش ظرفیت تازه‌اش؛ ۰ یعنی ظرفیت بلااستفاده و مشتری از دست رفته، ۱۰۰ یعنی فروش کامل ظرفیت با قراردادهای بلندمدت (start: 55)
- us_gasoline_affordability: ارزانی بنزین برای مصرف‌کننده آمریکایی؛ ۰ یعنی بنزین بسیار گران، ۱۰۰ یعنی بنزین بسیار ارزان (start: 55)
- us_shale_activity: سطح فعالیت حفاری و سرمایه‌گذاری شیل آمریکا؛ ۰ یعنی موج تعطیلی و ورشکستگی، ۱۰۰ یعنی رونق حفاری (start: 60)
- riyadh_washington_alignment: هماهنگی سیاسی ریاض و واشنگتن؛ ۰ یعنی شکاف علنی و تنبیه متقابل، ۱۰۰ یعنی همکاری نزدیک و بسته امنیتی فعال (start: 60)

Outside events, already fixed by a draw (use exactly these, add no others):
- stage 1: هیچ
- stage 2: weak_china_demand: داده‌های واردات نفت و فعالیت صنعتی چین ضعیف‌تر از انتظار منتشر می‌شود. (انتظار مازاد عرضه را تقویت می‌کند و قیمت و رقابت بر سر مشتریان آسیایی را فشرده‌تر می‌کند.)
- stage 3: هیچ
- stage 4: هیچ
- stage 5: harsh_northern_winter: زمستانی سردتر از معمول در اروپا، آمریکای شمالی و شمال آسیا تقاضای سوخت را بالا می‌برد. (تقاضای کوتاه‌مدت برای فرآورده‌ها و نفت خام را افزایش می‌دهد و فشار مازاد را موقتاً کم می‌کند.)

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

Actor names: saudi_arabia, russia, uae, us_government
Variable names: brent_price_level, opec_plus_cohesion, saudi_fiscal_space, russia_oil_revenue, uae_market_share, us_gasoline_affordability, us_shale_activity, riyadh_washington_alignment
