Answer the question below by playing the situation forward 5 stages, as realistically as you can.

فرض کن در نوامبر ۲۰۲۶ کمیسیون اروپا پیشنهاد می‌کند یک تحقیق ضدسوبسید بر خودروهای هیبریدی پلاگین ساخت چین با هدف عوارض موقت ظرف چهار ماه باز شود و عوارض جبرانی خودروهای تمام‌برقی BYD از ۱۷ به ۲۷ درصد برسد. چه می‌شود؟

Each stage lasts: یک فصل (سه ماه)

Actors:
- european_commission: کمیسیون اروپا
- china_government: دولت چین (وزارت بازرگانی)
- byd: BYD
- volkswagen_group: گروه Volkswagen

Variables to track (0 to 100):
- chinese_phev_import_flow: حجم واردات هیبرید پلاگین ساخت چین به اتحادیه اروپا؛ ۰ یعنی تقریباً متوقف، ۱۰۰ یعنی رشد بی‌مانع با سرعت سال ۲۰۲۶ (start: 72)
- eu_china_trade_tension: شدت تنش تجاری اتحادیه اروپا و چین؛ ۰ یعنی روابط آرام و مذاکره‌محور، ۱۰۰ یعنی جنگ تجاری تمام‌عیار با تلافی در چند بخش (start: 58)
- byd_eu_market_position: جایگاه BYD در بازار اروپا (فروش، حاشیه سود، شبکه فروش)؛ ۰ یعنی عقب‌نشینی از اروپا، ۱۰۰ یعنی رهبری بازار خودروی برقی‌شده اروپا (start: 50)
- vw_china_business_health: سلامت کسب‌وکار Volkswagen Group در چین (فروش، سود مشارکت‌ها، دسترسی به قطعات)؛ ۰ یعنی فروپاشی، ۱۰۰ یعنی رونق دوره پیش از ۲۰۲۰ (start: 38)
- eu_auto_jobs_security: امنیت تولید و اشتغال صنعت خودروی اتحادیه اروپا؛ ۰ یعنی بسته‌شدن گسترده کارخانه‌ها، ۱۰۰ یعنی ظرفیت پر و اشتغال باثبات (start: 42)
- eu_ev_affordability: در دسترس بودن خودروی برقی و هیبرید پلاگین ارزان برای مصرف‌کننده اروپایی؛ ۰ یعنی بسیار گران و کم‌گزینه، ۱۰۰ یعنی ارزان و پرگزینه (start: 52)
- eu_member_state_unity: یکپارچگی کشورهای عضو پشت سیاست تجاری کمیسیون در قبال خودروی چینی؛ ۰ یعنی شکاف علنی و رأی مخالف، ۱۰۰ یعنی حمایت یکپارچه (start: 44)
- chinese_production_in_eu: میزان تولید محلی خودروسازان چینی در خاک اتحادیه اروپا؛ ۰ یعنی هیچ تولیدی، ۱۰۰ یعنی تولید انبوه و زنجیره تأمین محلی (start: 22)

Outside events, already fixed by a draw (use exactly these, add no others):
- stage 1: auto_chip_supply_disruption: اختلالی شبیه بحران Nexperia در عرضه تراشه‌های خودرو رخ می‌دهد و خطوط تولید اروپایی کند می‌شوند. (وابستگی متقابل زنجیره تأمین را برجسته می‌کند و تولید و اشتغال خودروی اروپا را موقتاً پایین می‌آورد.)
- stage 2: us_tariff_shift_on_eu_cars: ایالات متحده تعرفه خودروهای اروپایی را تغییر می‌دهد یا تهدید تازه‌ای علیه آن‌ها مطرح می‌کند. (اهمیت بازار چین برای خودروسازان اروپایی و اشتهای اتحادیه برای درگیری در دو جبهه را جابه‌جا می‌کند.)
- stage 3: member_state_coalition_revolt: چند کشور عضو در بیانیه‌ای مشترک خواستار توقف اقدامات تازه علیه خودروی چینی می‌شوند. (یکپارچگی پشت کمیسیون را کاهش می‌دهد و احتمال رسیدن پیشنهادها به رأی را کم می‌کند.)
- stage 4: هیچ
- stage 5: هیچ

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

Actor names: european_commission, china_government, byd, volkswagen_group
Variable names: chinese_phev_import_flow, eu_china_trade_tension, byd_eu_market_position, vw_china_business_health, eu_auto_jobs_security, eu_ev_affordability, eu_member_state_unity, chinese_production_in_eu
