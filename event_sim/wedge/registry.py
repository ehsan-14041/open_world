"""
The three wedges.

Three is the number the architecture is being tested at, and it is deliberately a hard stop:
one cost shock at a cafe, one cost shock at a retailer, and one capacity/pricing decision at a
service business. The third is there precisely because it is not a cost shock — if the shared
machinery only ever ran the same scenario shape with different nouns, it would not have shown
anything about whether the architecture generalises.
"""

from __future__ import annotations

from event_sim.cafe.wedge import CAFE_WEDGE
from event_sim.salon.wedge import SALON_WEDGE
from event_sim.shop.wedge import SHOP_WEDGE
from event_sim.wedge.spec import WedgeSpec

WEDGES: dict[str, WedgeSpec] = {
    CAFE_WEDGE.id: CAFE_WEDGE,
    SHOP_WEDGE.id: SHOP_WEDGE,
    SALON_WEDGE.id: SALON_WEDGE,
}

#: Chooser-screen order and iconography. Plain language only — no model vocabulary here.
CHOOSER = [
    {"id": "cafe", "icon": "☕", "business": CAFE_WEDGE.business, "question": CAFE_WEDGE.question},
    {"id": "shop", "icon": "🛍", "business": SHOP_WEDGE.business, "question": SHOP_WEDGE.question},
    {"id": "salon", "icon": "✂", "business": SALON_WEDGE.business, "question": SALON_WEDGE.question},
]


def get(wedge_id: str) -> WedgeSpec:
    try:
        return WEDGES[wedge_id]
    except KeyError:
        raise KeyError(f"Unknown wedge {wedge_id!r}. Available: {sorted(WEDGES)}") from None
