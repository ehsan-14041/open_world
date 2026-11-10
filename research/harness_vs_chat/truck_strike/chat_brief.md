Situation: رانندگان کامیون در سراسر کشور در اعتراض به قیمت سوخت و نرخ کرایهٔ حمل اعتصاب سراسری را آغاز می‌کنند. اتحادیهٔ رانندگان، دولت، صاحبان بار و خرده‌فروشی‌ها هر کدام واکنش نشان می‌دهند و رویدادهای بیرونی هم مسیر را عوض می‌کنند. هر مرحله سه روز است.
Each stage lasts: سه روز. There are 5 stages.

Seats:
- environment (محیط و رویدادهای بیرونی). Goals: {"random_shocks": 0.5, "spillover": 0.5}. Character: حوادث خشونت‌بار جاده‌ای، خرید هراسی، آب‌وهوای بد یا پیوستن صنف‌های دیگر؛ هیچ‌کدام از چهار بازیگر کنترلشان نمی‌کنند و ممکن است رخ بدهند یا ندهند.
- drivers_union (اتحادیهٔ رانندگان کامیون). Goals: {"raise_margin": 0.6, "keep_unity": 0.4}. Character: نمایندهٔ رانندگانی که با سوخت گران و کرایهٔ ثابت حاشیهٔ سودشان تقریباً صفر شده؛ اعتصاب ابزار اصلی چانه‌زنی است ولی ماندگاری آن به همبستگی اعضا بستگی دارد.
- government (دولت). Goals: {"restore_order": 0.5, "limit_fiscal_cost": 0.5}. Character: هم قیمت سوخت و هم نرخ کرایه در دست اوست؛ از قطع زنجیرهٔ تأمین نگران است ولی بودجهٔ کافی برای یارانهٔ بزرگ ندارد و گاهی به فشار امنیتی متوسل می‌شود.
- shippers (صاحبان بار و کارخانه‌ها). Goals: {"keep_flow": 0.6, "limit_cost": 0.4}. Character: تولیدکنندگان و توزیع‌کنندگان عمده که با توقف حمل انبارشان پر و خط تولیدشان خالی می‌شود؛ حاضرند کرایه را بالا ببرند ولی نه به اندازهٔ خواستهٔ رانندگان.
- retailers (خرده‌فروشی‌ها و فروشگاه‌های زنجیره‌ای). Goals: {"keep_shelves": 0.6, "keep_margin": 0.4}. Character: به موجودی انبار و تحویل روزانه وابسته‌اند؛ با کمبود، قیمت و ذخیره‌سازی را مدیریت می‌کنند و زیر نگاه مصرف‌کننده و نهاد نظارت‌اند.

Variables (0 to 100), meaning, value before the event:
- freight_flow: میزان حمل‌ونقل جاده‌ای در جریان؛ مقدار بالا یعنی کامیون‌ها عادی کار می‌کنند = 85
- fuel_cost: فشار هزینهٔ سوخت بر رانندگان؛ مقدار بالا یعنی سوخت گران‌تر و سنگین‌تر = 65
- driver_margin: حاشیهٔ سود رانندگان پس از کسر سوخت؛ مقدار بالا یعنی درآمد بهتر = 35
- shelf_supply: موجودی کالا در قفسه‌ها و انبارهای توزیع؛ مقدار بالا یعنی عرضه کافی است = 80
- price_level: سطح قیمت کالاهای مصرفی؛ مقدار بالا یعنی گرانی بیشتر = 55
- public_order: آرامش و نظم عمومی در جاده‌ها و شهرها؛ مقدار بالا یعنی آرام‌تر = 75
- driver_unity: همبستگی و آمادگی رانندگان برای ادامهٔ اعتصاب؛ مقدار بالا یعنی متحدتر = 45

Actions, the seat each belongs to, and what each does to the variables in one stage:
- violent_road_incident [environment]: {"public_order": -12, "driver_unity": 6, "freight_flow": -5}
- panic_buying [environment]: {"shelf_supply": -15, "price_level": 8, "public_order": -4}
- severe_weather [environment]: {"freight_flow": -10, "shelf_supply": -4, "public_order": -2}
- other_union_joins [environment]: {"freight_flow": -12, "driver_unity": 10, "public_order": -4, "price_level": 3}
- start_nationwide_strike [drivers_union]: {"freight_flow": -40, "driver_unity": 10, "driver_margin": -5, "public_order": -5}
- extend_strike_to_ports [drivers_union]: {"freight_flow": -12, "shelf_supply": -5, "driver_margin": -6, "driver_unity": 5}
- blockade_highways [drivers_union]: {"freight_flow": -10, "public_order": -12, "price_level": 3, "driver_unity": 4}
- accept_deal_end_strike [drivers_union]: {"freight_flow": 30, "driver_margin": 6, "driver_unity": -12, "public_order": 5}
- cut_fuel_price [government]: {"fuel_cost": -12, "price_level": 2, "public_order": 2}
- raise_freight_tariff_floor [government]: {"driver_margin": 8, "price_level": 4, "driver_unity": -4}
- deploy_police_escorts [government]: {"freight_flow": 8, "public_order": 4, "driver_unity": 3, "driver_margin": -2}
- arrest_strike_leaders [government]: {"driver_unity": -6, "public_order": -8, "freight_flow": -3}
- raise_freight_rates [shippers]: {"driver_margin": 7, "price_level": 5, "freight_flow": 3, "driver_unity": -3}
- use_rail_and_own_fleet [shippers]: {"freight_flow": 6, "shelf_supply": 3, "driver_margin": -4, "price_level": 2}
- hire_strikebreaker_drivers [shippers]: {"freight_flow": 7, "driver_unity": 6, "public_order": -6, "driver_margin": -2}
- pause_shipments [shippers]: {"freight_flow": -6, "shelf_supply": -4, "price_level": 3, "driver_margin": -3}
- ration_stock [retailers]: {"shelf_supply": -4, "price_level": 3, "public_order": -3}
- hike_shelf_prices [retailers]: {"price_level": 8, "public_order": -4, "shelf_supply": 2}
- draw_down_inventory_buffer [retailers]: {"shelf_supply": 8, "price_level": -3, "driver_unity": 2}
- hold_position [any]: {}
