import logging

from celery import shared_task

from .services import release_expired

logger = logging.getLogger(__name__)


@shared_task
def release_expired_reservations() -> int:
    """Beat runs this every minute. Loops in batches until nothing expired is left."""
    total = 0
    while released := release_expired(limit=100):
        total += released
        if released < 100:
            break
    if total:
        logger.info("Released reservations for %d expired order(s)", total)
    return total
