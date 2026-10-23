import uuid

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
