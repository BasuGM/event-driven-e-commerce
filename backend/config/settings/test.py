import os

from .base import *  # noqa: F403

DEBUG = False
ALLOW_DEV_SEED = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
LOGGING = {"version": 1, "disable_existing_loggers": False}
ALLOW_FAKE_PAYMENTS = True
CSRF_TRUSTED_ORIGINS = ["http://localhost:3000"]
RESERVATION_TTL_MINUTES = 15

# Events: a separate Redis DB (tests delete their keys), reclaim at once, give up sooner
EVENTS_REDIS_URL = os.environ.get("EVENTS_TEST_REDIS_URL", "redis://redis:6379/15")
EVENTS_STREAM_PREFIX = "test-events"
EVENTS_CLAIM_IDLE_MS = 0
EVENTS_MAX_DELIVERIES = 3
EVENTS_BLOCK_MS = 10
REVALIDATE_SECRET = "test-revalidate-secret"
FRONTEND_INTERNAL_URL = "http://frontend.test"
