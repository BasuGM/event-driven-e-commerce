"""Consumer framework: Redis consumer groups with effectively-once processing.

Delivery is at-least-once (the relay may send an event twice; a crash before XACK redelivers
it). Each consumer makes that effectively-once with a ProcessedEvent row, written in the same
transaction as its side effects:

    BEGIN; INSERT ProcessedEvent ... ON CONFLICT DO NOTHING  -- 0 rows: seen it, skip
           handle(event)                                     -- side effects
    COMMIT; XACK                                             -- ack only after commit

A crash after COMMIT but before XACK redelivers the entry; the INSERT then finds the row and
the handler isn't run again. A handler that raises rolls back (no ProcessedEvent row), leaves
the entry pending, and it is reclaimed with XAUTOCLAIM after EVENTS_CLAIM_IDLE_MS (natural
backoff). After EVENTS_MAX_DELIVERIES attempts it goes to the dead-letter stream and is acked,
so one poison event can't block the group.

Handlers must be state-based (recompute from the database), not deltas: events aren't
guaranteed to arrive in order when more than one relay runs.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time

import redis
from django.conf import settings
from django.db import close_old_connections, connection, transaction

from .streams import Event, dlq_stream, redis_client, stream_name

logger = logging.getLogger(__name__)

READ_COUNT = 10
CLAIM_INTERVAL = 30.0  # seconds between XAUTOCLAIM sweeps


class Consumer:
    name: str = ""  # the consumer group; also the ProcessedEvent.consumer value
    streams: tuple[str, ...] = ()  # aggregate types, e.g. ("order",) -> events:order
    event_types: frozenset[str] = frozenset()

    def __init__(self, client: redis.Redis | None = None, *, consumer_name: str | None = None):
        self.client = client or redis_client()
        self.me = consumer_name or f"{socket.gethostname()}-{os.getpid()}"
        self.last_errors: dict[str, str] = {}  # entry id -> last handler error (for the DLQ)
        self._last_claim: float | None = None

    def handle(self, event: Event) -> None:
        """Apply the event. Runs inside the transaction that also records ProcessedEvent."""
        raise NotImplementedError

    # --- setup -----------------------------------------------------------------------------

    @property
    def stream_keys(self) -> list[str]:
        return [stream_name(s) for s in self.streams]

    def ensure_groups(self) -> None:
        # From id 0: a new group processes the stream's whole history (ProcessedEvent dedupes)
        for key in self.stream_keys:
            try:
                self.client.xgroup_create(key, self.name, id="0", mkstream=True)
            except redis.ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise

    # --- one iteration ---------------------------------------------------------------------

    def run_once(self, *, block_ms: int | None = None, claim: bool | None = None) -> int:
        """Reclaim stuck entries (every CLAIM_INTERVAL, or when ``claim``), then read new ones.
        Returns how many entries were looked at."""
        seen = 0
        now = time.monotonic()
        if claim or (claim is None and (self._last_claim is None or now - self._last_claim >= CLAIM_INTERVAL)):
            self._last_claim = now
            for key in self.stream_keys:
                seen += self._reclaim(key)
        response = self.client.xreadgroup(
            self.name,
            self.me,
            {key: ">" for key in self.stream_keys},
            count=READ_COUNT,
            block=settings.EVENTS_BLOCK_MS if block_ms is None else block_ms,
        )
        for key, entries in response or []:
            for entry_id, fields in entries:
                self._process(key, entry_id, fields, deliveries=1)
                seen += 1
        return seen

    def _reclaim(self, key: str) -> int:
        seen, start = 0, "0-0"
        while True:
            result = self.client.xautoclaim(
                key, self.name, self.me,
                min_idle_time=settings.EVENTS_CLAIM_IDLE_MS, start_id=start, count=READ_COUNT,
            )
            start, entries = result[0], result[1]
            for entry_id, fields in entries:
                pending = self.client.xpending_range(key, self.name, min=entry_id, max=entry_id, count=1)
                deliveries = pending[0]["times_delivered"] if pending else 1
                self._process(key, entry_id, fields, deliveries=deliveries)
                seen += 1
            if start == "0-0" or not entries:
                return seen

    def _process(self, key: str, entry_id: str, fields: dict | None, *, deliveries: int) -> None:
        if not fields:  # trimmed/deleted while pending: nothing to process
            self._ack(key, entry_id)
            return
        if deliveries > settings.EVENTS_MAX_DELIVERIES:
            self._dead_letter(key, entry_id, fields, deliveries)
            return
        if fields.get("type") not in self.event_types:
            self._ack(key, entry_id)  # not ours: no ProcessedEvent row, no transaction
            return
        try:
            event = Event.from_fields(fields)
            with transaction.atomic():
                if self._mark_processed(event.id):
                    self.handle(event)
        except Exception as exc:  # noqa: BLE001 - any failure leaves the entry pending
            self.last_errors[entry_id] = f"{type(exc).__name__}: {exc}"[:2000]
            logger.exception("%s: event %s failed (delivery %d)", self.name, entry_id, deliveries)
            return
        self._ack(key, entry_id)
        self.last_errors.pop(entry_id, None)

    def _mark_processed(self, event_id: str) -> bool:
        """Insert the idempotency row; False if this consumer already applied the event.
        A concurrent duplicate waits on the unique index, then sees the committed row."""
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO events_processedevent (consumer, event_id, processed_at) "
                "VALUES (%s, %s, now()) ON CONFLICT (consumer, event_id) DO NOTHING RETURNING id",
                [self.name, event_id],
            )
            return cursor.fetchone() is not None

    def _ack(self, key: str, entry_id: str) -> None:
        self.client.xack(key, self.name, entry_id)

    def _dead_letter(self, key: str, entry_id: str, fields: dict, deliveries: int) -> None:
        error = self.last_errors.pop(entry_id, "unknown (last attempt ran on another consumer)")
        self.client.xadd(
            dlq_stream(),
            {
                **fields,
                "dlq_consumer": self.name,
                "dlq_stream": key,
                "dlq_entry_id": entry_id,
                "dlq_deliveries": str(deliveries),
                "dlq_error": error,
            },
            maxlen=settings.EVENTS_STREAM_MAXLEN,
            approximate=True,
        )
        self._ack(key, entry_id)
        logger.error(
            "%s: event %s (%s) moved to %s after %d deliveries: %s",
            self.name, fields.get("id"), fields.get("type"), dlq_stream(), deliveries, error,
        )

    # --- long-running loop -----------------------------------------------------------------

    def run(self, stop: threading.Event) -> None:
        logger.info("Consumer %s (%s) started on %s", self.name, self.me, ", ".join(self.stream_keys))
        failures = 0
        while not stop.is_set():
            try:
                if failures or self._last_claim is None:
                    self.ensure_groups()  # also recreates groups after a Redis restart
                close_old_connections()
                self.run_once()
                failures = 0
            except (redis.RedisError, OSError):
                failures += 1
                delay = min(30.0, 0.5 * 2 ** (failures - 1))
                logger.exception("Consumer %s: Redis error; retrying in %.1fs", self.name, delay)
                stop.wait(delay)
        logger.info("Consumer %s stopped", self.name)
