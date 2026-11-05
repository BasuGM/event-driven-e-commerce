"""7a: the event log, the staff explorer API (staff-only) and dead-letter retry."""

import json
import uuid

import pytest
from rest_framework.test import APIClient

from apps.events.consumers.event_log import EventLogConsumer
from apps.events.consumers.product_stats import ProductStatsConsumer
from apps.events.models import DeadLetterRetry, EventLog, ProcessedEvent
from apps.events.relay import publish_batch
from apps.events.streams import dlq_stream, stream_name
from apps.orders.services import cancel

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client(make_user):
    user = make_user(email="staff-tester@example.com")
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    client = APIClient()
    client.force_login(user)
    client.user = user
    return client


def started(cls, client, name="t1"):
    consumer = cls(client, consumer_name=name)
    consumer.ensure_groups()
    return consumer


def entry(event_type="OrderPlaced", event_id=None, aggregate_id="a" * 32, payload=None):
    return {
        "id": event_id or str(uuid.uuid4()), "type": event_type, "aggregate_type": "order",
        "aggregate_id": aggregate_id, "version": "1", "occurred_at": "2026-11-04T10:00:00+00:00",
        "payload": json.dumps(payload or {"order_id": aggregate_id, "lines": []}),
    }


# --- event_log --------------------------------------------------------------------------------


def test_event_log_stores_every_event_once(events_redis):
    log = started(EventLogConsumer, events_redis)
    fields = entry()
    events_redis.xadd(stream_name("order"), fields)
    events_redis.xadd(stream_name("order"), fields)  # the relay re-sent it
    events_redis.xadd(stream_name("product"), {**entry("ProductsChanged"), "aggregate_type": "product"})

    log.run_once(claim=False)

    assert EventLog.objects.count() == 2  # every type, every stream, duplicates once
    row = EventLog.objects.get(event_id=fields["id"])
    assert (row.type, row.stream, row.payload) == ("OrderPlaced", stream_name("order"), json.loads(fields["payload"]))

    # Even without ProcessedEvent (e.g. a replay under another group), the unique id holds
    class Replay(EventLogConsumer):
        name = "event_log_replay"

    started(Replay, events_redis).run_once(claim=False)
    assert EventLog.objects.count() == 2


# --- access -----------------------------------------------------------------------------------


STAFF_URLS = [
    ("get", "/api/staff/events/"),
    ("get", "/api/staff/events/types/"),
    ("get", f"/api/staff/orders/{'a' * 32}/events/"),
    ("get", "/api/staff/health/"),
    ("post", "/api/staff/dead-letters/1-0/retry/"),
]


@pytest.mark.parametrize("method, url", STAFF_URLS)
def test_staff_endpoints_are_404_for_anonymous_and_customers(method, url, user_client, events_redis):
    assert getattr(APIClient(), method)(url).status_code == 404
    assert getattr(user_client(), method)(url).status_code == 404


def test_retry_needs_a_csrf_token(make_user, events_redis):
    user = make_user()
    user.is_staff = True
    user.save()
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.post("/api/staff/dead-letters/1-0/retry/").status_code == 403


# --- events list + order timeline ---------------------------------------------------------------


def test_events_list_filters_newest_first(staff_client, events_redis):
    log = started(EventLogConsumer, events_redis)
    for event_type, aggregate in [("OrderPlaced", "a" * 32), ("OrderPaid", "a" * 32), ("OrderPlaced", "b" * 32)]:
        events_redis.xadd(stream_name("order"), entry(event_type, aggregate_id=aggregate))
    log.run_once(claim=False)

    data = staff_client.get("/api/staff/events/", {"type": "OrderPlaced"}).json()
    assert data["count"] == 2 and {e["type"] for e in data["results"]} == {"OrderPlaced"}
    assert staff_client.get("/api/staff/events/", {"aggregate_id": "b" * 32}).json()["count"] == 1
    assert staff_client.get("/api/staff/events/", {"date_from": "2026-11-05"}).json()["count"] == 0
    bad = staff_client.get("/api/staff/events/", {"date_from": "2026-11-05", "date_to": "2026-11-01"})
    assert bad.status_code == 400 and "date_to" in bad.json()
    assert staff_client.get("/api/staff/events/types/").json() == ["OrderPaid", "OrderPlaced"]


def test_order_timeline_lists_events_in_order_with_consumer_status(staff_client, events_redis, placed_order):
    order, _, _ = placed_order
    cancel(order.pk)
    publish_batch(events_redis)
    started(EventLogConsumer, events_redis).run_once(claim=False)
    started(ProductStatsConsumer, events_redis).run_once(claim=False)  # notifications etc. not run

    timeline = staff_client.get(f"/api/staff/orders/{order.external_id}/events/").json()

    assert [e["type"] for e in timeline] == ["OrderPlaced", "OrderCanceled"]
    consumers = {c["name"]: c["processed_at"] for c in timeline[0]["consumers"]}
    assert set(consumers) == {"event_log", "notifications", "order_live", "product_stats"}
    assert consumers["event_log"] and consumers["product_stats"]  # processed (timestamps)
    assert consumers["notifications"] is None and consumers["order_live"] is None  # pending


# --- health ------------------------------------------------------------------------------------


def test_health_reports_pending_and_lag_per_group(staff_client, events_redis):
    started(EventLogConsumer, events_redis)  # creates its group
    events_redis.xadd(stream_name("order"), entry())
    events_redis.xadd(stream_name("order"), entry())
    # delivered to event_log but not acked -> pending; product_stats' group doesn't exist yet
    events_redis.xreadgroup("event_log", "t1", {stream_name("order"): ">"}, count=1)

    groups = {(g["stream"], g["group"]): g for g in staff_client.get("/api/staff/health/").json()["groups"]}
    event_log = groups[(stream_name("order"), "event_log")]
    assert (event_log["exists"], event_log["pending"], event_log["lag"]) == (True, 1, 1)
    assert groups[(stream_name("order"), "product_stats")]["exists"] is False


