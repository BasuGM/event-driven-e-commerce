"""Consumer framework: effectively-once processing on top of at-least-once delivery."""

import json
import uuid

import pytest

from apps.catalog.models import Category
from apps.events.consumer import Consumer
from apps.events.models import ProcessedEvent
from apps.events.streams import dlq_stream, stream_name

pytestmark = pytest.mark.django_db


class Crash(Exception):
    """Stands in for the process dying (e.g. between COMMIT and XACK)."""


class CountingConsumer(Consumer):
    """Its side effect is a database row, so we can see what committed and what rolled back."""

    name = "test_counter"
    streams = ("order",)
    event_types = frozenset({"OrderPlaced"})

    def __init__(self, *args, fail_with=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_with = fail_with

    def handle(self, event):
        Category.objects.create(name=f"evt-{event.id}", name_english="x", slug=f"evt-{event.id}")
        if self.fail_with:
            raise self.fail_with


def applied():
    return Category.objects.filter(name__startswith="evt-").count()


def publish(client, event_type="OrderPlaced", event_id=None, payload=None):
    fields = {
        "id": event_id or str(uuid.uuid4()), "type": event_type, "aggregate_type": "order",
        "aggregate_id": "a" * 32, "version": "1", "occurred_at": "2026-10-23T00:00:00+00:00",
        "payload": json.dumps(payload or {}),
    }
    client.xadd(stream_name("order"), fields)
    return fields["id"]


def consumer(client, name="c1", **kwargs):
    c = CountingConsumer(client, consumer_name=name, **kwargs)
    c.ensure_groups()
    return c


def pending(client):
    return client.xpending(stream_name("order"), CountingConsumer.name)["pending"]


def test_the_same_event_twice_is_applied_once(events_redis):
    c = consumer(events_redis)
    event_id = publish(events_redis)
    publish(events_redis, event_id=event_id)  # the relay re-sent it (crash before marking)

    c.run_once(claim=False)

    assert applied() == 1
    assert ProcessedEvent.objects.filter(consumer="test_counter", event_id=event_id).count() == 1
    assert pending(events_redis) == 0  # both entries acked


def test_crash_after_commit_before_ack_does_not_apply_twice(events_redis, monkeypatch):
    first = consumer(events_redis, name="c1")
    publish(events_redis)

    def crash(*args):
        raise Crash()

    monkeypatch.setattr(first, "_ack", crash)
    with pytest.raises(Crash):
        first.run_once(claim=False)
    assert applied() == 1 and pending(events_redis) == 1  # committed, but never acked

    # A restarted consumer reclaims the stuck entry (EVENTS_CLAIM_IDLE_MS = 0 in tests)
    second = consumer(events_redis, name="c2")
    second.run_once(claim=True)

    assert applied() == 1  # ProcessedEvent says it's done: the handler didn't run again
    assert pending(events_redis) == 0


def test_a_poison_event_is_dead_lettered_and_the_group_keeps_moving(events_redis, settings):
    assert settings.EVENTS_MAX_DELIVERIES == 3
    bad = consumer(events_redis, fail_with=ValueError("cannot apply this"))
    poison_id = publish(events_redis)

    bad.run_once(claim=False)  # delivery 1
    for _ in range(2):
        bad.run_once(claim=True)  # deliveries 2 and 3, via XAUTOCLAIM
    assert applied() == 0 and pending(events_redis) == 1  # each failure rolled back

    bad.run_once(claim=True)  # delivery 4 > max: dead-letter it

    [(_, dead)] = events_redis.xrange(dlq_stream())
    assert dead["id"] == poison_id
    assert dead["dlq_consumer"] == "test_counter" and dead["dlq_deliveries"] == "4"
    assert dead["dlq_error"] == "ValueError: cannot apply this"
    assert pending(events_redis) == 0
    assert not ProcessedEvent.objects.filter(event_id=poison_id).exists()

    good = consumer(events_redis)
    good_id = publish(events_redis)
    good.run_once(claim=True)
    assert ProcessedEvent.objects.filter(event_id=good_id).exists() and applied() == 1


def test_malformed_entries_are_retried_then_dead_lettered(events_redis):
    c = consumer(events_redis)
    events_redis.xadd(stream_name("order"), {"id": str(uuid.uuid4()), "type": "OrderPlaced", "payload": "{not json"})
    c.run_once(claim=False)
    for _ in range(3):
        c.run_once(claim=True)
    [(_, dead)] = events_redis.xrange(dlq_stream())
    assert dead["dlq_error"].startswith("KeyError") or dead["dlq_error"].startswith("JSONDecodeError")
    assert pending(events_redis) == 0


def test_event_types_it_does_not_handle_are_just_acked(events_redis):
    c = consumer(events_redis)
    publish(events_redis, event_type="OrderPaid")

    c.run_once(claim=False)

    assert pending(events_redis) == 0
    assert applied() == 0
    assert not ProcessedEvent.objects.exists()  # no idempotency row for events it ignores
