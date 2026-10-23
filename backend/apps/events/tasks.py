from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import OutboxEvent, ProcessedEvent


@shared_task
def purge_old_events() -> dict[str, int]:
    """Published outbox rows and ProcessedEvent rows older than EVENTS_RETENTION_DAYS.

    Safe for dedupe: an entry is redelivered only while pending, and after
    EVENTS_MAX_DELIVERIES attempts it moves to the dead-letter stream, long before this.
    """
    cutoff = timezone.now() - timedelta(days=settings.EVENTS_RETENTION_DAYS)
    outbox, _ = OutboxEvent.objects.filter(published_at__lt=cutoff).delete()
    processed, _ = ProcessedEvent.objects.filter(processed_at__lt=cutoff).delete()
    return {"outbox": outbox, "processed": processed}
