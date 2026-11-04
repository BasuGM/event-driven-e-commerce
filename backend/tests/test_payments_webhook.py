"""Webhook semantics: idempotent, order-independent, and never resurrecting a canceled order.

Events go through the real path: fake provider records them -> signed delivery -> the webhook
view -> handle_webhook -> services.pay(). Outbox rows show which order events were emitted.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.events.models import OutboxEvent
from apps.fake_provider.provider import FAIL, SUCCEED, SUCCEED_LATER, choose
from apps.orders.models import Order, Reservation
from apps.orders.services import checkout, release_expired
from apps.payments.gateway import PAYMENT_SUCCEEDED, WebhookEvent
from apps.payments.models import PaymentIntent, ProviderEvent
from apps.payments.services import handle_webhook, start_payment

from .test_concurrency import run_concurrently

pytestmark = pytest.mark.django_db


def emitted(order):
    return list(
        OutboxEvent.objects.filter(aggregate_id=order.external_id)
        .order_by("occurred_at", "id").values_list("event_type", flat=True)
    )


def refreshed(order, intent):
    order.refresh_from_db()
    intent.refresh_from_db()
    return order.status, intent.status, intent.needs_refund


def test_success_approves_once_even_when_delivered_twice(awaiting_payment, run_deliveries):
    order, intent, fake = awaiting_payment
    statuses = run_deliveries(choose(fake, SUCCEED, twice=True))

    assert statuses == [200, 200]  # the duplicate is acknowledged too, so the provider stops
    assert refreshed(order, intent) == ("approved", "succeeded", False)
    assert emitted(order) == ["OrderPlaced", "OrderPaid"]  # exactly one OrderPaid
    assert ProviderEvent.objects.count() == 1  # one event id, stored once
    assert order.payments.count() == 1  # one ledger row (orders.Payment)


def test_decline_cancels_once(awaiting_payment, run_deliveries):
    order, intent, fake = awaiting_payment
    run_deliveries(choose(fake, FAIL, twice=True))

    assert refreshed(order, intent) == ("canceled", "failed", False)
    assert emitted(order) == ["OrderPlaced", "PaymentFailed"]
    assert order.status_history.last().reason == "payment_failed"


def test_a_stale_decline_after_the_success_is_ignored(awaiting_payment, run_deliveries):
    """Declined at t-1, succeeded at t, delivered success first: the decline is old news."""
    order, intent, fake = awaiting_payment
    run_deliveries(choose(fake, SUCCEED, out_of_order=True))

    assert refreshed(order, intent) == ("approved", "succeeded", False)
    assert emitted(order) == ["OrderPlaced", "OrderPaid"]
    outcomes = dict(ProviderEvent.objects.values_list("type", "outcome"))
    assert outcomes == {"payment_intent.succeeded": "applied", "payment_intent.payment_failed": "ignored_stale"}


def test_decline_then_success_in_order_cancels_and_flags_a_refund(awaiting_payment, run_deliveries):
    """Our rule: a decline cancels the order. Money arriving afterwards is owed back."""
    order, intent, fake = awaiting_payment
    run_deliveries(choose(fake, FAIL))
    fake.status = "requires_payment"  # the customer retried on the provider's page
    fake.save()
    run_deliveries(choose(fake, SUCCEED))

    assert refreshed(order, intent) == ("canceled", "succeeded", True)
    assert intent.refund_reason == "paid after the order was canceled"
    assert emitted(order) == ["OrderPlaced", "PaymentFailed", "PaymentRefundDue"]


def test_success_delivered_late_but_paid_in_time_is_approved(awaiting_payment, run_deliveries):
    """The payment's own time decides: delivery lag alone doesn't cost the customer the order,
    as long as the sweeper hasn't released the stock yet."""
    order, intent, fake = awaiting_payment
    paid_at = timezone.now()
    deliveries = choose(fake, SUCCEED_LATER, delay=600, now=paid_at)
    Reservation.objects.update(expires_at=paid_at + timedelta(seconds=5))  # expired by delivery time

    run_deliveries(deliveries)

    assert refreshed(order, intent) == ("approved", "succeeded", False)
    assert emitted(order) == ["OrderPlaced", "OrderPaid"]


def test_success_after_the_sweeper_released_the_order_needs_a_refund(awaiting_payment, run_deliveries):
    order, intent, fake = awaiting_payment
    deliveries = choose(fake, SUCCEED_LATER, delay=60)
    assert release_expired(now=timezone.now() + timedelta(hours=1)) == 1  # sweeper wins

    run_deliveries(deliveries)

    assert refreshed(order, intent) == ("canceled", "succeeded", True)
    assert emitted(order) == ["OrderPlaced", "ReservationExpired", "PaymentRefundDue"]  # no OrderPaid


