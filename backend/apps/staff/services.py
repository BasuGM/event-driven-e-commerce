"""Read side of the event explorer (Redis + DB) and the dead-letter retry."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import redis
from django.conf import settings
from django.db import transaction

from apps.core.health import outbox_backlog
from apps.events.consumers import CONSUMERS
from apps.events.models import DeadLetterRetry, EventLog, ProcessedEvent
from apps.events.streams import dlq_stream, redis_client, stream_name

logger = logging.getLogger(__name__)

ENTRY_ID = re.compile(r"^\d{1,20}-\d{1,20}$")
DLQ_FIELDS = ("dlq_consumer", "dlq_stream", "dlq_entry_id", "dlq_deliveries", "dlq_error")
DLQ_LIMIT = 100


def consumers_for(event: EventLog) -> list[str]:
    """The registered consumers that should process this event (stream + type)."""
    return sorted(
        c.name for c in CONSUMERS.values() if event.aggregate_type in c.streams and event.type in c.event_types
    )


def order_timeline(order_id: str) -> list[dict]:
    events = list(EventLog.objects.filter(aggregate_id=order_id).order_by("occurred_at", "id"))
    processed: dict[tuple[str, str], datetime] = {
        (str(event_id), consumer): at
        for event_id, consumer, at in ProcessedEvent.objects.filter(
            event_id__in=[e.event_id for e in events]
        ).values_list("event_id", "consumer", "processed_at")
    }
    for event in events:
        event.consumers = [
            {"name": name, "processed_at": processed.get((str(event.event_id), name))}
            for name in consumers_for(event)
        ]
    return events


def group_health(client: redis.Redis) -> list[dict]:
    expected = sorted({(stream_name(s), c.name) for c in CONSUMERS.values() for s in c.streams})
    infos: dict[str, dict[str, dict]] = {}
    for key in {k for k, _ in expected}:
        try:
            infos[key] = {g["name"]: g for g in client.xinfo_groups(key)}
        except redis.ResponseError:  # the stream doesn't exist yet
            infos[key] = {}
    rows = []
    for key, group in expected:
        info = infos[key].get(group)
        active, inactive = _consumer_counts(client, key, group) if info else (0, 0)
        rows.append({
            "stream": key,
            "group": group,
            "exists": info is not None,
            "consumers": active,
            "inactive_consumers": inactive,
            "pending": info["pending"] if info else 0,
            "lag": info.get("lag") if info else None,
            "last_delivered_id": info["last-delivered-id"] if info else None,
        })
    return rows


def _consumer_counts(client: redis.Redis, key: str, group: str) -> tuple[int, int]:
    """(active, inactive): active = a read attempt within EVENTS_CONSUMER_ACTIVE_IDLE_MS (a live
    consumer polls every EVENTS_BLOCK_MS). Inactive names are leftovers from restarts that
    still own pending entries, or haven't been pruned yet."""
    consumers = client.xinfo_consumers(key, group)
    active = sum(1 for c in consumers if c["idle"] < settings.EVENTS_CONSUMER_ACTIVE_IDLE_MS)
    return active, len(consumers) - active


def dead_letters(client: redis.Redis) -> list[dict]:
    entries = client.xrevrange(dlq_stream(), count=DLQ_LIMIT)
    retried = dict(
        DeadLetterRetry.objects.filter(dlq_entry_id__in=[e for e, _ in entries]).values_list("dlq_entry_id", "retried_at")
    )
    return [
        {
            "entry_id": entry_id,
            "event_id": fields.get("id"),
            "type": fields.get("type"),
            "aggregate_id": fields.get("aggregate_id"),
            "consumer": fields.get("dlq_consumer"),
            "stream": fields.get("dlq_stream"),
            "deliveries": int(fields["dlq_deliveries"]) if fields.get("dlq_deliveries", "").isdigit() else None,
            "error": fields.get("dlq_error"),
            "retried_at": retried.get(entry_id),
        }
        for entry_id, fields in entries
    ]


def health() -> dict:
    client = redis_client()
    return {"groups": group_health(client), "outbox": outbox_backlog(), "dead_letters": dead_letters(client)}


class DeadLetterNotFound(Exception):
    pass


def retry_dead_letter(entry_id: str, *, user) -> tuple[DeadLetterRetry, bool]:
    """Put a dead-lettered event back on its stream, once.

    Every group on that stream sees the new entry. Groups that already processed the event
    find their ProcessedEvent row and just ack it; the consumer that dead-lettered it has no
    row (each failed attempt rolled back), so it is the one that applies it now. The unique
    DeadLetterRetry row makes a second retry of the same DLQ entry a no-op.
    """
    if not ENTRY_ID.match(entry_id):
        raise DeadLetterNotFound(entry_id)
    existing = DeadLetterRetry.objects.select_related("retried_by").filter(dlq_entry_id=entry_id).first()
    if existing is not None:
        return existing, False
    client = redis_client()
    entries = client.xrange(dlq_stream(), min=entry_id, max=entry_id)
    if not entries:
        raise DeadLetterNotFound(entry_id)
    fields = entries[0][1]
    original = {k: v for k, v in fields.items() if k not in DLQ_FIELDS}
    with transaction.atomic():
        # The unique row is the lock: a concurrent retry waits here, then sees it exists
        retry, created = DeadLetterRetry.objects.get_or_create(
            dlq_entry_id=entry_id,
            defaults={
                "event_id": fields.get("id", ""), "consumer": fields.get("dlq_consumer", ""),
                "stream": fields.get("dlq_stream", ""), "new_entry_id": "", "retried_by": user,
            },
        )
        if not created:
            return retry, False
        # XADD inside the transaction: if the commit then fails, the event may be delivered
        # again later, which the consumers' ProcessedEvent dedupe absorbs.
        retry.new_entry_id = client.xadd(retry.stream, original)
        retry.save(update_fields=["new_entry_id"])
    logger.info(
        "Dead letter %s (event %s, consumer %s) re-delivered to %s as %s by %s",
        entry_id, retry.event_id, retry.consumer, retry.stream, retry.new_entry_id, user.email,
    )
    return retry, True


def day_start(day) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)
