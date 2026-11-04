import logging

from celery import shared_task

from .models import FakeEvent
from .provider import deliver

logger = logging.getLogger(__name__)

MAX_RETRIES = 6


@shared_task(bind=True, max_retries=MAX_RETRIES)
def deliver_event(self, event_id: str) -> int:
    """Deliver one webhook; a non-2xx (or no connection) is retried with backoff, like a real
    provider. Retries are another way the merchant can see the same event twice."""
    status = deliver(FakeEvent.objects.get(pk=event_id))
    if not 200 <= status < 300:
        countdown = min(300, 5 * 2**self.request.retries)
        logger.warning("Fake provider: webhook %s got %s, retrying in %ss", event_id, status, countdown)
        raise self.retry(countdown=countdown)
    return status
