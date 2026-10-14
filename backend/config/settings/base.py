"""Settings shared by every environment. Values come from environment variables."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "apps.accounts",
    "apps.core",
    "apps.catalog",
    "apps.customers",
    "apps.orders",
    "apps.cart",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "ecommerce"),
        "USER": os.environ.get("POSTGRES_USER", "ecommerce"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Olist import
OLIST_DATA_DIR = os.environ.get("OLIST_DATA_DIR", "/data/olist")
OLIST_SOURCE_TIMEZONE = "America/Sao_Paulo"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Session auth only (no JWT). Views that are public opt out explicitly.
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
}

# --- Sessions and CSRF ---------------------------------------------------------------------
# The browser reaches Django through the Next.js rewrite (same origin), so cookies are
# first-party. Django sees Host=backend:8000 but Origin=http://localhost:<port>, hence the
# explicit trusted origins (we deliberately don't trust X-Forwarded-Host: port 8000 is exposed).
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
CSRF_COOKIE_HTTPONLY = False  # the browser client reads it to send X-CSRFToken
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True

# --- Orders --------------------------------------------------------------------------------
RESERVATION_TTL_MINUTES = int(os.environ.get("RESERVATION_TTL_MINUTES", "15"))
IDEMPOTENCY_KEY_TTL_HOURS = 24
ALLOW_FAKE_PAYMENTS = False  # simulated payments: dev/test only

# --- Celery --------------------------------------------------------------------------------
CELERY_BROKER_URL = REDIS_URL
CELERY_TASK_IGNORE_RESULT = True
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "release-expired-reservations": {
        "task": "apps.orders.tasks.release_expired_reservations",
        "schedule": 60.0,
    },
    "purge-expired-idempotency-keys": {
        "task": "apps.core.tasks.purge_expired_idempotency_keys",
        "schedule": 60.0 * 60 * 24,
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Event-driven e-commerce API",
    "DESCRIPTION": "E-commerce platform seeded with the Olist Brazilian E-Commerce dataset.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Keep component names stable for the generated TypeScript client
    "COMPONENT_SPLIT_REQUEST": True,
    # One shared enum for the three health fields instead of three auto-named copies
    "ENUM_NAME_OVERRIDES": {
        "HealthStatusEnum": "apps.core.serializers.HEALTH_CHOICES",
        "OrderStatusEnum": "apps.orders.models.Order.Status",
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
