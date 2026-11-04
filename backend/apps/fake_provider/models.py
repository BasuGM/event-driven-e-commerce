"""The fake provider's own records: what Stripe would keep on its side. Dev/test only."""

import secrets

from django.db import models


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


class FakeIntent(models.Model):
    class Status(models.TextChoices):
        REQUIRES_PAYMENT = "requires_payment"
        SUCCEEDED = "succeeded"
        FAILED = "failed"

    id = models.CharField(primary_key=True, max_length=40)
    idempotency_key = models.CharField(max_length=255, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    reference = models.CharField(max_length=64, help_text="The merchant's order id")
    return_url = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUIRES_PAYMENT)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.id


class FakeEvent(models.Model):
    id = models.CharField(primary_key=True, max_length=40)
    intent = models.ForeignKey(FakeIntent, on_delete=models.CASCADE, related_name="events")
    type = models.CharField(max_length=64)
    created_at = models.DateTimeField()
    body = models.TextField(help_text="The exact JSON bytes delivered (and signed)")
    delivery_attempts = models.PositiveIntegerField(default=0)
    last_status = models.PositiveSmallIntegerField(null=True, blank=True)
    last_delivered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.id} {self.type}"
