"""Order emails. Writes a pending Notification in the consumer's transaction; the sender
(Celery) sends it after commit. Email never happens inside this transaction."""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.notifications.models import Notification
from apps.notifications.rendering import render
from apps.orders import events as order_events
from apps.orders.models import Order
from apps.payments.services import PAYMENT_REFUND_DUE

from ..consumer import Consumer
from ..streams import Event

logger = logging.getLogger(__name__)

KINDS = {
    order_events.ORDER_PLACED: Notification.Kind.ORDER_PLACED,
    order_events.ORDER_PAID: Notification.Kind.ORDER_PAID,
    order_events.PAYMENT_FAILED: Notification.Kind.PAYMENT_FAILED,
    order_events.ORDER_CANCELED: Notification.Kind.ORDER_CANCELED,
    order_events.RESERVATION_EXPIRED: Notification.Kind.RESERVATION_EXPIRED,
    PAYMENT_REFUND_DUE: Notification.Kind.REFUND_DUE,
}


class NotificationsConsumer(Consumer):
    name = "notifications"
    streams = ("order",)
    event_types = frozenset(KINDS)

    def handle(self, event: Event) -> None:
        payload = event.payload
        user = get_user_model().objects.filter(pk=payload.get("user_id")).first()
        if user is None or not user.email:
            logger.info("notifications: no email for event %s (user %s), skipped", event.id, payload.get("user_id"))
            return
        kind = KINDS[event.type]
        subject, text, html = render(kind, payload, recipient_name=user.display_name)
        try:
            # Second guard behind ProcessedEvent: a replay under a new consumer group, or after
            # ProcessedEvent rows were purged, still finds this row and adds no second email.
            with transaction.atomic():
                notification = Notification.objects.create(
                    event_id=event.id, kind=kind, recipient=user.email,
                    order=Order.objects.filter(external_id=payload["order_id"]).first(),
                    subject=subject, body_text=text, body_html=html,
                )
        except IntegrityError:
            return
        transaction.on_commit(lambda: _enqueue(notification.pk), robust=True)


def _enqueue(notification_id: int) -> None:
    from apps.notifications.tasks import send_notification

    # If the broker is down this raises (robust=True logs it): the beat sweep sends it later
    send_notification.delay(notification_id)
