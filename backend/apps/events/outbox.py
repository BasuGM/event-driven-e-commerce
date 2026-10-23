"""Writing domain events. Call ``record_event`` from the service layer only (never views or
signals), inside the transaction that makes the change the event describes."""

from __future__ import annotations

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

from .models import OutboxEvent


def record_event(
    event_type: str, aggregate_type: str, aggregate_id: str, payload: dict, *, schema_version: int = 1
) -> OutboxEvent:
    """Add an event to the outbox. Commits (or rolls back) with the caller's transaction."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("record_event() must run inside the transaction that makes the change")
    # Round-trip through DjangoJSONEncoder: Decimal -> "75.01", datetime -> ISO 8601, like the API
    data = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
    return OutboxEvent.objects.create(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        schema_version=schema_version,
        payload=data,
    )