# --- dead-letter retry ---------------------------------------------------------------------------


def test_retry_redelivers_a_dead_letter_once_and_only_the_failed_consumer_applies_it(
    staff_client, events_redis, settings, monkeypatch
):
    fields = entry()
    events_redis.xadd(stream_name("order"), fields)
    log = started(EventLogConsumer, events_redis)
    log.run_once(claim=False)  # event_log processes it fine

    stats = started(ProductStatsConsumer, events_redis)
    monkeypatch.setattr(stats, "handle", lambda event: (_ for _ in ()).throw(RuntimeError("bug")))
    stats.run_once(claim=False)
    for _ in range(settings.EVENTS_MAX_DELIVERIES):
        stats.run_once(claim=True)
    [dead] = staff_client.get("/api/staff/health/").json()["dead_letters"]
    assert (dead["event_id"], dead["consumer"], dead["error"]) == (fields["id"], "product_stats", "RuntimeError: bug")
    assert dead["retried_at"] is None

    monkeypatch.undo()  # the bug is fixed
    stats = started(ProductStatsConsumer, events_redis)
    response = staff_client.post(f"/api/staff/dead-letters/{dead['entry_id']}/retry/")
    assert response.status_code == 200 and response.json()["created"] is True
    assert response.json()["retried_by"] == "staff-tester@example.com"
    stream_len = events_redis.xlen(stream_name("order"))

    again = staff_client.post(f"/api/staff/dead-letters/{dead['entry_id']}/retry/")
    assert again.json()["created"] is False  # idempotent: no second delivery
    assert events_redis.xlen(stream_name("order")) == stream_len
    assert DeadLetterRetry.objects.count() == 1

    stats.run_once(claim=False)
    log.run_once(claim=False)
    assert ProcessedEvent.objects.filter(consumer="product_stats", event_id=fields["id"]).count() == 1
    assert EventLog.objects.filter(event_id=fields["id"]).count() == 1  # event_log skipped the copy
    assert staff_client.get("/api/staff/health/").json()["dead_letters"][0]["retried_at"] is not None


def test_retry_of_an_unknown_entry_is_404(staff_client, events_redis):
    assert staff_client.post("/api/staff/dead-letters/999-0/retry/").status_code == 404
    assert staff_client.post("/api/staff/dead-letters/not-an-id/retry/").status_code == 404


# --- retention ------------------------------------------------------------------------------------


def test_purge_keeps_the_explorer_history_for_90_days_and_the_outbox_for_7():
    from datetime import timedelta

    from django.utils import timezone

    from apps.events.models import OutboxEvent
    from apps.events.tasks import purge_old_events

    now = timezone.now()

    def logged(age_days):
        row = EventLog.objects.create(
            event_id=uuid.uuid4(), type="OrderPlaced", aggregate_type="order", aggregate_id="a" * 32,
            stream="events:order", payload={}, occurred_at=now,
        )
        EventLog.objects.filter(pk=row.pk).update(received_at=now - timedelta(days=age_days))
        ProcessedEvent.objects.create(consumer="event_log", event_id=row.event_id)
        ProcessedEvent.objects.filter(event_id=row.event_id).update(processed_at=now - timedelta(days=age_days))

    logged(10)  # older than the outbox's 7 days, still within the explorer's 90
    logged(91)
    OutboxEvent.objects.create(event_type="OrderPlaced", aggregate_type="order", aggregate_id="a" * 32,
                               payload={}, published_at=now - timedelta(days=8))

    assert purge_old_events() == {"outbox": 1, "processed": 1, "event_log": 1}
    assert EventLog.objects.count() == ProcessedEvent.objects.count() == 1


# --- dead consumer names -------------------------------------------------------------------------


def test_dead_consumer_names_are_pruned_on_start_but_not_while_they_own_pending_entries(events_redis):
    import time

    events_redis.xadd(stream_name("order"), entry())
    old = started(EventLogConsumer, events_redis, name="old-host-1")
    old.run_once(claim=False)  # processed + acked: nothing pending
    events_redis.xadd(stream_name("order"), entry())
    events_redis.xreadgroup("event_log", "crashed-host-1", {stream_name("order"): ">"}, count=1)  # never acked
    time.sleep(0.4)  # both idle past EVENTS_CONSUMER_PRUNE_IDLE_MS (300 ms in tests)

    started(EventLogConsumer, events_redis, name="new-host-1")  # a restart: ensure_groups prunes

    names = {c["name"]: c["pending"] for c in events_redis.xinfo_consumers(stream_name("order"), "event_log")}
    assert "old-host-1" not in names
    assert names["crashed-host-1"] == 1  # its pending entry stays claimable by XAUTOCLAIM


def test_health_counts_only_active_consumers(staff_client, events_redis):
    import time

    started(EventLogConsumer, events_redis, name="gone-1").run_once(claim=False)
    events_redis.xadd(stream_name("order"), entry())
    events_redis.xreadgroup("event_log", "gone-2", {stream_name("order"): ">"}, count=1)  # pending
    time.sleep(0.4)
    live = EventLogConsumer(events_redis, consumer_name="live-1")
    live.run_once(claim=False)  # a read attempt just now

    groups = {(g["stream"], g["group"]): g for g in staff_client.get("/api/staff/health/").json()["groups"]}
    row = groups[(stream_name("order"), "event_log")]
    assert (row["consumers"], row["inactive_consumers"]) == (1, 2)