def test_success_paid_after_expiry_cancels_and_needs_a_refund(awaiting_payment):
    """A success whose own time is past the hold (sweeper not run yet): pay() cancels it."""
    order, intent, fake = awaiting_payment
    late = Reservation.objects.filter(order=order).order_by("expires_at").first().expires_at + timedelta(seconds=1)

    handle_webhook("fake", WebhookEvent(
        id="evt_late", type=PAYMENT_SUCCEEDED, created=late, payment_id=intent.provider_payment_id,
        raw_type="payment_intent.succeeded", payload={},
    ))

    assert refreshed(order, intent) == ("canceled", "succeeded", True)
    assert intent.refund_reason == "paid after the stock hold expired"
    assert emitted(order) == ["OrderPlaced", "ReservationExpired", "PaymentRefundDue"]


def test_refund_due_carries_the_payment_and_is_recorded_once(awaiting_payment, run_deliveries):
    order, intent, fake = awaiting_payment
    deliveries = choose(fake, SUCCEED_LATER, delay=60, twice=True)
    release_expired(now=timezone.now() + timedelta(hours=1))
    run_deliveries(deliveries)

    [refund] = OutboxEvent.objects.filter(event_type="PaymentRefundDue")
    assert refund.payload["payment"] == {
        "provider": "fake", "provider_payment_id": intent.provider_payment_id,
        "amount": str(intent.amount), "currency": "BRL", "refund_reason": "paid after the order was canceled",
    }
    assert refund.payload["order_id"] == order.external_id and refund.payload["lines"]


def test_events_for_unknown_payments_are_acknowledged_and_ignored():
    outcome = handle_webhook("fake", WebhookEvent(
        id="evt_unknown", type=PAYMENT_SUCCEEDED, created=datetime.now(UTC), payment_id="pi_nope",
        raw_type="payment_intent.succeeded", payload={},
    ))
    assert outcome == "no_change"


# --- race: the expiry sweeper and a success webhook on the same order ---------------------------


def _race_setup(make_user, make_offer, fill_cart, address):
    """Paid in time (2 s before expiry), webhook arriving just as the hold expires."""
    user = make_user()
    fill_cart(user, (make_offer(stock=3), 1))
    order = checkout(user, address)
    intent = start_payment(order, return_url="/")
    expires = timezone.now() - timedelta(milliseconds=50)
    Reservation.objects.filter(order=order).update(expires_at=expires)
    event = WebhookEvent(
        id=f"evt_race_{order.pk}", type=PAYMENT_SUCCEEDED, created=expires - timedelta(seconds=2),
        payment_id=intent.provider_payment_id, raw_type="payment_intent.succeeded", payload={},
    )
    return order, intent, event


def _check_one_winner(order, intent) -> str:
    order.refresh_from_db()
    intent.refresh_from_db()
    events = emitted(order)
    assert events.count("OrderPaid") + events.count("ReservationExpired") == 1, events
    assert intent.status == PaymentIntent.Status.SUCCEEDED
    if order.status == Order.Status.APPROVED:
        assert events == ["OrderPlaced", "OrderPaid"] and not intent.needs_refund
        return "approved"
    assert order.status == Order.Status.CANCELED and intent.needs_refund
    assert events == ["OrderPlaced", "ReservationExpired", "PaymentRefundDue"]
    return "refund"


@pytest.mark.django_db(transaction=True)
def test_sweeper_and_success_webhook_race_has_exactly_one_winner(make_user, make_offer, fill_cart, address):
    """Free-running race, several rounds: whoever wins, never both (no OrderPaid alongside
    ReservationExpired, no approved order with a refund flag)."""
    for _ in range(6):
        order, intent, event = _race_setup(make_user, make_offer, fill_cart, address)
        run_concurrently(lambda: release_expired(now=timezone.now()), lambda: handle_webhook("fake", event))
        _check_one_winner(order, intent)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("holds_lock_first, expected", [("webhook", "approved"), ("sweeper", "refund")])
def test_race_outcome_is_decided_by_who_holds_the_order_lock(
    holds_lock_first, expected, make_user, make_offer, fill_cart, address, monkeypatch
):
    """Deterministic contention: one side pauses *while holding the order lock* until the other
    side has started. The webhook holding it makes the sweeper skip (SKIP LOCKED) -> approved;
    the sweeper holding it makes the webhook wait, then find the order canceled -> refund."""
    import threading
    import time

    from apps.orders import services as order_services

    order, intent, event = _race_setup(make_user, make_offer, fill_cart, address)
    locked, other_started = threading.Event(), threading.Event()
    hook = "pay" if holds_lock_first == "webhook" else "_release_and_cancel"
    original = getattr(order_services, hook)

    def paused(*args, **kwargs):
        locked.set()  # the caller holds the order row lock at this point
        other_started.wait(timeout=5)
        time.sleep(0.2)  # let the other side reach the lock
        return original(*args, **kwargs)

    monkeypatch.setattr(order_services, hook, paused)

    def first():
        return handle_webhook("fake", event) if holds_lock_first == "webhook" else release_expired(now=timezone.now())

    def second():
        locked.wait(timeout=5)
        other_started.set()
        return release_expired(now=timezone.now()) if holds_lock_first == "webhook" else handle_webhook("fake", event)

    run_concurrently(first, second)

    assert _check_one_winner(order, intent) == expected
