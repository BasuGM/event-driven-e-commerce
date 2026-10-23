"""Redis connection and stream names shared by the relay and the consumers."""

from __future__ import annotations

import json
from dataclasses import dataclass

import redis
from django.conf import settings


def redis_client() -> redis.Redis:
    """Timeouts matter: the relay calls Redis while holding row locks in an open transaction.
    A hung Redis must surface as an error within seconds, not hold those locks forever.
    (Consumers' blocking reads use BLOCK < socket_timeout, so they don't trip it.)"""
    return redis.Redis.from_url(
        settings.EVENTS_REDIS_URL,
        socket_connect_timeout=settings.EVENTS_REDIS_CONNECT_TIMEOUT,
        socket_timeout=settings.EVENTS_REDIS_SOCKET_TIMEOUT,
        decode_responses=True,
    )


def stream_name(aggregate_type: str) -> str:
    return f"{settings.EVENTS_STREAM_PREFIX}:{aggregate_type}"


def dlq_stream() -> str:
    return f"{settings.EVENTS_STREAM_PREFIX}:dlq"


@dataclass(frozen=True)
class Event:
    """An event as read back from a stream entry."""

    id: str
    type: str
    aggregate_type: str
    aggregate_id: str
    version: int
    occurred_at: str
    payload: dict

    @classmethod
    def from_fields(cls, fields: dict[str, str]) -> Event:
        return cls(
            id=fields["id"],
            type=fields["type"],
            aggregate_type=fields["aggregate_type"],
            aggregate_id=fields["aggregate_id"],
            version=int(fields["version"]),
            occurred_at=fields["occurred_at"],
            payload=json.loads(fields["payload"]),
        )


def entry_fields(event) -> dict[str, str]:
    """OutboxEvent -> the flat string fields of a stream entry (the event id travels with it)."""
    return {
        "id": str(event.id),
        "type": event.event_type,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": event.aggregate_id,
        "version": str(event.schema_version),
        "occurred_at": event.occurred_at.isoformat(),
        "payload": json.dumps(event.payload, separators=(",", ":")),
    }
