"""Dependency checks used by the health endpoint."""

import logging

import redis
from django.conf import settings
from django.db import connection
from django.db.models import Count, Min
from django.utils import timezone

from apps.events.models import OutboxEvent

logger = logging.getLogger(__name__)


def check_db() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except Exception:
        logger.exception("Database health check failed")
        return False


def outbox_backlog() -> dict:
    """Unpublished outbox events and the age of the oldest (served by the partial index)."""
    row = OutboxEvent.objects.filter(published_at__isnull=True).aggregate(n=Count("id"), oldest=Min("occurred_at"))
    oldest = row["oldest"]
    return {
        "unpublished": row["n"],
        "oldest_unpublished_age_seconds": None if oldest is None else int((timezone.now() - oldest).total_seconds()),
    }


def check_redis() -> bool:
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        return bool(client.ping())
    except Exception:
        logger.exception("Redis health check failed")
        return False
