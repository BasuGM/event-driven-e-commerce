"""The payment provider interface. Everything provider-specific (API calls, webhook format and
signature) lives behind it; the rest of the app only sees these types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

PAYMENT_SUCCEEDED = "payment.succeeded"
PAYMENT_FAILED = "payment.failed"


@dataclass(frozen=True)
class ProviderPayment:
    id: str
    redirect_url: str  # where to send the customer to pay (the provider's hosted page)
    status: str


@dataclass(frozen=True)
class WebhookEvent:
    """A verified provider event, normalised. ``type`` is PAYMENT_SUCCEEDED, PAYMENT_FAILED or
    the provider's own type for events we don't act on."""

    id: str
    type: str
    created: datetime  # when the provider created it (i.e. when the payment happened)
    payment_id: str | None
    raw_type: str
    payload: dict = field(default_factory=dict)


class PaymentGateway(Protocol):
    name: str

    def create_payment(
        self, *, amount: Decimal, currency: str, reference: str, return_url: str,
        expires_at: datetime, idempotency_key: str,
    ) -> ProviderPayment:
        """Create (or, for the same idempotency key, return the existing) payment.
        May do network I/O: never call it inside a database transaction."""
        ...

    def parse_webhook(self, raw_body: bytes, headers) -> WebhookEvent:
        """Verify the signature over ``raw_body`` and parse it; raise InvalidSignature."""
        ...


def get_gateway() -> PaymentGateway:
    if settings.PAYMENT_PROVIDER == "fake":
        if not settings.ALLOW_FAKE_PAYMENTS:
            raise ImproperlyConfigured("PAYMENT_PROVIDER='fake' needs ALLOW_FAKE_PAYMENTS (dev/test only)")
        from apps.fake_provider.gateway import FakeGateway

        return FakeGateway()
    raise ImproperlyConfigured(f"Unknown PAYMENT_PROVIDER {settings.PAYMENT_PROVIDER!r}")


def payments_enabled() -> bool:
    return settings.PAYMENT_PROVIDER != "fake" or settings.ALLOW_FAKE_PAYMENTS
