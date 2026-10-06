"""
The shop's starting position — demo defaults, and the structure a real owner fills in.

Eight inputs, the same discipline as the cafe: every one is something an owner can read off
their own records in a couple of minutes. Average order value is deliberately NOT asked for —
it follows from monthly sales and orders per day, and asking for a third number that must be
consistent with the first two is how intake forms start disagreeing with themselves.

The demo values are FICTIONAL. They describe a small independent shop at a typical retail
gross margin with a few weeks of cash, chosen so that a supplier increase is a real problem
rather than a rounding error. They did not come from any real business.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace as _replace
from typing import Any

DAYS_PER_MONTH = 365.0 / 12.0


@dataclass(frozen=True)
class ShopBaseline:
    """Customer inputs. Units are plain currency and counts; no indices."""

    name: str
    monthly_revenue: float            # currency / month
    daily_orders: float               # orders / day
    monthly_cogs: float               # what the shop pays for the goods it sells
    monthly_fixed_costs: float        # rent, wages, utilities, everything fixed over 90 days
    cash_on_hand: float               # currency
    supplier_increase_pct: float      # the shock, percent
    low_margin_share_pct: float       # share of orders on lines that earn little
    is_demo: bool = True
    notes: list[str] = field(default_factory=list)

    # --- derived ---------------------------------------------------------------------------

    @property
    def average_order_value(self) -> float:
        return self.monthly_revenue / (self.daily_orders * DAYS_PER_MONTH)

    @property
    def cogs_pct(self) -> float:
        return 100.0 * self.monthly_cogs / self.monthly_revenue

    @property
    def gross_margin_pct(self) -> float:
        return 100.0 - self.cogs_pct

    @property
    def cogs_per_order(self) -> float:
        return self.monthly_cogs / (self.daily_orders * DAYS_PER_MONTH)

    @property
    def monthly_gross_profit(self) -> float:
        return self.monthly_revenue - self.monthly_cogs

    @property
    def monthly_net(self) -> float:
        return self.monthly_gross_profit - self.monthly_fixed_costs

    @property
    def net_margin_pct(self) -> float:
        return 100.0 * self.monthly_net / self.monthly_revenue

    @property
    def daily_fixed_costs(self) -> float:
        return self.monthly_fixed_costs / DAYS_PER_MONTH

    # --- names the shared accounting uses ---------------------------------------------------

    @property
    def daily_units(self) -> float:
        return self.daily_orders

    @property
    def average_ticket(self) -> float:
        return self.average_order_value

    @property
    def unit_cost(self) -> float:
        return self.cogs_per_order

    def replace(self, **changes: Any) -> "ShopBaseline":
        return _replace(self, **changes)

    # --- contract ---------------------------------------------------------------------------

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.monthly_revenue <= 0:
            problems.append("Monthly sales must be greater than zero.")
        if self.daily_orders <= 0:
            problems.append("Orders per day must be greater than zero.")
        if self.monthly_cogs <= 0:
            problems.append("Monthly cost of goods must be greater than zero.")
        if self.monthly_revenue > 0 and self.monthly_cogs >= self.monthly_revenue:
            problems.append("Cost of goods must be below monthly sales.")
        if self.monthly_fixed_costs < 0:
            problems.append("Fixed costs cannot be negative.")
        if self.cash_on_hand < 0:
            problems.append("Cash on hand cannot be negative.")
        if not 0 <= self.supplier_increase_pct <= 200:
            problems.append("The supplier increase should be between 0% and 200%.")
        if not 0 <= self.low_margin_share_pct <= 100:
            problems.append("The low-margin share should be between 0% and 100%.")
        return problems

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "is_demo": self.is_demo,
            "monthly_revenue": round(self.monthly_revenue, 2),
            "daily_orders": round(self.daily_orders, 1),
            "average_order_value": round(self.average_order_value, 2),
            "monthly_cogs": round(self.monthly_cogs, 2),
            "cogs_pct": round(self.cogs_pct, 1),
            "gross_margin_pct": round(self.gross_margin_pct, 1),
            "monthly_fixed_costs": round(self.monthly_fixed_costs, 2),
            "monthly_net": round(self.monthly_net, 2),
            "net_margin_pct": round(self.net_margin_pct, 1),
            "cash_on_hand": round(self.cash_on_hand, 2),
            "supplier_increase_pct": self.supplier_increase_pct,
            "low_margin_share_pct": self.low_margin_share_pct,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ShopBaseline":
        return cls(
            name=str(d.get("name") or "Unnamed shop"),
            monthly_revenue=float(d["monthly_revenue"]),
            daily_orders=float(d["daily_orders"]),
            monthly_cogs=float(d["monthly_cogs"]),
            monthly_fixed_costs=float(d["monthly_fixed_costs"]),
            cash_on_hand=float(d["cash_on_hand"]),
            supplier_increase_pct=float(d.get("supplier_increase_pct", 25.0)),
            low_margin_share_pct=float(d.get("low_margin_share_pct", 20.0)),
            is_demo=bool(d.get("is_demo", False)),
            notes=list(d.get("notes") or []),
        )


#: The fictional demo shop. A small independent store: ~90 orders a day at about $34, goods at
#: 58% of revenue (a normal retail gross margin, thinner than a cafe's), and about six weeks of
#: cash. A 25% supplier increase on a 58% cost base is roughly 14 points of margin — enough to
#: turn a modest profit into a loss, which is exactly when this decision gets asked.
DEMO_SHOP = ShopBaseline(
    name="Demo shop (fictional)",
    monthly_revenue=92000.0,
    daily_orders=90.0,
    monthly_cogs=53360.0,
    monthly_fixed_costs=33000.0,
    cash_on_hand=26000.0,
    supplier_increase_pct=25.0,
    low_margin_share_pct=20.0,
    is_demo=True,
    notes=[
        "Fictional. Chosen to be a realistic small retailer at a normal gross margin, not a "
        "composite of any real business.",
        "Cost of goods is 58% of sales, so a 25% supplier increase removes roughly 14 points "
        "of gross margin if nothing else changes.",
    ],
)

INTAKE_FIELDS: list[dict[str, str]] = [
    {"key": "name", "label": "Business name", "unit": "", "hint": "Only used on the report."},
    {"key": "monthly_revenue", "label": "Monthly sales", "unit": "currency", "hint": "Typical month, before the cost increase."},
    {"key": "daily_orders", "label": "Orders per day", "unit": "orders", "hint": "Average orders or sales a day, online and in store together."},
    {"key": "monthly_cogs", "label": "Monthly cost of goods", "unit": "currency", "hint": "What you pay suppliers for the goods you sell. Not wages, not rent, not shipping you absorb."},
    {"key": "monthly_fixed_costs", "label": "Monthly fixed costs", "unit": "currency", "hint": "Rent, wages, utilities, software, loan payments — everything that will not change in the next 90 days."},
    {"key": "cash_on_hand", "label": "Cash available", "unit": "currency", "hint": "What is in the business account today."},
    {"key": "supplier_increase_pct", "label": "Supplier cost increase", "unit": "%", "hint": "The increase you are facing, as a percentage of what you pay for goods."},
    {"key": "low_margin_share_pct", "label": "Share of orders on low-margin lines", "unit": "%", "hint": "Roughly what share of orders are lines that earn you little. A guess is fine; it is tested as an assumption."},
]
