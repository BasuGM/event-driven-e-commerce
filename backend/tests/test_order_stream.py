"""The live order stream (SSE): snapshot first, signals, heartbeats, cleanup, final state.

Runs the real async view with Django's AsyncClient under asyncio.run (no extra test plugin).
transaction=True: the view reads on thread-pool connections, which must see committed rows.
"""

import asyncio
import json
from datetime import timedelta

import pytest
import redis
from asgiref.sync import sync_to_async
from django.db import connection
from django.test import AsyncClient
from django.utils import timezone

from apps.orders.live import channel_name
from apps.orders.services import cancel, checkout
from apps.payments.services import mark_returned, start_payment

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def close_async_connections():
    """aforce_login/auser run on asgiref's thread-sensitive thread, which keeps its own DB
    connection (in production, Django's request signals close it). Close it after each test
    so the test database can be torn down."""
    yield
    # A lambda, so `connection` is looked up on that thread (not bound to the main thread's)
    asyncio.run(sync_to_async(lambda: connection.close())())


@pytest.fixture
def order_of(make_user, make_offer, fill_cart, address):
    def make(**offer):
        user = make_user()
        fill_cart(user, (make_offer(**offer), 1))
        return user, checkout(user, address)

    return make


def parse(chunks: list[str]) -> list[dict]:
    """SSE text -> [{"id":…, "event":…, "data":…} | {"comment":…} | {"retry":…}]"""
    events = []
    for block in "".join(chunks).split("\n\n"):
        if not block:
            continue
        if block.startswith(":"):
            events.append({"comment": block[1:].strip()})
            continue
        event = {}
        for line in block.split("\n"):
            key, _, value = line.partition(": ")
            event[key] = json.loads(value) if key == "data" else value
        events.append(event)
    return events


class Stream:
    """Reads a stream response in a background task, so a test can act while it's open and
    then cancel it the way Django does on a client disconnect."""

    def __init__(self, response):
        self.response, self.chunks = response, []
        self.task = asyncio.ensure_future(self._read())

    async def _read(self):
        async for chunk in self.response.streaming_content:
            self.chunks.append(chunk.decode())

    @property
    def events(self):
        return parse(self.chunks)

    def snapshots(self):
        return [e["data"] for e in self.events if e.get("event") == "snapshot"]

    async def wait_for(self, predicate, timeout=3.0):
        async with asyncio.timeout(timeout):
            while not predicate(self):
                await asyncio.sleep(0.02)

    async def disconnect(self):
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass


async def open_stream(user=None, order=None, *, last_event_id=None):
    client = AsyncClient()
    if user is not None:
        await client.aforce_login(user)
    headers = {"Last-Event-ID": last_event_id} if last_event_id else {}
    return await client.get(f"/api/orders/{order.external_id}/stream/", headers=headers)


def subscribers(order) -> int:
    from apps.events.streams import redis_client

    return dict(redis_client().pubsub_numsub(channel_name(order.external_id)))[channel_name(order.external_id)]


def publish(order):
    from apps.orders.live import publish_order_signal

    return publish_order_signal(order.external_id, "test")


def test_owner_gets_the_snapshot_first_then_a_new_one_on_a_signal(order_of):
    user, order = order_of()

    async def run():
        response = await open_stream(user, order)
        assert response.status_code == 200
        assert response["Content-Type"] == "text/event-stream"
        assert response["Cache-Control"] == "no-cache, no-transform"
        assert response["X-Accel-Buffering"] == "no"
        stream = Stream(response)
        await stream.wait_for(lambda s: s.snapshots())
        first = stream.events[:2]
        assert first[0] == {"retry": "3000"}
        assert first[1]["event"] == "snapshot" and first[1]["id"] == first[1]["data"]["version"]
        assert first[1]["data"]["status"] == "created" and first[1]["data"]["can_pay"] is True

        await stream.wait_for(lambda s: subscribers(order) == 1)
        await sync_to_async(publish)(order)  # a signal without a change: nothing new
        await asyncio.sleep(0.3)
        assert len(stream.snapshots()) == 1

        await sync_to_async(cancel)(order.pk)  # the change ...
        await sync_to_async(publish)(order)  # ... and its signal
        await stream.wait_for(lambda s: len(s.snapshots()) == 2)
        latest = stream.snapshots()[-1]
        assert latest["status"] == "canceled" and latest["version"] != first[1]["id"]
        await stream.wait_for(lambda s: s.task.done())  # final state: end event, stream closed
        assert stream.events[-1] == {"event": "end", "data": {}}

    asyncio.run(run())


def test_other_users_get_404_and_anonymous_401(order_of, make_user):
    _, order = order_of()

    async def run():
        assert (await open_stream(await sync_to_async(make_user)(), order)).status_code == 404
        assert (await open_stream(None, order)).status_code == 401

    asyncio.run(run())


