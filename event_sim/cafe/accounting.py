"""
From engine trajectories to money — by definition, not by dynamics.

The engine hands back four daily index series: input cost, ingredient cost per order, menu
price, and orders. This module applies accounting identities to them:

    orders(t)        = baseline_daily_orders     × demand_index(t) / 100
    price(t)         = baseline_average_order    × price_index(t)  / 100
    revenue(t)       = orders(t) × price(t)
    cogs(t)          = orders(t) × baseline_cogs_per_order × cogs_index(t) / 100
    gross_profit(t)  = revenue(t) − cogs(t)
    cash(t)          = cash(t−1) + gross_profit(t) − daily_fixed_costs

None of these is a causal claim. Gross profit is revenue minus cost by definition; cash is
yesterday's cash plus today's net by definition. Putting them inside the engine as variables
that "relax toward a pressure" would be wrong in kind, not merely in degree — which is why
they are here and not in the module.

Cash may go negative. That is the insolvency signal a cafe owner cares about, and it is the
reason the engine's capacity-bounded queue stock (floored at zero) cannot stand in for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from event_sim.cafe.baseline import DAYS_PER_MONTH, CafeBaseline


@dataclass
class Ledger:
    """Daily business quantities for one world. Index 0 is the day before the shock."""

    days: list[int] = field(default_factory=list)
    orders: list[float] = field(default_factory=list)
    price: list[float] = field(default_factory=list)
    revenue: list[float] = field(default_factory=list)
    cogs: list[float] = field(default_factory=list)
    gross_profit: list[float] = field(default_factory=list)
    gross_margin_pct: list[float] = field(default_factory=list)
    net: list[float] = field(default_factory=list)
    cash: list[float] = field(default_factory=list)

    def at(self, day: int) -> dict[str, float]:
        i = min(day, len(self.days) - 1)
        return {
            "day": self.days[i],
            "orders": self.orders[i],
            "price": self.price[i],
            "revenue": self.revenue[i],
            "cogs": self.cogs[i],
            "gross_profit": self.gross_profit[i],
            "gross_margin_pct": self.gross_margin_pct[i],
            "net": self.net[i],
            "cash": self.cash[i],
        }

    def window_sum(self, key: str, start_day: int, end_day: int) -> float:
        series = getattr(self, key)
        return float(sum(series[start_day : end_day + 1]))


def build_ledger(
    baseline: CafeBaseline,
    *,
    demand_index: Sequence[float],
    price_index: Sequence[float],
    cogs_index: Sequence[float],
) -> Ledger:
    n = min(len(demand_index), len(price_index), len(cogs_index))
    led = Ledger()
    cash = baseline.cash_on_hand
    fixed = baseline.daily_fixed_costs

    for day in range(n):
        orders = baseline.daily_orders * float(demand_index[day]) / 100.0
        price = baseline.average_order_value * float(price_index[day]) / 100.0
        revenue = orders * price
        cogs = orders * baseline.cogs_per_order * float(cogs_index[day]) / 100.0
        gp = revenue - cogs
        net = gp - fixed
        if day > 0:
            cash += net
        led.days.append(day)
        led.orders.append(orders)
        led.price.append(price)
        led.revenue.append(revenue)
        led.cogs.append(cogs)
        led.gross_profit.append(gp)
        led.gross_margin_pct.append(100.0 * gp / revenue if revenue > 0 else 0.0)
        led.net.append(net)
        led.cash.append(cash)
    return led


def runway_months(cash: float, monthly_net: float) -> float | None:
    """Months until cash is exhausted at a constant monthly net. None = not at risk."""
    if monthly_net >= 0:
        return None
    if cash <= 0:
        return 0.0
    return cash / (-monthly_net)


def decision_metrics(led: Ledger, baseline: CafeBaseline, *, horizon: int = 90) -> dict[str, Any]:
    """The quantities a cafe owner would actually use to choose."""
    last = min(horizon, len(led.days) - 1)
    # Steady-state monthly figures from the final 30 days, scaled to a calendar month.
    tail_start = max(1, last - 29)
    tail_days = last - tail_start + 1
    scale = DAYS_PER_MONTH / tail_days
    monthly_revenue = led.window_sum("revenue", tail_start, last) * scale
    monthly_gp = led.window_sum("gross_profit", tail_start, last) * scale
    monthly_net = led.window_sum("net", tail_start, last) * scale
    monthly_orders = led.window_sum("orders", tail_start, last) * scale

    worst_margin_day = min(range(1, last + 1), key=lambda d: led.gross_margin_pct[d])
    min_cash_day = min(range(0, last + 1), key=lambda d: led.cash[d])

    return {
        "monthly_revenue": monthly_revenue,
        "monthly_gross_profit": monthly_gp,
        "monthly_net": monthly_net,
        "monthly_orders": monthly_orders,
        "gross_margin_pct_end": led.gross_margin_pct[last],
        "worst_gross_margin_pct": led.gross_margin_pct[worst_margin_day],
        "worst_gross_margin_day": worst_margin_day,
        "orders_change_pct": 100.0 * (led.orders[last] / led.orders[0] - 1.0),
        "revenue_change_pct": 100.0 * (monthly_revenue / baseline.monthly_revenue - 1.0),
        "cash_day_30": led.cash[min(30, last)],
        "cash_day_90": led.cash[last],
        "cash_change_90": led.cash[last] - led.cash[0],
        "min_cash": led.cash[min_cash_day],
        "min_cash_day": min_cash_day,
        "cash_goes_negative": any(c < 0 for c in led.cash[: last + 1]),
        "first_negative_day": next((d for d in range(0, last + 1) if led.cash[d] < 0), None),
        "runway_months_at_end": runway_months(led.cash[last], monthly_net),
        "cumulative_gross_profit_90": led.window_sum("gross_profit", 1, last),
        "cumulative_net_90": led.window_sum("net", 1, last),
    }
