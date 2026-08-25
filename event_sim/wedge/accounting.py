"""
From engine trajectories to money — by definition, not by dynamics.

Shared by every wedge. The engine hands back daily index series; this module applies
accounting identities to them:

    units(t)         = baseline_daily_units      × demand_index(t) / 100
    price(t)         = baseline_average_ticket   × price_index(t)  / 100
    revenue(t)       = units(t) × price(t)
    unit_cost(t)     = units(t) × baseline_unit_cost × cost_index(t) / 100
    gross_profit(t)  = revenue(t) − unit_cost(t)
    cash(t)          = cash(t−1) + gross_profit(t) − daily_fixed_costs

None of these is a causal claim. Gross profit is revenue minus cost by definition; cash is
yesterday's cash plus today's net by definition. Putting them inside the engine as variables
that "relax toward a pressure" would be wrong in kind, not merely in degree — which is why
they are here and not in a module.

Cash may go negative. That is the insolvency signal an owner cares about, and it is the reason
the engine's capacity-bounded queue stock (floored at zero) cannot stand in for it.

CAPACITY is the one addition the salon wedge needs, and it belongs here for the same reason:

    served(t) = min(demanded(t), capacity_per_day)

A business with a fixed number of appointment slots cannot serve more than it has, no matter
what demand does. That is an identity about slots, not a behaviour to be simulated — and
because it is applied after the engine, the demand trajectory itself stays interpretable as
"what customers wanted". Wedges without a binding capacity pass None and this code path is
never entered, which is what keeps the cafe's arithmetic untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

DAYS_PER_MONTH = 365.0 / 12.0


class BaselineLike(Protocol):
    """What the ledger needs from a wedge's baseline, whatever else it carries."""

    monthly_revenue: float
    cash_on_hand: float

    @property
    def daily_units(self) -> float: ...
    @property
    def average_ticket(self) -> float: ...
    @property
    def unit_cost(self) -> float: ...
    @property
    def daily_fixed_costs(self) -> float: ...


@dataclass
class Ledger:
    """Daily business quantities for one world. Index 0 is the day before anything changes."""

    days: list[int] = field(default_factory=list)
    orders: list[float] = field(default_factory=list)
    price: list[float] = field(default_factory=list)
    revenue: list[float] = field(default_factory=list)
    cogs: list[float] = field(default_factory=list)
    gross_profit: list[float] = field(default_factory=list)
    gross_margin_pct: list[float] = field(default_factory=list)
    net: list[float] = field(default_factory=list)
    cash: list[float] = field(default_factory=list)
    #: Only populated when a capacity limit is in force.
    demanded: list[float] = field(default_factory=list)
    turned_away: list[float] = field(default_factory=list)
    utilisation_pct: list[float] = field(default_factory=list)

    @property
    def capacity_limited(self) -> bool:
        return bool(self.demanded)

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
    baseline: BaselineLike,
    *,
    demand_index: Sequence[float],
    price_index: Sequence[float],
    cogs_index: Sequence[float],
    capacity_per_day: float | None = None,
) -> Ledger:
    n = min(len(demand_index), len(price_index), len(cogs_index))
    led = Ledger()
    cash = baseline.cash_on_hand
    fixed = baseline.daily_fixed_costs

    for day in range(n):
        demanded = baseline.daily_units * float(demand_index[day]) / 100.0
        if capacity_per_day is None:
            orders = demanded
        else:
            # You cannot serve more appointments than you have slots.
            orders = min(demanded, capacity_per_day)
            led.demanded.append(demanded)
            led.turned_away.append(max(0.0, demanded - orders))
            led.utilisation_pct.append(100.0 * orders / capacity_per_day if capacity_per_day > 0 else 0.0)

        price = baseline.average_ticket * float(price_index[day]) / 100.0
        revenue = orders * price
        cogs = orders * baseline.unit_cost * float(cogs_index[day]) / 100.0
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


def decision_metrics(led: Ledger, baseline: BaselineLike, *, horizon: int = 90) -> dict[str, Any]:
    """The quantities an owner would actually use to choose."""
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

    metrics: dict[str, Any] = {
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

    # Capacity figures exist only where a capacity limit was applied, so a wedge without one
    # produces exactly the metric set it did before this module was shared.
    if led.capacity_limited:
        capacity = led.orders[last] / (led.utilisation_pct[last] / 100.0) if led.utilisation_pct[last] > 0 else 0.0
        metrics.update({
            "utilisation_pct_end": led.utilisation_pct[last],
            "utilisation_pct_start": led.utilisation_pct[0],
            "turned_away_per_day_end": led.turned_away[last],
            "turned_away_per_day_start": led.turned_away[0],
            "demanded_change_pct": 100.0 * (led.demanded[last] / led.demanded[0] - 1.0),
            "revenue_per_slot_end": (led.revenue[last] / capacity) if capacity > 0 else 0.0,
            "gross_profit_per_slot_end": (led.gross_profit[last] / capacity) if capacity > 0 else 0.0,
            "monthly_turned_away": led.window_sum("turned_away", tail_start, last) * scale,
        })
    return metrics