def test_heartbeats_keep_the_connection_alive(order_of):
    user, order = order_of()

    async def run():
        stream = Stream(await open_stream(user, order))
        await stream.wait_for(lambda s: sum("comment" in e for e in s.events) >= 2)  # every 0.2 s in tests
        assert stream.events[2] == {"comment": "heartbeat"}  # not before the snapshot
        await stream.disconnect()

    asyncio.run(run())


def test_disconnect_unsubscribes(order_of):
    user, order = order_of()

    async def run():
        stream = Stream(await open_stream(user, order))
        await stream.wait_for(lambda s: subscribers(order) == 1)
        await stream.disconnect()
        await asyncio.sleep(0.1)
        assert subscribers(order) == 0

    asyncio.run(run())


def test_a_reconnect_with_the_current_version_does_not_replay_it(order_of):
    user, order = order_of()

    async def run():
        first = Stream(await open_stream(user, order))
        await first.wait_for(lambda s: s.snapshots())
        version = first.snapshots()[0]["version"]
        await first.disconnect()

        again = Stream(await open_stream(user, order, last_event_id=version))
        await again.wait_for(lambda s: any("comment" in e for e in s.events))
        assert again.snapshots() == []  # client already has this state
        await again.disconnect()

    asyncio.run(run())


def test_a_final_order_gets_one_snapshot_and_end(order_of):
    user, order = order_of()
    cancel(order.pk)

    async def run():
        stream = Stream(await open_stream(user, order))
        await stream.wait_for(lambda s: s.task.done())
        assert [e.get("event") for e in stream.events] == [None, "snapshot", "end"]

    asyncio.run(run())


def test_without_redis_it_polls_the_database(order_of, settings):
    settings.EVENTS_REDIS_URL = "redis://localhost:1/0"  # nothing listens there
    user, order = order_of()

    async def run():
        stream = Stream(await open_stream(user, order))
        await stream.wait_for(lambda s: s.snapshots())
        await sync_to_async(cancel)(order.pk)  # no signal at all: the poll finds it
        await stream.wait_for(lambda s: len(s.snapshots()) == 2)
        assert stream.snapshots()[-1]["status"] == "canceled"

    asyncio.run(run())


def test_processing_turns_overdue_without_a_signal(order_of, settings):
    settings.PAYMENT_CONFIRMATION_TIMEOUT_SECONDS = 0.6
    user, order = order_of()
    start_payment(order, return_url="/")
    mark_returned(order)

    async def run():
        stream = Stream(await open_stream(user, order))
        await stream.wait_for(lambda s: s.snapshots())
        first = stream.snapshots()[0]
        assert first["payment"]["status"] == "processing" and first["can_pay"] is False
        await stream.wait_for(lambda s: len(s.snapshots()) == 2, timeout=2)  # woken at overdue_at
        overdue = stream.snapshots()[-1]
        assert overdue["payment"]["confirmation_overdue"] is True and overdue["can_pay"] is True
        await stream.disconnect()

    asyncio.run(run())


def test_many_streams_leave_the_db_connection_count_stable(order_of):
    user, order = order_of()

    def connections() -> int:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
            return cursor.fetchone()[0]

    async def one_stream():
        stream = Stream(await open_stream(user, order))
        await stream.wait_for(lambda s: s.snapshots())
        await stream.disconnect()

    async def run(n):
        for _ in range(n):
            await one_stream()
        await asyncio.gather(*(one_stream() for _ in range(10)))  # concurrent ones too

    asyncio.run(run(2))  # warm-up: the session/auth thread opens its connection once
    before = connections()
    asyncio.run(run(20))
    assert connections() == before


def test_the_wsgi_backend_refuses_to_stream(order_of, client):
    """Under WSGI an async stream would be buffered whole and hold a worker for minutes."""
    user, order = order_of()
    client.force_login(user)
    response = client.get(f"/api/orders/{order.external_id}/stream/")
    assert response.status_code == 404


def test_a_change_committed_while_subscribing_is_not_missed(order_of, monkeypatch):
    """The first snapshot must be read *after* subscribing. A change committed between an
    earlier read and the subscription would otherwise go unnoticed until the next signal, a
    reconnect or the fallback poll (here: no signal is ever published)."""
    import redis.asyncio.client as aioredis_client

    user, order = order_of()
    real_subscribe = aioredis_client.PubSub.subscribe
    changed = []

    async def subscribe_after_a_change(self, *args, **kwargs):
        if not changed:  # the change lands just before the subscription takes effect
            changed.append(True)
            await sync_to_async(cancel)(order.pk)
        return await real_subscribe(self, *args, **kwargs)

    monkeypatch.setattr(aioredis_client.PubSub, "subscribe", subscribe_after_a_change)

    async def run():
        stream = Stream(await open_stream(user, order))
        await stream.wait_for(lambda s: s.snapshots() and s.snapshots()[-1]["status"] == "canceled")
        await stream.wait_for(lambda s: s.task.done())  # final: end event, stream closed
        assert stream.events[-1] == {"event": "end", "data": {}}
        assert changed

    asyncio.run(run())
