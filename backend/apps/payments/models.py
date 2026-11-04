from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.orders.models import Order

MONEY = {"max_digits": 12, "decimal_places": 2}


class PaymentIntent(models.Model):
    """A payment at the provider, from creation to success/failure (the provider lifecycle).

    Not to be confused with ``orders.Payment``: that's the settled-payment ledger (Olist's
    shape), written by ``services.pay()`` once an order is actually paid.
    """

    class Status(models.TextChoices):
        REQUIRES_PAYMENT = "requires_payment"
        # The customer came back from the provider's page; its webhook hasn't arrived yet.
        # UI state only: the webhook still decides the outcome.
        PROCESSING = "processing"
        SUCCEEDED = "succeeded"
        FAILED = "failed"

    OPEN_STATUSES = (Status.REQUIRES_PAYMENT, Status.PROCESSING)

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payment_intents")
    provider = models.CharField(max_length=32)
    provider_payment_id = models.CharField(max_length=64, unique=True)
    amount = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=3, default="BRL")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUIRES_PAYMENT)
    # Money arrived for an order we can no longer fulfil (paid after cancel/expiry). There is no
    # refund logic yet: the flag (admin filter) and a PaymentRefundDue event are the hand-off.
    needs_refund = models.BooleanField(default=False, db_index=True)
    refund_reason = models.CharField(max_length=200, blank=True, default="")
    last_event_at = models.DateTimeField(null=True, blank=True)
    redirect_url = models.CharField(max_length=500, blank=True, default="")
    returned_at = models.DateTimeField(null=True, blank=True, help_text="Customer back from the provider's page")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Two "Pay" clicks reuse one open intent instead of creating a second
            models.UniqueConstraint(
                fields=["order"], condition=Q(status__in=["requires_payment", "processing"]),
                name="uniq_open_intent_per_order",
            )
        ]

    def __str__(self) -> str:
        return f"{self.provider_payment_id} ({self.status})"

    @property
    def overdue_at(self):
        """When "processing" stops blocking Pay (the webhook may never come)."""
        if self.status != self.Status.PROCESSING or self.returned_at is None:
            return None
        return self.returned_at + timedelta(seconds=settings.PAYMENT_CONFIRMATION_TIMEOUT_SECONDS)

    def confirmation_overdue(self, now=None) -> bool:
        overdue_at = self.overdue_at
        return overdue_at is not None and (now or timezone.now()) >= overdue_at

    def awaiting_webhook(self, now=None) -> bool:
        """Processing and still within the window: Pay stays hidden."""
        return self.status == self.Status.PROCESSING and not self.confirmation_overdue(now)


class ProviderEvent(models.Model):
    """Every webhook event we accepted, once: the unique key is our idempotency guard."""

    class Outcome(models.TextChoices):
        APPLIED = "applied"  # moved the payment and/or the order
        IGNORED_STALE = "ignored_stale"  # older than what we already applied (e.g. fail after success)
        REFUND_FLAGGED = "refund_flagged"  # money for an order that's no longer payable
        NO_CHANGE = "no_change"  # nothing to do (already in that state, or a type we don't use)

    provider = models.CharField(max_length=32)
    provider_event_id = models.CharField(max_length=64)
    type = models.CharField(max_length=64)
    payment_intent = models.ForeignKey(
        PaymentIntent, null=True, blank=True, on_delete=models.SET_NULL, related_name="events"
    )
    payload = models.JSONField()
    created_at = models.DateTimeField(help_text="When the provider created the event")
    received_at = models.DateTimeField(auto_now_add=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "provider_event_id"], name="uniq_provider_event")
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.provider_event_id} {self.type}"
