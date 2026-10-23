"""Outbox relay: copies unpublished OutboxEvent rows into Redis Streams.

One batch = one transaction:

1. lock up to N unpublished rows, oldest first, with ``FOR UPDATE SKIP LOCKED`` (a second relay
   skips rows this one holds and takes the next ones, so two relays never send the same row);
2. XADD them one by one, stopping at the first Redis error (never skip ahead of a failed row);
3. stamp ``published_at`` on what was sent; record ``attempts``/``last_error`` on the failed row;
4. commit, which releases the locks.

A crash between XADD and the commit leaves the rows unpublished, so they're sent again: a
duplicate, which consumers dedupe by event id. That's the at-least-once trade-off.
"""

from __future__ import annotations

import logging
import random
import threading
from dataclasses import dataclass

import redis
from django.conf import settings
from django.db import DatabaseError, close_old_connections, transaction
from django.db.models import F
from django.utils import timezone

from .models import OutboxEvent
from .readiness import missing_event_tables, wait_for_event_tables
from .streams import entry_fields, redis_client, stream_name

logger = logging.getLogger(__name__)

IDLE_SLEEP = 0.5
MAX_BACKOFF = 30.0


@dataclass
class BatchResult:
    selected: int
    published: int
    error: Exception | None = None


def publish_batch(client: redis.Redis | None = None, *, batch_size: int | None = None) -> BatchResult:
    client = client or redis_client()
    batch_size = batch_size or settings.RELAY_BATCH_SIZE
    with transaction.atomic():
        rows = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(published_at__isnull=True)
            .order_by("occurred_at", "id")[:batch_size]
        )
        published, error = [], None
        for row in rows:
            try:
                client.xadd(
                    stream_name(row.aggregate_type),
                    entry_fields(row),
                    maxlen=settings.EVENTS_STREAM_MAXLEN,
                    approximate=True,
                )
            except redis.RedisError as exc:  # includes ConnectionError and TimeoutError
                error = exc
                OutboxEvent.objects.filter(pk=row.pk).update(
                    attempts=F("attempts") + 1, last_error=f"{type(exc).__name__}: {exc}"[:2000]
                )
                break
            published.append(row.pk)
        if published:
            OutboxEvent.objects.filter(pk__in=published).update(published_at=timezone.now())
    return BatchResult(selected=len(rows), published=len(published), error=error)


def run_relay(stop: threading.Event, *, client: redis.Redis | None = None) -> None:
    """Loop until ``stop`` is set. Full batches loop straight away; an empty outbox polls every
    IDLE_SLEEP; Redis or database errors back off exponentially (with jitter, capped)."""
    client = client or redis_client()
    failures = 0
    if not wait_for_event_tables(stop, who="Relay"):
        return
    logger.info("Outbox relay started")
    while not stop.is_set():
        close_old_connections()
        try:
            result = publish_batch(client)
        except DatabaseError:
            if missing_event_tables():  # schema dropped under us (make reset): wait, quietly
                if not wait_for_event_tables(stop, who="Relay"):
                    break
                continue
            logger.exception("Relay: database error")
            result = BatchResult(selected=0, published=0, error=DatabaseError("database error"))
        if result.published:
            logger.info("Relay: published %d event(s)", result.published)
        if result.error is not None:
            failures += 1
            delay = min(MAX_BACKOFF, 0.5 * 2 ** (failures - 1)) * random.uniform(0.8, 1.2)
            logger.warning("Relay: %s; retrying in %.1fs", result.error, delay)
            stop.wait(delay)
            continue
        failures = 0
        if result.selected < settings.RELAY_BATCH_SIZE:
            stop.wait(IDLE_SLEEP)
    logger.info("Outbox relay stopped")
