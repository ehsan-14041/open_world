"""
Where every number comes from, in four words a business owner already understands.

The internal evidence ladder (`literature_backed`, `expert_assumption`, `user_assumption`,
`derived`) stays in the record for reproducibility, but it is not customer copy. On the page
each quantity is one of four things:

    Your numbers          they typed it
    External research     it comes from a published study, and the study is named
    Model assumptions     we chose it; it is our judgement, and it is swept
    Calculated results    it follows from the others by arithmetic

The rule that matters is the third one. If literature does not justify a number, it is a model
assumption — not a citation stretched to cover it. Evidence that is category-level rather than
business-specific says so in its own transfer note.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from string import Formatter
from typing import Any

CUSTOMER = "Customer input"
RESEARCH = "External research"
ASSUMPTION = "Assumption"
DERIVED = "Derived"

LADDER = {
    CUSTOMER: "user_assumption",
    RESEARCH: "literature_backed",
    ASSUMPTION: "expert_assumption",
    DERIVED: "derived",
}


@dataclass(frozen=True)
class Assumption:
    key: str
    label: str
    value: str
    klass: str
    swept: bool
    note: str = ""
    source: str = ""
    #: How the value was built, and the figures it was built from. `value` above is the English
    #: rendering; these two let a page re-render the same value in another language without
    #: recomputing anything — the numbers travel, only the words around them change.
    value_spec: dict[str, Any] | None = None
    value_ctx: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ladder_status"] = LADDER[self.klass]
        return d


def class_counts(items: list[Assumption]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in items:
        out[a.klass] = out.get(a.klass, 0) + 1
    return out


#: Studies the wedges draw on. Each carries what it actually measured and — the part that
#: matters — what it does NOT license us to claim.
ANDREYEVA_2010 = {
    "id": "andreyeva2010",
    "citation": "Andreyeva T, Long MW, Brownell KD. The impact of food prices on consumption: a systematic review of research on the price elasticity of demand for food. American Journal of Public Health. 2010;100(2):216-222. doi:10.2105/AJPH.2008.151415",
    "population": "160 US studies, 1938-2007; 13 estimates for the 'food away from home' category",
    "estimate": "Own-price elasticity 0.81 (95% CI 0.56-1.07; range 0.23-1.76)",
    "limitations": "Category-level (primary demand): how much less the public eats out when eating out as a whole gets dearer. Not firm-level. US only. Studies up to 2007.",
    "transfer": "Justified for the CENTRAL setting when the cost shock is market-wide and competitors also raise prices, so the cafe's price moves with the category. Not justified on its own for a single cafe raising prices while competitors hold theirs.",
}

BIJMOLT_2005 = {
    "id": "bijmolt2005",
    "citation": "Bijmolt THA, van Heerde HJ, Pieters RGM. New empirical generalizations on the determinants of price elasticity. Journal of Marketing Research. 2005;42(2):141-156.",
    "population": "1,851 price elasticities from 81 studies, predominantly packaged consumer goods in retail scanner data",
    "estimate": "Mean brand-level price elasticity -2.62",
    "limitations": "Brand-level in supermarket categories with near-perfect substitutes on the same shelf. It measures switching between brands inside a shop, not switching between shops.",
    "transfer": "Used as the upper reference point. For a shop it is the 'my customers can buy the identical thing elsewhere' end of the range; for a cafe it is further away still, and the HIGH setting of 1.60 there is a judgement placed between the food category CI top (1.07) and this mean.",
}

TELLIS_1988 = {
    "id": "tellis1988",
    "citation": "Tellis GJ. The price elasticity of selective demand: a meta-analysis of econometric models of sales. Journal of Marketing Research. 1988;25(4):331-341.",
    "population": "367 price elasticities from roughly 220 brands and markets",
    "estimate": "Mean price elasticity -1.76",
    "limitations": "Selective (brand-level) demand, largely goods rather than services, and estimated from studies published up to the mid-1980s. Like Bijmolt it measures brand switching, not store switching.",
    "transfer": "A second brand-level reference point for the shop wedge, quoted so the range shown is not resting on a single meta-analysis. It does not establish what happens when one shop raises all of its prices at once.",
}


# ---- one spec, two renderers ---------------------------------------------------------------
#
# The registry is the most prose-heavy part of a wedge, and the PHP host has to produce exactly
# the same rows so a report generated on a shared host is the same report. Writing it twice
# would guarantee drift, so it is written once as a declarative spec and rendered from that in
# both languages. Only these value kinds exist; a wedge that needs a new one is a wedge whose
# evidence does not fit the shape, which is worth noticing.


def _money(value: float, dp: int = 0) -> str:
    return f"{value:,.{dp}f}"


#: Which ctx fields each value kind reads. Only these travel to the page — a registry row
#: should carry the numbers it shows, not the whole baseline.
def value_context(kind: dict, ctx: dict) -> dict[str, Any]:
    k = kind["kind"]
    if k in ("money", "g", "fixed"):
        return {kind["field"]: ctx[kind["field"]]}
    if k == "money_with_pct":
        return {kind["field"]: ctx[kind["field"]], kind["pct_of"]: ctx[kind["pct_of"]]}
    if k == "axis":
        return {"setting": ctx["axis_settings"].get(kind["axis"], "central")}
    if k == "template":
        return {name: ctx[name] for _, name, _, _ in Formatter().parse(kind["text"]) if name}
    return {}


def render_value(kind: dict, ctx: dict) -> str:
    """Render one registry row's value. `ctx` holds the baseline figures and derived numbers."""
    k = kind["kind"]
    if k == "literal":
        return str(kind["text"])
    if k == "money":
        return _money(ctx[kind["field"]], int(kind.get("dp", 0)))
    if k == "money_with_pct":
        return f"{_money(ctx[kind['field']])} ({ctx[kind['pct_of']]:.0f}% of sales)"
    if k == "g":
        return f"{kind.get('prefix', '')}{ctx[kind['field']]:g}{kind.get('suffix', '')}"
    if k == "fixed":
        return f"{kind.get('prefix', '')}{ctx[kind['field']]:.{int(kind.get('dp', 1))}f}{kind.get('suffix', '')}"
    if k == "axis":
        return str(kind["map"][ctx["axis_settings"].get(kind["axis"], "central")])
    if k == "template":
        return kind["text"].format(**ctx)
    raise KeyError(f"unknown registry value kind {k!r}")


