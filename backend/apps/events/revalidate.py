"""Tells the Next.js frontend to revalidate cache tags (POST /internal/revalidate)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

TIMEOUT_SECONDS = 5


class RevalidateError(Exception):
    pass


def product_tag(slug: str) -> str:
    """Must match productTag() in frontend/src/lib/cache-tags.ts."""
    return f"product:{slug}"


def revalidate_tags(tags: list[str]) -> None:
    """Raises on anything but a 2xx, so the consumer retries (and eventually dead-letters)."""
    if not settings.REVALIDATE_SECRET or not settings.FRONTEND_INTERNAL_URL:
        raise ImproperlyConfigured("REVALIDATE_SECRET and FRONTEND_INTERNAL_URL must be set")
    request = urllib.request.Request(
        f"{settings.FRONTEND_INTERNAL_URL.rstrip('/')}/internal/revalidate",
        data=json.dumps({"tags": tags}).encode(),
        headers={"Content-Type": "application/json", "x-revalidate-secret": settings.REVALIDATE_SECRET},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        raise RevalidateError(f"revalidate returned {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RevalidateError(f"revalidate failed: {exc}") from exc
    if not 200 <= status < 300:
        raise RevalidateError(f"revalidate returned {status}")
