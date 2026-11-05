from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import EventLog, OutboxEvent, ProcessedEvent


@shared_task
def purge_old_events() -> dict[str, int]:
    """Published outbox rows after EVENTS_RETENTION_DAYS (a delivery buffer); EventLog and
    ProcessedEvent rows after EVENT_LOG_RETENTION_DAYS (the explorer shows which consumers
    processed each logged event, so both are kept as long).

    Safe for dedupe: an entry is redelivered only while pending, and after
    EVENTS_MAX_DELIVERIES attempts it moves to the dead-letter stream, long before this.
    """
    now = timezone.now()
    outbox, _ = OutboxEvent.objects.filter(published_at__lt=now - timedelta(days=settings.EVENTS_RETENTION_DAYS)).delete()
    history = now - timedelta(days=settings.EVENT_LOG_RETENTION_DAYS)
    processed, _ = ProcessedEvent.objects.filter(processed_at__lt=history).delete()
    logged, _ = EventLog.objects.filter(received_at__lt=history).delete()
    return {"outbox": outbox, "processed": processed, "event_log": logged}
