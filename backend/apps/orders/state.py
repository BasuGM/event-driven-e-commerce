"""The order state machine: an explicit transition table, enforced in one function."""

from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.core.errors import InvalidTransition

from .models import Order, OrderStatusHistory

S = Order.Status

TRANSITIONS: dict[str, frozenset[str]] = {
    S.CREATED: frozenset({S.APPROVED, S.CANCELED}),  # paid / payment failed, expired, customer
    S.APPROVED: frozenset({S.INVOICED, S.CANCELED}),  # canceled = refund (later step)
    S.INVOICED: frozenset({S.SHIPPED}),
    S.SHIPPED: frozenset({S.DELIVERED}),
    # delivered and canceled are terminal; Olist's processing/unavailable are historical only
}

# Timestamp columns stamped when an order enters a status
_STAMPS = {S.APPROVED: "approved_at", S.SHIPPED: "delivered_carrier_at", S.DELIVERED: "delivered_customer_at"}


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in TRANSITIONS.get(from_status, frozenset())


def transition(order: Order, to_status: str, reason: str, *, now: datetime | None = None) -> Order:
    """Move an order to ``to_status`` and record it. Illegal moves raise InvalidTransition.

    The caller must hold the order's row lock (``select_for_update``) inside a transaction, so
    two requests can't both read "created" and both transition.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("transition() must run inside transaction.atomic() on a locked order")
    from_status = order.status
    if not can_transition(from_status, to_status):
        raise InvalidTransition(
            f"Order can't go from '{from_status}' to '{to_status}'.",
            current_status=from_status,
        )
    now = now or timezone.now()
    order.status = to_status
    fields = ["status"]
    if column := _STAMPS.get(to_status):
        setattr(order, column, now)
        fields.append(column)
    order.save(update_fields=fields)
    OrderStatusHistory.objects.create(order=order, from_status=from_status, to_status=to_status, reason=reason)
    return order
