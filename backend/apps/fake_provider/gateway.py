"""FakeGateway: a Stripe-shaped provider that lives in this codebase (dev/test only)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from django.conf import settings

from apps.payments.gateway import PAYMENT_FAILED, PAYMENT_SUCCEEDED, ProviderPayment, WebhookEvent
from apps.payments.signature import verify

from .models import FakeIntent, new_id

SIGNATURE_HEADER = "Fake-Signature"
TYPES = {"payment_intent.succeeded": PAYMENT_SUCCEEDED, "payment_intent.payment_failed": PAYMENT_FAILED}


class FakeGateway:
    name = "fake"

    def create_payment(
        self, *, amount: Decimal, currency: str, reference: str, return_url: str, expires_at, idempotency_key: str
    ) -> ProviderPayment:
        intent, _ = FakeIntent.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                "id": new_id("pi"), "amount": amount, "currency": currency, "reference": reference,
                "return_url": return_url, "expires_at": expires_at,
            },
        )
        # Served through the Next /api proxy, so one relative URL works for every browser
        return ProviderPayment(id=intent.id, redirect_url=f"/api/fake-provider/pay/{intent.id}/", status=intent.status)

    def parse_webhook(self, raw_body: bytes, headers) -> WebhookEvent:
        verify(
            headers.get(SIGNATURE_HEADER), raw_body, settings.PAYMENT_WEBHOOK_SECRET,
            tolerance=settings.PAYMENT_WEBHOOK_TOLERANCE_SECONDS,
        )
        data = json.loads(raw_body)  # only after the signature checked out
        payment = data["data"]["object"]
        return WebhookEvent(
            id=data["id"],
            type=TYPES.get(data["type"], data["type"]),
            created=datetime.fromtimestamp(data["created"], UTC),
            payment_id=payment.get("id"),
            raw_type=data["type"],
            payload=data,
        )
