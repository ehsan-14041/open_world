"""
The salon's starting position — demo defaults, and the structure a real owner fills in.

Nine inputs. Two of them are not in the other wedges and earn their place:

  * how full the diary already is, as a percentage. An owner knows "we're about 85% booked"
    far more readily than they know how many slots exist, and the number of slots follows from
    it — so we ask the easy question and derive the hard one.
  * how much busier it has got. This wedge's shock is demand, not cost.

Average ticket is deliberately NOT asked for: it follows from monthly sales and appointments.
Wages sit in fixed costs, not in the per-appointment cost, because over 90 days a salon's
staff cost does not move with one more or one fewer appointment.

The demo values are FICTIONAL — a small salon at a healthy margin whose diary is filling up.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace as _replace
from typing import Any

DAYS_PER_MONTH = 365.0 / 12.0


@dataclass(frozen=True)
class SalonBaseline:
    """Customer inputs. Units are plain currency, counts and percentages; no indices."""

    name: str
    monthly_revenue: float            # currency / month
    appointments_per_day: float       # appointments actually served today
    monthly_variable_costs: float     # products and consumables only — NOT wages
    monthly_fixed_costs: float        # rent, wages, utilities: fixed over 90 days
    cash_on_hand: float               # currency
    utilisation_pct: float            # how full the diary is today, percent
    demand_growth_pct: float          # how much busier it has become
    low_margin_share_pct: float       # share of appointments on discounted / low-margin services
    is_demo: bool = True
    notes: list[str] = field(default_factory=list)

    # --- derived ---------------------------------------------------------------------------

    @property
    def average_ticket(self) -> float:
        return self.monthly_revenue / (self.appointments_per_day * DAYS_PER_MONTH)

    @property
    def unit_cost(self) -> float:
        """Products and consumables per appointment."""
        return self.monthly_variable_costs / (self.appointments_per_day * DAYS_PER_MONTH)

    @property
    def capacity_per_day(self) -> float:
        """Appointment slots available per day, implied by today's diary."""
        return self.appointments_per_day / (self.utilisation_pct / 100.0)

    @property
    def daily_units(self) -> float:
        return self.appointments_per_day

    @property
    def daily_fixed_costs(self) -> float:
        return self.monthly_fixed_costs / DAYS_PER_MONTH

    @property
    def variable_cost_pct(self) -> float:
        return 100.0 * self.monthly_variable_costs / self.monthly_revenue

    @property
    def gross_margin_pct(self) -> float:
        return 100.0 - self.variable_cost_pct

    @property
    def monthly_gross_profit(self) -> float:
        return self.monthly_revenue - self.monthly_variable_costs

    @property
    def monthly_net(self) -> float:
        return self.monthly_gross_profit - self.monthly_fixed_costs

    @property
    def net_margin_pct(self) -> float:
        return 100.0 * self.monthly_net / self.monthly_revenue

    #: Present for symmetry with the other wedges' reports.
    @property
    def monthly_cogs(self) -> float:
        return self.monthly_variable_costs

    @property
    def cogs_pct(self) -> float:
        return self.variable_cost_pct

    def replace(self, **changes: Any) -> "SalonBaseline":
        return _replace(self, **changes)

    # --- contract ---------------------------------------------------------------------------

    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.monthly_revenue <= 0:
            problems.append("Monthly sales must be greater than zero.")
        if self.appointments_per_day <= 0:
            problems.append("Appointments per day must be greater than zero.")
        if self.monthly_variable_costs < 0:
            problems.append("Product cost cannot be negative.")
        if self.monthly_revenue > 0 and self.monthly_variable_costs >= self.monthly_revenue:
            problems.append("Product cost must be below monthly sales.")
        if self.monthly_fixed_costs < 0:
            problems.append("Fixed costs cannot be negative.")
        if self.cash_on_hand < 0:
            problems.append("Cash on hand cannot be negative.")
        if not 1 <= self.utilisation_pct <= 100:
            problems.append("How full the diary is should be between 1% and 100%.")
        if not 0 <= self.demand_growth_pct <= 200:
            problems.append("The increase in demand should be between 0% and 200%.")
        if not 0 <= self.low_margin_share_pct <= 100:
            problems.append("The low-margin share should be between 0% and 100%.")
        return problems

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "is_demo": self.is_demo,
            "monthly_revenue": round(self.monthly_revenue, 2),
            "appointments_per_day": round(self.appointments_per_day, 2),
            "average_ticket": round(self.average_ticket, 2),
            "monthly_variable_costs": round(self.monthly_variable_costs, 2),
            "variable_cost_pct": round(self.variable_cost_pct, 1),
            "gross_margin_pct": round(self.gross_margin_pct, 1),
            "monthly_fixed_costs": round(self.monthly_fixed_costs, 2),
            "monthly_net": round(self.monthly_net, 2),
            "net_margin_pct": round(self.net_margin_pct, 1),
            "cash_on_hand": round(self.cash_on_hand, 2),
            "utilisation_pct": self.utilisation_pct,
            "capacity_per_day": round(self.capacity_per_day, 2),
            "demand_growth_pct": self.demand_growth_pct,
            "low_margin_share_pct": self.low_margin_share_pct,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SalonBaseline":
        return cls(
            name=str(d.get("name") or "Unnamed salon"),
            monthly_revenue=float(d["monthly_revenue"]),
            appointments_per_day=float(d["appointments_per_day"]),
            monthly_variable_costs=float(d["monthly_variable_costs"]),
            monthly_fixed_costs=float(d["monthly_fixed_costs"]),
            cash_on_hand=float(d["cash_on_hand"]),
            utilisation_pct=float(d.get("utilisation_pct", 85.0)),
            demand_growth_pct=float(d.get("demand_growth_pct", 25.0)),
            low_margin_share_pct=float(d.get("low_margin_share_pct", 25.0)),
            is_demo=bool(d.get("is_demo", False)),
            notes=list(d.get("notes") or []),
        )


