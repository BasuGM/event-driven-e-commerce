from celery import shared_task

from .sender import send_due, send_one


@shared_task
def send_notification(notification_id: int) -> str:
    """Enqueued right after the consumer commits (low latency)."""
    return send_one(notification_id)


@shared_task
def send_due_notifications() -> dict[str, int]:
    """Beat, every 30 s: retries, and anything whose enqueue was lost."""
    return send_due()
