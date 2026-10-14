import os

from .base import *  # noqa: F403

DEBUG = True
# Dev-only accounts (admin / staff / customer) may be seeded in this environment.
ALLOW_DEV_SEED = True
ALLOW_FAKE_PAYMENTS = os.environ.get("ALLOW_FAKE_PAYMENTS", "true").lower() == "true"