#: The fictional demo salon. Twelve appointments a day at about $66, products at 12% of
#: revenue, staff and rent in fixed costs, a healthy 17% net margin, and a diary already 85%
#: full when demand rises 25%. Those last two numbers are the whole scenario: the extra demand
#: cannot all be served, so the question stops being "how do I get more customers".
DEMO_SALON = SalonBaseline(
    name="Demo salon (fictional)",
    monthly_revenue=24000.0,
    appointments_per_day=12.0,
    monthly_variable_costs=2880.0,
    monthly_fixed_costs=17000.0,
    cash_on_hand=9000.0,
    utilisation_pct=85.0,
    demand_growth_pct=25.0,
    low_margin_share_pct=25.0,
    is_demo=True,
    notes=[
        "Fictional. A small salon at a realistic margin, not a composite of any real business.",
        "Staff cost sits in fixed costs: over 90 days it does not move with one more appointment.",
        "At 85% full, roughly 14 slots a day exist and 12 are used.",
    ],
)

INTAKE_FIELDS: list[dict[str, str]] = [
    {"key": "name", "label": "Business name", "unit": "", "hint": "Only used on the report."},
    {"key": "monthly_revenue", "label": "Monthly sales", "unit": "currency", "hint": "A typical month right now."},
    {"key": "appointments_per_day", "label": "Appointments per day", "unit": "appointments", "hint": "How many you actually do on an average working day."},
    {"key": "utilisation_pct", "label": "How full is the diary?", "unit": "%", "hint": "Roughly what share of your available appointment slots get booked. 100% means completely full."},
    {"key": "monthly_variable_costs", "label": "Monthly product cost", "unit": "currency", "hint": "Colour, product, consumables — what you use up per appointment. NOT wages and NOT rent."},
    {"key": "monthly_fixed_costs", "label": "Monthly fixed costs", "unit": "currency", "hint": "Rent, wages, utilities, everything that will not change in the next 90 days."},
    {"key": "cash_on_hand", "label": "Cash available", "unit": "currency", "hint": "What is in the business account today."},
    {"key": "demand_growth_pct", "label": "How much busier?", "unit": "%", "hint": "How much more demand you are seeing than before — enquiries, requests, waiting list."},
    {"key": "low_margin_share_pct", "label": "Share on discounted / low-margin services", "unit": "%", "hint": "Roughly what share of appointments are discounted or earn you least. A guess is fine; it is tested as an assumption."},
]
