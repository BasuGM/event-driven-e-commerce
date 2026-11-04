"""order_live: one Pub/Sub signal per order event, on that order's channel."""

import time
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events.consumers.order_live import OrderLiveConsumer
from apps.events.relay import publish_batch
from apps.fake_provider.provider import SUCCEED_LATER, choose
from apps.orders.live import channel_name
from apps.orders.services import cancel, release_expired

pytestmark = pytest.mark.django_db


@pytest.fixture
def listen(events_redis):
    """Subscribe to an order's channel; returns a function collecting what arrived."""
    pubsub = events_redis.pubsub(ignore_subscribe_messages=True)

    def subscribe(order):
        pubsub.subscribe(channel_name(order.external_id))
        pubsub.get_message(timeout=1)  # the subscribe confirmation

        def received():
            messages, deadline = [], time.monotonic() + 0.5
            while time.monotonic() < deadline:
                message = pubsub.get_message(timeout=0.1)
                if message:
                    messages.append(message["data"])
            return messages

        return received

    yield subscribe
    pubsub.close()


def consume(events_redis):
    consumer = OrderLiveConsumer(events_redis, consumer_name="t1")
    consumer.ensure_groups()
    publish_batch(events_redis)
    consumer.run_once(claim=False)
    return consumer


def test_each_order_event_publishes_one_signal_for_that_order(events_redis, awaiting_payment, run_deliveries, listen):
    order, _, fake = awaiting_payment
    received = listen(order)
    deliveries = choose(fake, SUCCEED_LATER, delay=60)
    release_expired(now=timezone.now() + timedelta(hours=1))  # ReservationExpired
    run_deliveries(deliveries)  # late success -> PaymentRefundDue

    consume(events_redis)

    from apps.events.models import OutboxEvent

    ids = list(
        OutboxEvent.objects.filter(aggregate_id=order.external_id).order_by("occurred_at", "id")
        .values_list("id", flat=True)
    )
    assert len(ids) == 3  # OrderPlaced, ReservationExpired, PaymentRefundDue
    assert received() == [str(i) for i in ids]  # one signal each, carrying the event id


def test_other_orders_are_not_signalled(events_redis, placed_order, make_user, make_offer, fill_cart, address, listen):
    from apps.orders.services import checkout

    order, _, _ = placed_order
    other_user = make_user()
    fill_cart(other_user, (make_offer(), 1))
    other = checkout(other_user, address)
    received = listen(other)
    cancel(order.pk)

    consume(events_redis)

    assert len(received()) == 1  # only `other`'s OrderPlaced


def test_a_duplicate_event_is_acked_without_a_second_signal(events_redis, placed_order, listen):
    order, _, _ = placed_order
    received = listen(order)
    consume(events_redis)
    # The same entry again for this group (e.g. redelivered after a crash before XACK)
    from apps.events.streams import stream_name

    [(_, fields)] = events_redis.xrange(stream_name("order"))
    events_redis.xadd(stream_name("order"), fields)
    OrderLiveConsumer(events_redis, consumer_name="t1").run_once(claim=False)

    assert len(received()) == 1
    assert events_redis.xpending(stream_name("order"), "order_live")["pending"] == 0
