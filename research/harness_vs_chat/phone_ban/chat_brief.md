Situation: یک کشور میان‌اندازه با ارز ضعیف ناگهان واردات گوشی‌های با قیمت بالای ۶۰۰ دلار را ممنوع می‌کند. دولت، واردکنندگان، مصرف‌کنندگان و مونتاژکاران داخلی هر کدام واکنش نشان می‌دهند و محیط بیرونی (نرخ ارز، مسیرهای قاچاق، واکنش سازندگان خارجی) اثر می‌گذارد. هر مرحله یک ماه است.
Each stage lasts: یک ماه. There are 5 stages.

Seats:
- environment (محیط و رویدادهای بیرونی). Goals: {"external_shocks": 0.5, "market_drift": 0.5}. Character: نمایندهٔ آنچه از کنترل چهار بازیگر بیرون است: نوسان نرخ ارز، مسیرهای قاچاق، واکنش سازندگان خارجی و فضای عمومی؛ رویدادها ممکن است رخ بدهند یا ندهند.
- government (دولت و گمرک). Goals: {"save_fx": 0.6, "avoid_unrest": 0.4}. Character: تصمیم ممنوعیت و تعدیل یا لغو آن با اوست؛ نگران ذخیرهٔ ارزی و درآمد گمرک است و از نارضایتی عمومی هم می‌ترسد.
- importers (واردکنندگان و عمده‌فروشان گوشی). Goals: {"keep_margin": 0.6, "keep_stock_flow": 0.4}. Character: سرمایهٔ در گردششان در موجودی گوشی گره خورده است؛ برای دور زدن یا نرم کردن محدودیت راه پیدا می‌کنند.
- consumers (مصرف‌کنندگان گوشی). Goals: {"get_phone": 0.6, "low_price": 0.4}. Character: قدرت خریدشان با ارز ضعیف کم شده است؛ اگر کانال رسمی بسته شود سراغ بازار غیررسمی می‌روند یا خرید را عقب می‌اندازند.
- local_assemblers (مونتاژکاران و تولیدکنندگان داخلی). Goals: {"grow_share": 0.6, "secure_parts": 0.4}. Character: از حذف رقیب وارداتی سود می‌برند ولی به قطعات وارداتی و ارز وابسته‌اند و ظرفیتشان محدود است.

Variables (0 to 100), meaning, value before the event:
- legal_supply: عرضهٔ قانونی گوشی در بازار؛ مقدار بالا یعنی گوشی فراوان و رسمی = 80
- smuggling: سهم گوشی قاچاق و غیررسمی؛ مقدار بالا یعنی قاچاق گسترده = 20
- phone_price: سطح قیمت گوشی برای مصرف‌کننده؛ مقدار بالا یعنی گران‌تر = 55
- fx_pressure: فشار بر بازار ارز؛ مقدار بالا یعنی ارز ضعیف‌تر و فشار بیشتر = 60
- customs_revenue: درآمد گمرکی دولت؛ مقدار بالا یعنی درآمد بیشتر = 50
- local_assembly: تولید و مونتاژ گوشی در داخل؛ مقدار بالا یعنی تولید داخلی قوی‌تر = 25
- discontent: نارضایتی عمومی؛ مقدار بالا یعنی ناراضی‌تر = 35

Actions, the seat each belongs to, and what each does to the variables in one stage:
- impose_phone_import_ban [government]: {"legal_supply": -32, "phone_price": 12, "smuggling": 10, "fx_pressure": -6, "customs_revenue": -14, "local_assembly": 4, "discontent": 10}
- soften_ban_with_quota [government]: {"legal_supply": 12, "phone_price": -5, "smuggling": -5, "fx_pressure": 3, "customs_revenue": 6, "local_assembly": -2, "discontent": -5}
- lift_ban [government]: {"legal_supply": 25, "phone_price": -8, "smuggling": -8, "fx_pressure": 6, "customs_revenue": 10, "local_assembly": -4, "discontent": -8}
- crack_down_on_smuggling [government]: {"smuggling": -8, "phone_price": 4, "customs_revenue": 3, "discontent": 4}
- lobby_for_exemptions [importers]: {"legal_supply": 4, "phone_price": -2, "local_assembly": -2}
- import_just_below_threshold [importers]: {"legal_supply": 6, "phone_price": -3, "customs_revenue": 3, "fx_pressure": 2}
- stockpile_phones [importers]: {"phone_price": 3, "fx_pressure": 3, "customs_revenue": 2}
- raise_retail_prices [importers]: {"phone_price": 8, "smuggling": 3, "discontent": 5}
- buy_grey_market_phones [consumers]: {"smuggling": 8, "customs_revenue": -3, "phone_price": -2, "fx_pressure": 3, "discontent": -2}
- delay_phone_purchase [consumers]: {"phone_price": -3, "customs_revenue": -2, "discontent": 2}
- protest_online [consumers]: {"discontent": 8, "fx_pressure": 1}
- expand_local_assembly [local_assemblers]: {"local_assembly": 8, "legal_supply": 3, "phone_price": -2, "fx_pressure": 2, "customs_revenue": -2}
- assemble_from_imported_kits [local_assemblers]: {"local_assembly": 6, "legal_supply": 4, "phone_price": -2, "fx_pressure": 3}
- raise_local_prices [local_assemblers]: {"local_assembly": 2, "phone_price": 4, "discontent": 3}
- currency_depreciation_shock [environment]: {"fx_pressure": 12, "phone_price": 7, "smuggling": 3, "discontent": 5}
- smuggling_route_expands [environment]: {"smuggling": 12, "phone_price": -4, "customs_revenue": -4, "legal_supply": -2}
- foreign_maker_cuts_models_below_threshold [environment]: {"legal_supply": 8, "phone_price": -3, "customs_revenue": 3, "local_assembly": -3}
- public_mood_turns_hostile [environment]: {"discontent": 8, "fx_pressure": 3}
- hold_position [any]: {}
