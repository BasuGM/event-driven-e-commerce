"""What the fake provider does when the customer chooses on its hosted page, and how it
delivers webhooks: asynchronously (Celery), signed at send time, retried on failure, and on
request twice or out of order, so the merchant's idempotency is exercised for real."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.payments.signature import sign

from .gateway import SIGNATURE_HEADER
from .models import FakeEvent, FakeIntent, new_id

SUCCEED, FAIL, SUCCEED_LATER = "succeed", "fail", "succeed_later"
OUT_OF_ORDER_GAP = 3  # seconds between the two deliveries of the out-of-order scenario
DUPLICATE_GAP = 1


@dataclass(frozen=True)
class Delivery:
    event_id: str
    countdown: float  # seconds from now


class PaymentExpired(Exception):
    pass


def _event(intent: FakeIntent, event_type: str, created: datetime) -> FakeEvent:
    status = "succeeded" if event_type.endswith("succeeded") else "requires_payment"
    body = {
        "id": new_id("evt"),
        "object": "event",
        "type": event_type,
        "created": int(created.timestamp()),
        "data": {
            "object": {
                "id": intent.id,
                "object": "payment_intent",
                "amount": int(intent.amount * 100),  # minor units, like Stripe
                "currency": intent.currency.lower(),
                "status": status,
                "metadata": {"order_id": intent.reference},
            }
        },
    }
    return FakeEvent.objects.create(
        id=body["id"], intent=intent, type=event_type, created_at=created,
        body=json.dumps(body, separators=(",", ":")),
    )


def choose(
    intent: FakeIntent, choice: str, *, delay: float = 0, twice: bool = False, out_of_order: bool = False,
    now: datetime | None = None,
) -> list[Delivery]:
    """Record the customer's choice as provider events and schedule their deliveries.

    - succeed / fail: one event, delivered right away;
    - succeed_later: the payment happens now (event ``created`` = now), delivery waits ``delay``;
    - out_of_order: a decline (t-1s) then the success (t), delivered success first;
    - twice: every delivery is scheduled a second time.
    """
    now = now or timezone.now()
    if intent.expires_at is not None and now >= intent.expires_at:
        raise PaymentExpired(intent.id)
    deliveries: list[Delivery] = []
    with transaction.atomic():
        if choice == FAIL:
            intent.status = FakeIntent.Status.FAILED
            deliveries.append(Delivery(_event(intent, "payment_intent.payment_failed", now).id, 0))
        else:
            intent.status = FakeIntent.Status.SUCCEEDED
            wait = delay if choice == SUCCEED_LATER else 0
            if out_of_order:
                declined = _event(intent, "payment_intent.payment_failed", now - timedelta(seconds=1))
                succeeded = _event(intent, "payment_intent.succeeded", now)
                deliveries += [Delivery(succeeded.id, wait), Delivery(declined.id, wait + OUT_OF_ORDER_GAP)]
            else:
                deliveries.append(Delivery(_event(intent, "payment_intent.succeeded", now).id, wait))
        intent.save(update_fields=["status"])
        if twice:
            deliveries += [Delivery(d.event_id, d.countdown + DUPLICATE_GAP) for d in deliveries]
        transaction.on_commit(lambda: schedule(deliveries))
    return deliveries


def schedule(deliveries: list[Delivery]) -> None:
    from .tasks import deliver_event

    for delivery in deliveries:
        deliver_event.apply_async((delivery.event_id,), countdown=delivery.countdown)


def http_post(url: str, body: bytes, headers: dict) -> int:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError):
        return 0  # couldn't connect: retried like a 5xx


def deliver(event: FakeEvent, *, post=None) -> int:
    """POST one event to the merchant's webhook, signed now (a fresh timestamp per attempt,
    like Stripe). Returns the HTTP status (0 = no connection)."""
    body = event.body.encode()
    post = post or http_post  # looked up per call (not bound at definition), so it can be swapped
    status = post(
        f"{settings.BACKEND_INTERNAL_URL.rstrip('/')}/api/payments/webhook/",
        body,
        {"Content-Type": "application/json", SIGNATURE_HEADER: sign(settings.PAYMENT_WEBHOOK_SECRET, body)},
    )
    FakeEvent.objects.filter(pk=event.pk).update(
        delivery_attempts=F("delivery_attempts") + 1, last_status=status, last_delivered_at=timezone.now()
    )
    return status
