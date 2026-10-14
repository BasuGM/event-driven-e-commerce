"""Idempotency keys for unsafe requests (checkout now, payments later).

A retry with the same key replays the stored response; the same key with a different body is a
409. Only successful outcomes are stored: the key row is inserted in the *same* transaction as
the work, so a failure rolls both back and a retry simply runs again.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.utils import timezone

from .errors import IdempotencyConflict
from .models import IdempotencyKey


@dataclass
class IdempotentResult:
    status: int
    body: dict
    replayed: bool


def request_hash(data) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), cls=DjangoJSONEncoder)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _replay(record: IdempotencyKey, digest: str) -> IdempotentResult:
    if record.request_hash != digest:
        raise IdempotencyConflict(
            "This Idempotency-Key was already used with a different request body."
        )
    return IdempotentResult(record.response_status, record.response_body, replayed=True)


def run_idempotent(user, key: str, data, handler: Callable[[], tuple[int, dict, object]]) -> IdempotentResult:
    """Run ``handler`` at most once per (user, key) and remember its successful response.

    ``handler`` returns (status, body, order) and runs inside the same transaction as the key
    insert. Concurrency: a second request with the same key blocks on the unique index until the
    first commits, then gets IntegrityError and replays the stored response.
    """
    digest = request_hash(data)
    now = timezone.now()
    # An expired key is forgotten: the same key may be used again
    IdempotencyKey.objects.filter(user=user, key=key, expires_at__lte=now).delete()

    with transaction.atomic():
        try:
            with transaction.atomic():  # savepoint: a duplicate insert must not poison the outer tx
                record = IdempotencyKey.objects.create(
                    user=user, key=key, request_hash=digest,
                    expires_at=now + timedelta(hours=settings.IDEMPOTENCY_KEY_TTL_HOURS),
                )
        except IntegrityError:
            return _replay(IdempotencyKey.objects.get(user=user, key=key), digest)

        status, body, order = handler()  # DomainError here rolls back the key row too
        record.response_status = status
        record.response_body = json.loads(json.dumps(body, cls=DjangoJSONEncoder))
        record.order = order
        record.save(update_fields=["response_status", "response_body", "order"])
        return IdempotentResult(status, record.response_body, replayed=False)
