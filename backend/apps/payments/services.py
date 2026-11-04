"""Starting a payment, and applying the provider's verified events to payments and orders.

Lock order (project rule): Order -> PaymentIntent -> Offers. ``services.pay()`` locks the order
again (already held, so no wait) and then the offers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from django.db import IntegrityError, transaction

from apps.core.errors import InvalidTransition, ReservationExpired
from apps.events.outbox import record_event
from apps.orders import services as order_services
from apps.orders.events import order_payload
from apps.orders.models import Order, Reservation

from .gateway import PAYMENT_FAILED, PAYMENT_SUCCEEDED, WebhookEvent, get_gateway
from .models import PaymentIntent, ProviderEvent

logger = logging.getLogger(__name__)

PAYMENT_REFUND_DUE = "PaymentRefundDue"
Outcome = ProviderEvent.Outcome


def _now() -> datetime:
    return datetime.now(UTC)


def start_payment(order: Order, *, return_url: str) -> PaymentIntent:
    """Create (or reuse) the order's open payment intent. Raises InvalidTransition if the order
    can't be paid (not unpaid, or its stock hold expired)."""
    _check_payable(order)
    open_intent = order.payment_intents.filter(status=PaymentIntent.Status.REQUIRES_PAYMENT).first()
    if open_intent is not None:
        return open_intent

    totals = order_services.order_totals(order)
    expires_at = (
        order.reservations.filter(status=Reservation.Status.ACTIVE).order_by("expires_at")
        .values_list("expires_at", flat=True).first()
    )
    gateway = get_gateway()
    # The provider call happens outside any transaction (it may be slow network I/O). Its
    # idempotency key is derived from the order, so two concurrent clicks get the same payment.
    created = gateway.create_payment(
        amount=totals[0] + totals[1], currency="BRL", reference=order.external_id,
        return_url=return_url, expires_at=expires_at, idempotency_key=f"order:{order.external_id}:intent",
    )
    with transaction.atomic():
        order = order_services.lock_order(order.pk)
        try:
            with transaction.atomic():  # savepoint: a concurrent click may have inserted it
                intent, _ = PaymentIntent.objects.get_or_create(
                    provider_payment_id=created.id,
                    defaults={
                        "order": order, "provider": gateway.name, "amount": totals[0] + totals[1],
                        "currency": "BRL", "redirect_url": created.redirect_url,
                    },
                )
        except IntegrityError:
            intent = PaymentIntent.objects.get(provider_payment_id=created.id)
    return intent


def _check_payable(order: Order) -> None:
    if order.status != Order.Status.CREATED:
        raise InvalidTransition(f"Only unpaid orders can be paid; this order is '{order.status}'.", current_status=order.status)
    expired = order.reservations.filter(status=Reservation.Status.ACTIVE, expires_at__lte=_now()).exists()
    if expired:
        raise ReservationExpired("The stock hold for this order has expired.", current_status=order.status)


# --- webhooks ---------------------------------------------------------------------------------


def _record_once(provider: str, event: WebhookEvent) -> ProviderEvent | None:
    """Insert the event; None if we've already seen it (duplicate delivery). A concurrent
    duplicate waits on the unique index until the first commits, then gets IntegrityError."""
    try:
        with transaction.atomic():  # savepoint, so the outer transaction survives a duplicate
            return ProviderEvent.objects.create(
                provider=provider, provider_event_id=event.id, type=event.raw_type,
                payload=event.payload, created_at=event.created,
            )
    except IntegrityError:
        return None


def handle_webhook(provider: str, event: WebhookEvent) -> str:
    """Apply one verified event, exactly once. Returns the outcome (or "duplicate")."""
    with transaction.atomic():
        stored = _record_once(provider, event)
        if stored is None:
            return "duplicate"
        intent = (
            PaymentIntent.objects.filter(provider=provider, provider_payment_id=event.payment_id).first()
            if event.payment_id else None
        )
        if intent is None or event.type not in (PAYMENT_SUCCEEDED, PAYMENT_FAILED):
            if event.payment_id and intent is None:
                logger.warning("Webhook %s for unknown payment %s", event.id, event.payment_id)
            stored.outcome = Outcome.NO_CHANGE
            stored.save(update_fields=["outcome"])
            return stored.outcome

        order = order_services.lock_order(intent.order_id)  # Order first ...
        intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)  # ... then the intent
        if event.type == PAYMENT_SUCCEEDED:
            outcome = _apply_success(intent, order, event)
        else:
            outcome = _apply_failure(intent, order, event)
        stored.payment_intent, stored.outcome = intent, outcome
        stored.save(update_fields=["payment_intent", "outcome"])
        return outcome


def _apply_success(intent: PaymentIntent, order: Order, event: WebhookEvent) -> str:
    if intent.status == PaymentIntent.Status.SUCCEEDED:
        return Outcome.NO_CHANGE
    intent.status, intent.last_event_at = PaymentIntent.Status.SUCCEEDED, event.created
    if order.status == Order.Status.CREATED:
        try:
            # The payment's own time decides whether it was within the hold: a webhook that is
            # merely delivered late still counts, as long as the stock hasn't been released.
            order_services.pay(order.pk, "success", now=event.created)
        except ReservationExpired:  # paid after the hold expired: pay() canceled the order
            return _flag_refund(intent, order, event, "paid after the stock hold expired")
        intent.save()
        return Outcome.APPLIED
    if order.status == Order.Status.CANCELED:
        return _flag_refund(intent, order, event, "paid after the order was canceled")
    # Already approved (or further along) through another payment: a second charge
    return _flag_refund(intent, order, event, f"order already {order.status}")


def _apply_failure(intent: PaymentIntent, order: Order, event: WebhookEvent) -> str:
    stale = intent.status == PaymentIntent.Status.SUCCEEDED or (
        intent.last_event_at is not None and event.created < intent.last_event_at
    )
    if stale:  # e.g. a decline delivered after the success that followed it
        return Outcome.IGNORED_STALE
    intent.status, intent.last_event_at = PaymentIntent.Status.FAILED, event.created
    intent.save()
    if order.status != Order.Status.CREATED:
        return Outcome.NO_CHANGE
    try:
        order_services.pay(order.pk, "fail", now=event.created)
    except (InvalidTransition, ReservationExpired):
        return Outcome.NO_CHANGE  # expiry got there first: the order is canceled either way
    return Outcome.APPLIED


def _flag_refund(intent: PaymentIntent, order: Order, event: WebhookEvent, reason: str) -> str:
    intent.needs_refund, intent.refund_reason = True, reason
    intent.save()
    order.refresh_from_db()
    payload = order_payload(order, reason="refund_due", now=event.created)
    payload["payment"] = {
        "provider": intent.provider,
        "provider_payment_id": intent.provider_payment_id,
        "amount": intent.amount,
        "currency": intent.currency,
        "refund_reason": reason,
    }
    record_event(PAYMENT_REFUND_DUE, "order", order.external_id, payload)
    logger.warning("Payment %s for order %s needs a refund: %s", intent.provider_payment_id, order.external_id, reason)
    return Outcome.REFUND_FLAGGED
