"""Turn an order event into the email's subject, text and HTML."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.template.loader import render_to_string

from apps.catalog.models import Product
from apps.core.formatting import format_brl

from .models import Notification

K = Notification.Kind

COPY = {
    K.ORDER_PLACED: (
        "We've received order {number}",
        "Thanks for your order! We're holding your items for {ttl} minutes while you pay.",
    ),
    K.ORDER_PAID: ("Payment confirmed for order {number}", "Your payment went through. We'll get your order ready."),
    K.PAYMENT_FAILED: (
        "Payment failed for order {number}",
        "Your payment was declined, so we canceled the order and released the items. You can order again any time.",
    ),
    K.ORDER_CANCELED: ("Order {number} canceled", "Your order was canceled as requested. Nothing was charged."),
    K.RESERVATION_EXPIRED: (
        "Order {number} expired",
        "We didn't receive your payment in time, so the order was canceled and the items released.",
    ),
    K.REFUND_DUE: (
        "Refund due for order {number}",
        "We received your payment of {paid} after the order was canceled ({reason}). "
        "We owe you a refund of {paid}; you don't need to do anything.",
    ),
}

# A refund is also due when a second payment arrives for an order that was already paid (the
# order isn't canceled then): same subject, different explanation.
REFUND_DUE_ALREADY_PAID = (
    "Refund due for order {number}",
    "We're sorry: a second payment of {paid} was received for an order that was already paid. "
    "We owe you a refund of {paid}; you don't need to do anything.",
)


def render(kind: str, payload: dict, *, recipient_name: str) -> tuple[str, str, str]:
    order_id = payload["order_id"]
    number = f"#{order_id[:8]}"
    names = dict(Product.objects.filter(pk__in=[l["product_id"] for l in payload["lines"]]).values_list("id", "name"))
    lines = [
        {
            "name": names.get(line["product_id"], line["product_slug"]),
            "quantity": line["quantity"],
            "total": format_brl(Decimal(line["unit_price"]) * line["quantity"]),
        }
        for line in payload["lines"]
    ]
    totals = payload["totals"]
    payment = payload.get("payment", {})
    subject_t, intro_t = COPY[kind]
    if kind == K.REFUND_DUE and payload.get("status") != "canceled":
        subject_t, intro_t = REFUND_DUE_ALREADY_PAID
    fmt = {
        "number": number,
        "ttl": settings.RESERVATION_TTL_MINUTES,
        "paid": format_brl(payment.get("amount", totals["total"])),
        "reason": payment.get("refund_reason", ""),
    }
    context = {
        "subject": subject_t.format(**fmt),
        "intro": intro_t.format(**fmt),
        "name": recipient_name,
        "number": number,
        "lines": lines,
        "items_total": format_brl(totals["items_total"]),
        "freight_total": format_brl(totals["freight_total"]),
        "total": format_brl(totals["total"]),
        "order_url": f"{settings.FRONTEND_PUBLIC_URL.rstrip('/')}/orders/{order_id}",
    }
    return (
        context["subject"],
        render_to_string("notifications/order_email.txt", context),
        render_to_string("notifications/order_email.html", context),
    )
