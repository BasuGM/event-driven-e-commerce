from celery import shared_task
from django.utils import timezone

from .models import IdempotencyKey


@shared_task
def purge_expired_idempotency_keys() -> int:
    deleted, _ = IdempotencyKey.objects.filter(expires_at__lte=timezone.now()).delete()
    return deleted
