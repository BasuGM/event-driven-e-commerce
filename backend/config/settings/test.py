from .base import *  # noqa: F403

DEBUG = False
ALLOW_DEV_SEED = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
LOGGING = {"version": 1, "disable_existing_loggers": False}
ALLOW_FAKE_PAYMENTS = True
CSRF_TRUSTED_ORIGINS = ["http://localhost:3000"]
RESERVATION_TTL_MINUTES = 15
