Situation: یک شرکت بزرگ هوش مصنوعی قوی‌ترین مدل کدنویسی خود را برای همه رایگان می‌کند و پرسش این است که شرکت‌های برون‌سپاری نرم‌افزار (فروشندگان ساعت برنامه‌نویس به مشتریان خارجی) چه می‌شوند. آزمایشگاه هوش مصنوعی، شرکت‌های برون‌سپاری، مشتریان خارجی، برنامه‌نویس‌ها و محیط بیرونی هر کدام واکنش نشان می‌دهند. هر مرحله یک ماه است.
Each stage lasts: یک ماه. There are 5 stages.

Seats:
- environment (محیط و رویدادهای بیرونی). Goals: {"external_shocks": 0.5, "background_drift": 0.5}. Character: آنچه از کنترل چهار بازیگر بیرون است: حرکت رقیب‌های هوش مصنوعی، شکست دیدنی کد تولیدشده با هوش مصنوعی و وضعیت اقتصاد عمومی؛ ممکن است رخ بدهد یا ندهد.
- frontier_lab (آزمایشگاه پیشروی هوش مصنوعی). Goals: {"market_share": 0.6, "sustainable_costs": 0.4}. Character: مدل را برای تصاحب بازار و عادت‌دادن توسعه‌دهنده‌ها رایگان کرده؛ هزینهٔ محاسبه بالاست و می‌تواند سقف مصرف را محدود کند.
- outsourcers (شرکت‌های برون‌سپاری نرم‌افزار). Goals: {"keep_revenue": 0.6, "keep_margin": 0.4}. Character: درآمدشان از فروش ساعت برنامه‌نویس به مشتریان خارجی است؛ حاشیهٔ سود کم و وابستگی به چند مشتری بزرگ دارند.
- foreign_clients (مشتریان خارجی). Goals: {"lower_dev_cost": 0.6, "delivery_quality": 0.4}. Character: شرکت‌ها و استارتاپ‌های کشورهای ثروتمند که کار برنامه‌نویسی می‌خرند؛ با ابزار رایگان گزینهٔ انجام کار در داخل را جدی می‌گیرند ولی از خطای کد و ریسک امنیتی می‌ترسند.
- developers (برنامه‌نویس‌های شاغل در برون‌سپاری). Goals: {"stable_income": 0.6, "skill_value": 0.4}. Character: بیشترشان جونیور و میان‌رده‌اند؛ می‌توانند مهارت خود را به بازبینی و طراحی ببرند، مستقیم برای مشتری کار کنند یا شغل را رها کنند.

Variables (0 to 100), meaning, value before the event:
- free_ai_access: دسترسی رایگان به قوی‌ترین مدل کدنویسی؛ مقدار بالا یعنی همه رایگان و بدون محدودیت دسترسی دارند = 25
- ai_code_trust: اعتماد مشتریان به کد تولیدشده با هوش مصنوعی؛ مقدار بالا یعنی اعتماد زیاد = 45
- inhouse_ai_adoption: سهم کارهای نرم‌افزاری که مشتریان خارجی خودشان با هوش مصنوعی انجام می‌دهند؛ مقدار بالا یعنی انجام بیشتر کار در داخل = 30
- client_hours: حجم ساعت‌های برون‌سپاری‌شدهٔ سفارش‌داده‌شده؛ مقدار بالا یعنی سفارش زیاد = 70
- hourly_rates: نرخ ساعتی که برون‌سپارها می‌گیرند؛ مقدار بالا یعنی نرخ بالا = 60
- firm_margin: حاشیهٔ سود و سلامت مالی شرکت‌های برون‌سپاری؛ مقدار بالا یعنی سودآوری خوب = 55
- dev_employment: اشتغال برنامه‌نویس‌ها در این شرکت‌ها؛ مقدار بالا یعنی اشتغال کامل = 70

Actions, the seat each belongs to, and what each does to the variables in one stage:
- make_coding_model_free [frontier_lab]: {"free_ai_access": 40, "inhouse_ai_adoption": 6, "ai_code_trust": 3}
- limit_free_usage [frontier_lab]: {"free_ai_access": -20, "inhouse_ai_adoption": -4, "ai_code_trust": -2}
- launch_agentic_coding_tool [frontier_lab]: {"ai_code_trust": 6, "inhouse_ai_adoption": 8, "free_ai_access": 3}
- offer_enterprise_deal [frontier_lab]: {"inhouse_ai_adoption": 5, "ai_code_trust": 3, "client_hours": -2}
- adopt_ai_in_delivery [outsourcers]: {"firm_margin": 6, "hourly_rates": -4, "dev_employment": -3, "ai_code_trust": 2}
- cut_hourly_rates [outsourcers]: {"client_hours": 5, "hourly_rates": -12, "firm_margin": -7}
- pivot_to_ai_review_services [outsourcers]: {"firm_margin": -3, "ai_code_trust": 4, "client_hours": 3, "hourly_rates": 2}
- lay_off_junior_staff [outsourcers]: {"firm_margin": 6, "dev_employment": -12, "client_hours": -2}
- shift_work_to_inhouse_ai [foreign_clients]: {"inhouse_ai_adoption": 10, "client_hours": -6, "ai_code_trust": 1}
- cut_outsourcing_contracts [foreign_clients]: {"client_hours": -12, "firm_margin": -5, "inhouse_ai_adoption": 3}
- renegotiate_rates_down [foreign_clients]: {"hourly_rates": -10, "firm_margin": -4, "client_hours": 2}
- keep_complex_work_outsourced [foreign_clients]: {"client_hours": 5, "hourly_rates": 2, "inhouse_ai_adoption": -3}
- upskill_as_ai_reviewers [developers]: {"ai_code_trust": 3, "firm_margin": 2, "dev_employment": 2, "client_hours": -1}
- freelance_directly_with_ai [developers]: {"dev_employment": -5, "client_hours": -3, "inhouse_ai_adoption": 2}
- leave_the_field_or_emigrate [developers]: {"dev_employment": -8, "firm_margin": -2, "hourly_rates": 2}
- rival_lab_matches_free [environment]: {"free_ai_access": 6, "inhouse_ai_adoption": 4, "ai_code_trust": 2}
- visible_ai_code_failure [environment]: {"ai_code_trust": -14, "inhouse_ai_adoption": -5, "client_hours": 3}
- client_economy_downturn [environment]: {"client_hours": -10, "hourly_rates": -5, "firm_margin": -4}
- rival_tool_price_hike [environment]: {"free_ai_access": -8, "inhouse_ai_adoption": -3, "firm_margin": -1}
- hold_position [any]: {}
