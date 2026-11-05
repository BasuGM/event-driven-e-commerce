import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class OutboxEvent(models.Model):
    """A domain event, written in the same transaction as the state change it describes.

    The relay publishes unpublished rows to Redis Streams and stamps ``published_at``. If the
    business transaction rolls back, the row never existed, so nothing is ever published for a
    change that didn't happen.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=64)
    aggregate_type = models.CharField(max_length=32)
    aggregate_id = models.CharField(max_length=64)
    schema_version = models.PositiveSmallIntegerField(default=1)
    payload = models.JSONField()
    occurred_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            # The relay's query (unpublished, oldest first) stays an index scan however large
            # the table grows: published rows aren't in this index at all.
            models.Index(
                fields=["occurred_at", "id"],
                condition=Q(published_at__isnull=True),
                name="outbox_unpublished_idx",
            ),
            models.Index(fields=["aggregate_type", "aggregate_id"], name="outbox_aggregate_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.aggregate_type}:{self.aggregate_id}"


class ProcessedEvent(models.Model):
    """One row per (consumer, event) the consumer has applied: its idempotency record.

    Written in the same transaction as the consumer's side effects, so "applied" and
    "recorded as applied" can never disagree.
    """

    consumer = models.CharField(max_length=64)
    event_id = models.UUIDField()
    processed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["consumer", "event_id"], name="uniq_processed_event")
        ]

    def __str__(self) -> str:
        return f"{self.consumer}:{self.event_id}"


class EventLog(models.Model):
    """Durable history of every event, written by the event_log consumer. The outbox is a
    delivery buffer purged after a week; this is what the staff explorer reads (kept
    EVENT_LOG_RETENTION_DAYS)."""

    event_id = models.UUIDField(unique=True)
    type = models.CharField(max_length=64)
    aggregate_type = models.CharField(max_length=32)
    aggregate_id = models.CharField(max_length=64)
    stream = models.CharField(max_length=64)
    schema_version = models.PositiveSmallIntegerField(default=1)
    payload = models.JSONField()
    occurred_at = models.DateTimeField(help_text="When the event was recorded (outbox)")
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["type", "received_at"], name="eventlog_type_idx"),
            models.Index(fields=["aggregate_id", "occurred_at"], name="eventlog_aggregate_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.aggregate_type}:{self.aggregate_id}"


class DeadLetterRetry(models.Model):
    """A staff retry of a dead-lettered stream entry: one per DLQ entry, so retrying twice
    re-delivers once (and who did it is recorded)."""

    dlq_entry_id = models.CharField(max_length=40, unique=True)
    event_id = models.CharField(max_length=40)
    consumer = models.CharField(max_length=64)
    stream = models.CharField(max_length=64)
    new_entry_id = models.CharField(max_length=40)
    retried_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    retried_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.dlq_entry_id} -> {self.new_entry_id}"
