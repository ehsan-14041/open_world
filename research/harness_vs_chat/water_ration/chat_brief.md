Situation: پس از یک خشکسالی شدید، شهری چندمیلیون‌نفره جیره‌بندی آب لوله‌کشی را آغاز می‌کند و آب بخشی از هر روز قطع می‌شود. شرکت آب، شهرداری و دولت شهری، خانوارها و تانکرکش‌های خصوصی هر کدام واکنش نشان می‌دهند و باران، موج گرما یا ترکیدگی خطوط نیز اثر می‌گذارد. هر مرحله دو هفته است.
Each stage lasts: دو هفته. There are 5 stages.

Seats:
- environment (محیط و رویدادهای بیرونی). Goals: {"external_events": 0.5, "random_shocks": 0.5}. Character: نمایندهٔ رویدادهایی که از کنترل چهار بازیگر بیرون است: باران یا نبود آن، موج گرما، ترکیدگی لوله و پخش شایعه؛ هر رویداد ممکن است رخ دهد یا ندهد.
- water_utility (شرکت آب و فاضلاب شهری). Goals: {"protect_reservoir": 0.6, "keep_service_running": 0.4}. Character: تصمیم جیره‌بندی، سختگیری و تخفیف آن با اوست؛ نگران ته‌نشینی مخازن است و با شبکهٔ فرسوده و بودجهٔ محدود کار می‌کند.
- city_government (شهرداری و دولت شهری). Goals: {"public_order": 0.5, "protect_vulnerable": 0.5}. Character: اختیار تعرفه، جریمه، تانکر امدادی و پیام‌رسانی عمومی را دارد؛ هم از خشم مردم می‌ترسد و هم از اتمام آب.
- households (خانوارهای شهری). Goals: {"reliable_water": 0.7, "low_cost": 0.3}. Character: برای آب شرب و بهداشت به لوله و مخزن خانگی وابسته‌اند؛ بخشی ذخیره می‌کنند، بخشی از تانکر می‌خرند و بخشی اعتراض می‌کنند.
- tanker_vendors (تانکرکش‌ها و فروشندگان خصوصی آب). Goals: {"profit": 0.7, "keep_customers": 0.3}. Character: از کمبود آب لوله سود می‌برند؛ قیمت و ناوگان را با تقاضا تنظیم می‌کنند و گاهی از منابع کم‌کیفیت برداشت می‌کنند.

Variables (0 to 100), meaning, value before the event:
- reservoir: سطح ذخیرهٔ سدها و منابع آب شهر؛ مقدار بالا یعنی ذخیرهٔ بیشتر = 25
- supply_hours: ساعت‌های برقراری آب لوله در روز؛ مقدار بالا یعنی آب بیشتر و بدون قطع = 95
- home_storage: ذخیرهٔ آب در مخزن و ظرف خانوارها؛ مقدار بالا یعنی ذخیرهٔ بیشتر = 40
- tanker_price: قیمت آب تانکری در بازار آزاد؛ مقدار بالا یعنی گران‌تر = 25
- public_anger: نارضایتی و اعتراض مردم؛ مقدار بالا یعنی خشم بیشتر = 25
- health_risk: خطر بهداشتی و بیماری ناشی از آب؛ مقدار بالا یعنی خطر بیشتر = 15
- utility_budget: توان مالی شرکت آب؛ مقدار بالا یعنی بودجه و درآمد بیشتر = 55

Actions, the seat each belongs to, and what each does to the variables in one stage:
- rain_arrives [environment]: {"reservoir": 8, "public_anger": -3}
- heat_wave [environment]: {"reservoir": -6, "health_risk": 5, "public_anger": 3}
- main_pipe_burst [environment]: {"supply_hours": -10, "health_risk": 5, "utility_budget": -4, "reservoir": -3}
- rationing_rumor_spreads [environment]: {"tanker_price": 6, "public_anger": 6, "home_storage": 3}
- start_rationing [water_utility]: {"supply_hours": -35, "reservoir": 5, "public_anger": 12, "utility_budget": -5, "tanker_price": 6}
- tighten_rationing [water_utility]: {"supply_hours": -12, "reservoir": 4, "public_anger": 8, "utility_budget": -3}
- ease_rationing [water_utility]: {"supply_hours": 12, "reservoir": -4, "public_anger": -6, "utility_budget": 3}
- fix_leaks_and_pressure [water_utility]: {"reservoir": 3, "supply_hours": 3, "utility_budget": -6}
- deploy_free_tankers [city_government]: {"home_storage": 6, "tanker_price": -5, "public_anger": -5, "health_risk": -2, "utility_budget": -5}
- raise_water_tariff [city_government]: {"utility_budget": 8, "reservoir": 2, "public_anger": 8}
- launch_conservation_campaign [city_government]: {"reservoir": 3, "public_anger": -2, "utility_budget": -2}
- fine_excess_users [city_government]: {"reservoir": 3, "public_anger": 7, "utility_budget": 3}
- hoard_water_in_tanks [households]: {"home_storage": 12, "reservoir": -3, "tanker_price": 3, "health_risk": 3}
- buy_from_tankers [households]: {"home_storage": 8, "tanker_price": 6, "public_anger": -2, "health_risk": 1}
- cut_use_voluntarily [households]: {"reservoir": 3, "home_storage": -3, "public_anger": 2}
- protest_and_complain [households]: {"public_anger": 5, "supply_hours": 2, "utility_budget": -2}
- raise_tanker_prices [tanker_vendors]: {"tanker_price": 12, "public_anger": 5, "home_storage": -3}
- expand_tanker_fleet [tanker_vendors]: {"tanker_price": -8, "home_storage": 4, "reservoir": -2, "health_risk": 2}
- sell_unsafe_well_water [tanker_vendors]: {"tanker_price": -6, "home_storage": 5, "health_risk": 12, "reservoir": -2}
- hold_position [any]: {}
