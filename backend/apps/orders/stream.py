"""GET /api/orders/<id>/stream/: Server-Sent Events for one order, served by the ASGI `stream`
service (uvicorn). An open stream is an idle coroutine, not a worker thread.

    retry: <ms>                              EventSource reconnect delay
    id: <version>  event: snapshot  data: {…}   the current state, read from the database
    : heartbeat                              every ORDER_STREAM_HEARTBEAT_SECONDS
    event: end                               final state reached: the client stops

The snapshot is read and sent on connect, after subscribing (unless the client's Last-Event-ID
is already that version)
and again whenever a signal arrives and the version changed. The stream closes after
ORDER_STREAM_MAX_SECONDS; EventSource then reconnects by itself.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime

import redis
import redis.asyncio as aioredis
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.handlers.asgi import ASGIRequest
from django.db import connection
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone

from .live import channel_name, is_final, read_snapshot

logger = logging.getLogger(__name__)


def _read_and_close(user, order_id: str) -> dict | None:
    """Runs on the thread pool (thread_sensitive=False), so concurrent streams don't queue on
    Django's single thread-sensitive thread. DB connections are per thread: close this one,
    or a long-lived stream would leave pool threads holding connections."""
    try:
        return read_snapshot(user, order_id)
    finally:
        connection.close()


read = sync_to_async(_read_and_close, thread_sensitive=False)


def _event(snapshot: dict) -> str:
    data = json.dumps(snapshot, separators=(",", ":"), default=str)
    return f"id: {snapshot['version']}\nevent: snapshot\ndata: {data}\n\n"


END = "event: end\ndata: {}\n\n"
HEARTBEAT = ": heartbeat\n\n"


def _seconds_until_overdue(snapshot: dict) -> float | None:
    """A processing payment turns overdue with no event: wake up then to send the new state."""
    overdue_at = (snapshot.get("payment") or {}).get("overdue_at")
    if not overdue_at or (snapshot.get("payment") or {}).get("confirmation_overdue"):
        return None
    return max(0.0, (datetime.fromisoformat(overdue_at) - timezone.now()).total_seconds())


async def order_stream(request, order_id: str):
    if not isinstance(request, ASGIRequest):
        # Under WSGI an async stream would be buffered whole and hold a worker for minutes
        return JsonResponse({"detail": "Served by the stream service (ASGI)."}, status=404)
    user = await request.auser()
    if not user.is_authenticated:
        return JsonResponse({"detail": "Authentication credentials were not provided."}, status=401)
    # Ownership check only (404 before any 200 is sent); the snapshot the client receives is
    # read again inside the stream, after subscribing.
    if await read(user, order_id) is None:  # someone else's order (or none): 404, like the order API
        return JsonResponse({"detail": "Not found."}, status=404)
    response = StreamingHttpResponse(
        event_stream(user, order_id, request.headers.get("Last-Event-ID")),
        content_type="text/event-stream",
    )
    # no-transform: Next's rewrite proxy runs `compression`, which would gzip and buffer the
    # stream otherwise. X-Accel-Buffering: nginx-style proxies must not buffer it either.
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    return response


async def event_stream(user, order_id: str, last_event_id: str | None) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + settings.ORDER_STREAM_MAX_SECONDS
    heartbeat = settings.ORDER_STREAM_HEARTBEAT_SECONDS
    yield f"retry: {settings.ORDER_STREAM_RETRY_MS}\n\n"

    client, pubsub = None, None
    try:
        try:
            client = aioredis.from_url(settings.EVENTS_REDIS_URL, socket_connect_timeout=2)
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            await pubsub.subscribe(channel_name(order_id))
            # Consume the subscribe confirmation now; otherwise the first get_message() returns
            # None at once and the loop would send a heartbeat right after the snapshot
            await pubsub.get_message(timeout=1)
        except (redis.RedisError, OSError):
            logger.warning("Order stream %s: Redis unavailable, polling the database", order_id)
            pubsub = None

        # Subscribe first, *then* read the snapshot we send. A change committed before the
        # subscription is in this read; one committed after it sends us a signal. (Reading
        # first would miss a change committed in between until the next signal.) A signal for
        # a change this read already includes is absorbed by the version check below.
        snapshot = await read(user, order_id)
        if snapshot is None:  # deleted (or no longer theirs) since the ownership check
            return
        if snapshot["version"] != last_event_id:  # a reconnect never replays what the client has
            yield _event(snapshot)
        if is_final(snapshot):
            yield END
            return

        while (remaining := deadline - loop.time()) > 0:
            overdue_in = _seconds_until_overdue(snapshot)
            timeout = min(heartbeat, remaining)
            if overdue_in is not None:
                timeout = min(timeout, overdue_in + 0.05)
            if pubsub is None:
                timeout = min(timeout, settings.ORDER_STREAM_FALLBACK_POLL_SECONDS)

            signalled = False
            if pubsub is not None:
                try:
                    signalled = await pubsub.get_message(timeout=timeout) is not None
                except (redis.RedisError, OSError):
                    logger.warning("Order stream %s: Redis lost, polling the database", order_id)
                    pubsub = None
                    continue
            else:
                await asyncio.sleep(timeout)

            due = overdue_in is not None and overdue_in <= timeout
            if signalled or pubsub is None or due:
                current = await read(user, order_id)
                if current is None:
                    return
                if current["version"] != snapshot["version"]:
                    snapshot = current
                    yield _event(snapshot)
                    if is_final(snapshot):
                        yield END
                        return
                    continue
            if not signalled:
                yield HEARTBEAT
    finally:
        # Runs on every exit: final state, timeout, error, and client disconnect (Django
        # cancels the response task when the ASGI server reports http.disconnect)
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception:  # noqa: BLE001 - best effort; the connection is closed below
                pass
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass
