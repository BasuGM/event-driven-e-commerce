from django.conf import settings
from django.db import models


class IdempotencyKey(models.Model):
    """Remembers the outcome of an unsafe request so a retry with the same key replays it.

    Scoped per user (two users may send the same UUID). Only successful outcomes are stored:
    failed attempts roll back with no side effects, so re-running them is safe.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "key"], name="uniq_idempotency_user_key")]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.key}"
