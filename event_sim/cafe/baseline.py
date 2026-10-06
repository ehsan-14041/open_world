"""
The cafe's starting position — demo defaults, and the structure a real owner fills in.

Eight inputs. Every one of them is something an owner can read off their own books in a few
minutes; nothing here requires a model, an estimate from us, or a number they would have to
guess at. That is the point of the intake: the module stays fixed, and only these numbers
change between the demo cafe and a real one.

The demo values are FICTIONAL. They are chosen to be realistic for a single-site cafe at a
thin but positive margin, so that a 30% ingredient shock is a genuine problem rather than a
rounding error, but they did not come from any real business and must never be presented as
if they did.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any

DAYS_PER_MONTH = 365.0 / 12.0


@dataclass(frozen=True)
class CafeBaseline:
    """Customer inputs. Units are plain currency and counts; no indices."""

    name: str
    monthly_revenue: float            # currency / month
    daily_orders: float               # orders / day
    monthly_cogs: float               # ingredient / input cost, currency / month
    monthly_fixed_costs: float        # rent, wages, utilities, everything that does not move in 90 days
    cash_on_hand: float               # currency
    supplier_increase_pct: float      # the shock, percent (e.g. 30)
    low_margin_share_pct: float       # share of orders on items that could be removed/reformulated
    is_demo: bool = True
    notes: list[str] = field(default_factory=list)

    # --- derived, not input --------------------------------------------------------------

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

    # --- names the shared accounting uses, so one ledger serves every wedge ---------------

    @property
    def daily_units(self) -> float:
        return self.daily_orders

    @property
    def average_ticket(self) -> float:
        return self.average_order_value

    @property
    def unit_cost(self) -> float:
        return self.cogs_per_order

    def replace(self, **changes: Any) -> "CafeBaseline":
        from dataclasses import replace as _replace
        return _replace(self, **changes)

    def validate(self) -> list[str]:
        """Plain-language problems with the inputs. Empty list means usable."""
        problems: list[str] = []
        if self.monthly_revenue <= 0:
            problems.append("Monthly revenue must be positive.")
        if self.daily_orders <= 0:
            problems.append("Daily orders must be positive.")
        if not 0 < self.monthly_cogs < self.monthly_revenue:
            problems.append("Ingredient cost must be positive and below revenue.")
        if self.monthly_fixed_costs < 0:
            problems.append("Fixed costs cannot be negative.")
        if self.cash_on_hand < 0:
            problems.append("Cash on hand cannot be negative.")
        if not 0 <= self.supplier_increase_pct <= 150:
            problems.append("Supplier increase should be between 0% and 150%.")
        if not 0 <= self.low_margin_share_pct <= 60:
            problems.append("Low-margin share should be between 0% and 60% of orders.")
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
    def from_dict(cls, d: dict[str, Any]) -> CafeBaseline:
        return cls(
            name=str(d.get("name") or "Unnamed cafe"),
            monthly_revenue=float(d["monthly_revenue"]),
            daily_orders=float(d["daily_orders"]),
            monthly_cogs=float(d["monthly_cogs"]),
            monthly_fixed_costs=float(d["monthly_fixed_costs"]),
            cash_on_hand=float(d["cash_on_hand"]),
            supplier_increase_pct=float(d.get("supplier_increase_pct", 30.0)),
            low_margin_share_pct=float(d.get("low_margin_share_pct", 20.0)),
            is_demo=bool(d.get("is_demo", False)),
            notes=list(d.get("notes") or []),
        )


#: The fictional demo cafe. A single-site neighbourhood cafe: ~200 orders a day at about
#: $8 a ticket, ingredients at 32% of revenue, a thin 7% net margin, and five weeks of cash.
DEMO_CAFE = CafeBaseline(
    name="Demo cafe (fictional)",
    monthly_revenue=48_600.0,
    daily_orders=200.0,
    monthly_cogs=15_550.0,
    monthly_fixed_costs=29_500.0,
    cash_on_hand=18_000.0,
    supplier_increase_pct=30.0,
    low_margin_share_pct=20.0,
    is_demo=True,
    notes=[
        "All values are fictional and chosen for illustration; they are not from any real business.",
        "Fixed costs include wages: over a 90-day horizon staffing is treated as fixed.",
    ],
)

#: The intake questions, in the order an owner would answer them. Labels are customer-facing.
INTAKE_FIELDS: list[dict[str, str]] = [
    {"key": "name", "label": "Business name", "unit": "", "hint": "Only used on the report."},
    {"key": "monthly_revenue", "label": "Monthly sales", "unit": "currency", "hint": "Typical month, before the cost increase."},
    {"key": "daily_orders", "label": "Orders per day", "unit": "orders", "hint": "Average transactions a day."},
    {"key": "monthly_cogs", "label": "Monthly ingredient / input cost", "unit": "currency", "hint": "What you pay suppliers for what you sell. Not wages, not rent."},
    {"key": "monthly_fixed_costs", "label": "Monthly fixed costs", "unit": "currency", "hint": "Rent, wages, utilities, loan payments — everything that will not change in the next 90 days."},
    {"key": "cash_on_hand", "label": "Cash available", "unit": "currency", "hint": "What is in the business account today."},
    {"key": "supplier_increase_pct", "label": "Expected supplier cost increase", "unit": "%", "hint": "The increase you are facing, as a percentage of your ingredient cost."},
    {"key": "low_margin_share_pct", "label": "Share of orders on low-margin items", "unit": "%", "hint": "Roughly what share of orders are items you could drop or reformulate. A guess is fine; it is tested as an assumption."},
]
