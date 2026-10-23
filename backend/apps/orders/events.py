"""Order domain events: names and payloads. Emitted only from services.py, inside the
transaction that makes the change (see apps/events/outbox.py)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from apps.catalog.models import Offer
from apps.events.outbox import record_event

from .models import Order

ORDER_PLACED = "OrderPlaced"
ORDER_PAID = "OrderPaid"
PAYMENT_FAILED = "PaymentFailed"  # the order is canceled and its stock released
ORDER_CANCELED = "OrderCanceled"  # by the customer
RESERVATION_EXPIRED = "ReservationExpired"  # source: "sweeper" or "payment_attempt"
ORDER_EVENTS = frozenset({ORDER_PLACED, ORDER_PAID, PAYMENT_FAILED, ORDER_CANCELED, RESERVATION_EXPIRED})


def order_payload(order: Order, *, reason: str, now: datetime, source: str | None = None) -> dict:
    """What consumers need without re-querying: lines (offer/product/quantity), totals, user.

    Items are stored one row per unit (like Olist), so they're grouped into lines by
    (product, seller), the offer's natural key. Prices are the snapshots taken at checkout.
    """
    lines: dict[tuple[int, int], dict] = {}
    for item in order.items.select_related("product").order_by("item_number"):
        line = lines.setdefault(
            (item.product_id, item.seller_id),
            {
                "offer_id": None,
                "product_id": item.product_id,
                "product_slug": item.product.slug,
                "seller_id": item.seller_id,
                "quantity": 0,
                "unit_price": item.price,
                "unit_freight": item.freight_value,
            },
        )
        line["quantity"] += 1
    for offer_id, product_id, seller_id in Offer.objects.filter(
        product_id__in={p for p, _ in lines}, seller_id__in={s for _, s in lines}
    ).values_list("id", "product_id", "seller_id"):
        if (product_id, seller_id) in lines:
            lines[(product_id, seller_id)]["offer_id"] = offer_id

    items_total = sum((l["unit_price"] * l["quantity"] for l in lines.values()), Decimal("0.00"))
    freight_total = sum((l["unit_freight"] * l["quantity"] for l in lines.values()), Decimal("0.00"))
    payload = {
        "order_id": order.external_id,
        "user_id": order.customer.user_id,
        "status": order.status,
        "reason": reason,
        "occurred_at": now,
        "lines": list(lines.values()),
        "totals": {
            "item_count": sum(l["quantity"] for l in lines.values()),
            "items_total": items_total,
            "freight_total": freight_total,
            "total": items_total + freight_total,
        },
    }
    if source:
        payload["source"] = source
    return payload


def record_order_event(
    event_type: str, order: Order, *, reason: str, now: datetime, source: str | None = None
) -> None:
    record_event(event_type, "order", order.external_id, order_payload(order, reason=reason, now=now, source=source))
