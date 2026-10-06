"""
Trades that share a wedge's model.

A bakery whose flour bill jumps and a cafe whose ingredients jump are the same question asked
by different people: an input cost rose, and the owner can hold the price, raise it, or raise it
less and cut what earns least. The model is the same model — same variables, same lags, same
elasticity edge, same 162-point sweep — so a variant is vocabulary, not arithmetic. Nothing here
touches the engine, and a variant cannot: it carries no numbers at all.

What a variant DOES have to carry is how far the evidence travels. The cafe's elasticity comes
from research on eating out; bread is a staple people buy whatever the price, and a burger is
bought on impulse against easy substitutes. Neither is what that study measured. The catalogue
says so in each variant's own words, and the two-week test is the way an owner replaces the
borrowed figure with their own.
"""

from __future__ import annotations

from typing import Any

#: variant id -> the wedge whose model it borrows. Order is the order they are offered in.
VARIANTS: dict[str, dict[str, Any]] = {
    "bakery": {"base": "cafe", "icon": "🥖"},
    "fastfood": {"base": "cafe", "icon": "🍔"},
}


def variants_of(wedge_id: str) -> list[str]:
    """The trades offered on this wedge's model, in the order they are shown."""
    return [vid for vid, v in VARIANTS.items() if v["base"] == wedge_id]


def base_of(variant_id: str) -> str | None:
    v = VARIANTS.get(variant_id)
    return v["base"] if v else None
