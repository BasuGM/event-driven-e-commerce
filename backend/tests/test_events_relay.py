"""Relay: publish unpublished outbox rows to Redis Streams, mark them, never skip a failure."""

import json

import pytest
import redis

from apps.events.models import OutboxEvent
from apps.events.relay import publish_batch
from apps.events.streams import stream_name

from .test_concurrency import run_concurrently


def make_events(n, aggregate_type="order"):
    return [
        OutboxEvent.objects.create(
            event_type="OrderPlaced", aggregate_type=aggregate_type, aggregate_id=f"{i:032x}",
            payload={"n": i, "total": "10.50"},
        )
        for i in range(n)
    ]


class FailingClient:
    """Delegates to the real client but raises on the Nth XADD (1-based)."""

    def __init__(self, real, fail_on, exc):
        self.real, self.fail_on, self.exc, self.calls = real, fail_on, exc, 0

    def xadd(self, *args, **kwargs):
        self.calls += 1
        if self.calls == self.fail_on:
            raise self.exc
        return self.real.xadd(*args, **kwargs)


@pytest.mark.django_db
def test_publishes_in_order_with_the_event_id_and_marks_rows(events_redis):
    rows = make_events(3)

    result = publish_batch(events_redis)

    assert (result.selected, result.published, result.error) == (3, 3, None)
    entries = events_redis.xrange(stream_name("order"))
    assert [fields["id"] for _, fields in entries] == [str(r.id) for r in rows]
    first = entries[0][1]
    assert first["type"] == "OrderPlaced" and first["version"] == "1"
    assert json.loads(first["payload"]) == {"n": 0, "total": "10.50"}
    assert not OutboxEvent.objects.filter(published_at__isnull=True).exists()
    assert publish_batch(events_redis).selected == 0  # nothing left


@pytest.mark.django_db
def test_stops_at_the_first_redis_error_and_records_it(events_redis):
    rows = make_events(4)

    result = publish_batch(FailingClient(events_redis, fail_on=3, exc=redis.ConnectionError("refused")))

    assert (result.published, type(result.error)) == (2, redis.ConnectionError)
    state = {r.id: r for r in OutboxEvent.objects.all()}
    assert [state[r.id].published_at is not None for r in rows] == [True, True, False, False]
    failed = state[rows[2].id]
    assert (failed.attempts, failed.last_error) == (1, "ConnectionError: refused")
    assert state[rows[3].id].attempts == 0  # never tried: we don't skip past a failure

    # Redis is back: the same rows go out, in order
    assert publish_batch(events_redis).published == 2
    ids = [fields["id"] for _, fields in events_redis.xrange(stream_name("order"))]
    assert ids == [str(r.id) for r in rows]


@pytest.mark.django_db
def test_a_hung_redis_times_out_instead_of_holding_the_locks(events_redis):
    """socket_timeout turns a hang into redis.TimeoutError, which ends the batch normally."""
    assert events_redis.connection_pool.connection_kwargs["socket_timeout"] == 5
    assert events_redis.connection_pool.connection_kwargs["socket_connect_timeout"] == 2
    [row] = make_events(1)

    result = publish_batch(FailingClient(events_redis, fail_on=1, exc=redis.TimeoutError("Timeout reading from socket")))

    assert isinstance(result.error, redis.TimeoutError)
    row.refresh_from_db()
    assert (row.published_at, row.attempts) == (None, 1)


@pytest.mark.django_db(transaction=True)
def test_two_relays_never_publish_the_same_row(events_redis):
    make_events(200)

    def relay():
        published = 0
        while (result := publish_batch(events_redis, batch_size=20)).selected:
            published += result.published
        return published

    counts = run_concurrently(relay, relay)

    assert sum(counts) == 200, counts
    ids = [fields["id"] for _, fields in events_redis.xrange(stream_name("order"))]
    assert len(ids) == len(set(ids)) == 200
    assert not OutboxEvent.objects.filter(published_at__isnull=True).exists()