def build_context(baseline, axis_settings: dict, knobs: dict, extra: dict) -> dict:
    """Everything a value kind may refer to, in one flat mapping."""
    ctx = dict(baseline.to_dict())
    ctx.update(knobs)
    ctx.update(extra)
    ctx["axis_settings"] = axis_settings
    return ctx


def render_registry(spec: list[dict], baseline, *, axis_settings: dict, knobs: dict,
                    extra: dict, custom_elasticity: float | None,
                    research_settings: list[str]) -> list[Assumption]:
    """
    Turn a wedge's spec into its assumption registry.

    The one rule with teeth: a row is classed as External research only at the axis settings a
    published study actually supports. Everywhere else it is a model assumption, whatever the
    prose around it says.
    """
    ctx = build_context(baseline, axis_settings, knobs, extra)
    out: list[Assumption] = []
    for row in spec:
        klass = row["klass"]
        value = render_value(row["value"], ctx)
        source = row.get("source", "")
        if row.get("elasticity"):
            setting = axis_settings.get(row["value"].get("axis", "price_sensitivity"), "central")
            klass = RESEARCH if setting in research_settings else ASSUMPTION
            if custom_elasticity is not None:
                value = f"{abs(custom_elasticity):.2f} (your value)"
                klass = CUSTOMER
                source = ""
            if klass != RESEARCH:
                source = row.get("assumption_source", source if klass == CUSTOMER else "")
        out.append(Assumption(
            key=row["key"], label=row["label"], value=value, klass=klass,
            swept=bool(row.get("swept", False)), note=row.get("note", ""), source=source,
            value_spec=row["value"], value_ctx=value_context(row["value"], ctx),
        ))
    return out
