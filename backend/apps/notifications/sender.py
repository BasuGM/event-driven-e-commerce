"""Sends pending notifications. Separate from the consumer on purpose: SMTP is slow and can
fail, and an email can't be rolled back, so it must never happen inside the consumer's
transaction.

One row per transaction, locked with SKIP LOCKED (two senders never pick the same row). The
row is marked sent in the same transaction as the send. The one unavoidable gap: if the
process dies after the SMTP server accepted the message but before the commit, the row is
still pending and the email goes out again. The Message-ID is deterministic, so a client or
Mailpit can recognise the duplicate.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from .models import Notification

logger = logging.getLogger(__name__)

BASE_BACKOFF = 30  # seconds; doubles per attempt
MAX_BACKOFF = 3600


def message_id(notification: Notification) -> str:
    return f"<notification-{notification.pk}@olist-commerce.local>"


def send_one(notification_id: int, *, now=None) -> str:
    """Send one due, pending notification. Returns "sent", "retry", "failed" or "skipped"."""
    now = now or timezone.now()
    with transaction.atomic():
        notification = (
            Notification.objects.select_for_update(skip_locked=True)
            .filter(pk=notification_id, status=Notification.Status.PENDING, next_attempt_at__lte=now)
            .first()
        )
        if notification is None:
            return "skipped"  # already sent, not due yet, or another sender has it
        notification.attempts += 1
        try:
            email = EmailMultiAlternatives(
                notification.subject, notification.body_text, settings.DEFAULT_FROM_EMAIL,
                [notification.recipient], headers={"Message-ID": message_id(notification)},
            )
            email.attach_alternative(notification.body_html, "text/html")
            email.send()
        except Exception as exc:  # noqa: BLE001 - any SMTP/network failure is retried
            notification.last_error = f"{type(exc).__name__}: {exc}"[:2000]
            if notification.attempts >= settings.NOTIFICATION_MAX_ATTEMPTS:
                notification.status = Notification.Status.FAILED
                logger.error("Notification %s failed for good: %s", notification.pk, notification.last_error)
                result = "failed"
            else:
                delay = min(MAX_BACKOFF, BASE_BACKOFF * 2 ** (notification.attempts - 1))
                notification.next_attempt_at = now + timedelta(seconds=delay)
                logger.warning("Notification %s: %s; retry in %ss", notification.pk, notification.last_error, delay)
                result = "retry"
            notification.save(update_fields=["attempts", "last_error", "status", "next_attempt_at"])
            return result
        notification.status, notification.sent_at = Notification.Status.SENT, now
        notification.save(update_fields=["attempts", "status", "sent_at"])
        return "sent"


def send_due(*, now=None, limit: int = 100) -> dict[str, int]:
    now = now or timezone.now()
    ids = list(
        Notification.objects.filter(status=Notification.Status.PENDING, next_attempt_at__lte=now)
        .order_by("next_attempt_at", "id").values_list("id", flat=True)[:limit]
    )
    counts: dict[str, int] = {}
    for pk in ids:
        result = send_one(pk, now=now)
        counts[result] = counts.get(result, 0) + 1
    return counts
