"""Every order state change writes exactly one outbox event, in the same transaction."""

from datetime import timedelta

import pytest
from django.db import transaction
from django.utils import timezone

from apps.core.errors import InvalidTransition, OutOfStock
from apps.events.models import OutboxEvent
from apps.events.outbox import record_event
from apps.orders.services import cancel, checkout, pay, release_expired

pytestmark = pytest.mark.django_db


def events(order):
    return list(
        OutboxEvent.objects.filter(aggregate_id=order.external_id).order_by("occurred_at").values_list(
            "event_type", flat=True
        )
    )


def test_checkout_records_order_placed_with_the_consumers_payload(placed_order):
    order, user, (a, b) = placed_order
    [event] = OutboxEvent.objects.all()

    assert (event.event_type, event.aggregate_type, event.aggregate_id) == ("OrderPlaced", "order", order.external_id)
    assert event.schema_version == 1 and event.published_at is None
    payload = event.payload
    assert (payload["order_id"], payload["user_id"], payload["status"]) == (order.external_id, user.id, "created")
    # One line per offer (items are stored one per unit), money as decimal strings
    assert sorted(payload["lines"], key=lambda line: line["offer_id"]) == [
        {"offer_id": a.id, "product_id": a.product_id, "product_slug": a.product.slug, "seller_id": a.seller_id,
         "quantity": 2, "unit_price": "59.90", "unit_freight": "12.50"},
        {"offer_id": b.id, "product_id": b.product_id, "product_slug": b.product.slug, "seller_id": b.seller_id,
         "quantity": 1, "unit_price": "10.00", "unit_freight": "0.00"},
    ]
    assert payload["totals"] == {
        "item_count": 3, "items_total": "129.80", "freight_total": "25.00", "total": "154.80",
    }


@pytest.mark.parametrize(
    "act, expected",
    [
        (lambda o: pay(o.pk, "success"), "OrderPaid"),
        (lambda o: pay(o.pk, "fail"), "PaymentFailed"),
        (lambda o: cancel(o.pk), "OrderCanceled"),
    ],
)
def test_each_transition_records_one_event(placed_order, act, expected):
    order, _, _ = placed_order
    act(order)
    assert events(order) == ["OrderPlaced", expected]
    assert OutboxEvent.objects.get(event_type=expected).payload["status"] == ("approved" if expected == "OrderPaid" else "canceled")


def test_sweeper_records_reservation_expired(placed_order):
    order, _, _ = placed_order
    assert release_expired(now=timezone.now() + timedelta(hours=1)) == 1
    assert events(order) == ["OrderPlaced", "ReservationExpired"]
    assert OutboxEvent.objects.get(event_type="ReservationExpired").payload["source"] == "sweeper"
    # Idempotent sweeper: a second run neither changes the order nor emits again
    assert release_expired(now=timezone.now() + timedelta(hours=1)) == 0
    assert len(events(order)) == 2


def test_late_payment_records_reservation_expired_and_keeps_it(placed_order):
    """pay() commits the cancel and *then* raises: the event must survive that raise."""
    from apps.core.errors import ReservationExpired

    order, _, _ = placed_order
    with pytest.raises(ReservationExpired):
        pay(order.pk, "success", now=timezone.now() + timedelta(hours=1))
    assert events(order) == ["OrderPlaced", "ReservationExpired"]
    assert OutboxEvent.objects.get(event_type="ReservationExpired").payload["source"] == "payment_attempt"


def test_rejected_changes_leave_no_event(placed_order, make_user, make_offer, fill_cart, address):
    order, _, _ = placed_order
    pay(order.pk, "success")
    with pytest.raises(InvalidTransition):
        cancel(order.pk)  # already paid
    assert events(order) == ["OrderPlaced", "OrderPaid"]

    buyer = make_user()
    fill_cart(buyer, (make_offer(stock=1), 2))
    before = OutboxEvent.objects.count()
    with pytest.raises(OutOfStock):
        checkout(buyer, address)
    assert OutboxEvent.objects.count() == before


def test_rollback_after_the_write_leaves_no_event(make_user, make_offer, fill_cart, address):
    user = make_user()
    fill_cart(user, (make_offer(), 1))
    with pytest.raises(RuntimeError), transaction.atomic():
        checkout(user, address)  # its own atomic() becomes a savepoint of ours
        assert OutboxEvent.objects.count() == 1
        raise RuntimeError("something later in the same transaction fails")
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)  # the default wraps every test in a transaction
def test_record_event_refuses_to_run_outside_a_transaction():
    with pytest.raises(RuntimeError, match="inside the transaction"):
        record_event("OrderPlaced", "order", "x", {})
