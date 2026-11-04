from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """An email to send, written by the notifications consumer in its transaction and sent
    later by the sender (never inside the consumer's transaction).

    Unique on (event_id, kind): however often an event is delivered or replayed, there is one
    row, so at most one email.
    """

    class Kind(models.TextChoices):
        ORDER_PLACED = "order_placed"
        ORDER_PAID = "order_paid"
        PAYMENT_FAILED = "payment_failed"
        ORDER_CANCELED = "order_canceled"
        RESERVATION_EXPIRED = "reservation_expired"
        REFUND_DUE = "refund_due"

    class Status(models.TextChoices):
        PENDING = "pending"
        SENT = "sent"
        FAILED = "failed"  # gave up after NOTIFICATION_MAX_ATTEMPTS

    event_id = models.UUIDField()
    kind = models.CharField(max_length=32, choices=Kind.choices)
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    recipient = models.EmailField()
    # Rendered when the row is created: the sender stays trivial, a retry sends the same bytes
    subject = models.CharField(max_length=200)
    body_text = models.TextField()
    body_html = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    last_error = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event_id", "kind"], name="uniq_notification_event_kind")]
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="notification_due_idx")]

    def __str__(self) -> str:
        return f"{self.kind} -> {self.recipient} ({self.status})"
