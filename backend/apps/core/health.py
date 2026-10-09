"""Dependency checks used by the health endpoint."""

import logging

import redis
from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)


def check_db() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except Exception:
        logger.exception("Database health check failed")
        return False


def check_redis() -> bool:
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        return bool(client.ping())
    except Exception:
        logger.exception("Redis health check failed")
        return False
