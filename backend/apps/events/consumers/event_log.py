"""Every event, from every stream, into EventLog: the explorer's history (the outbox is only a
delivery buffer). Duplicates are ignored twice over: ProcessedEvent, then the unique event_id."""

from __future__ import annotations

from datetime import datetime

from ..consumer import ALL, Consumer
from ..models import EventLog
from ..streams import Event, stream_name


class EventLogConsumer(Consumer):
    name = "event_log"
    streams = ("order", "product")
    event_types = ALL

    def handle(self, event: Event) -> None:
        EventLog.objects.bulk_create(
            [
                EventLog(
                    event_id=event.id,
                    type=event.type,
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    stream=stream_name(event.aggregate_type),
                    schema_version=event.version,
                    payload=event.payload,
                    occurred_at=datetime.fromisoformat(event.occurred_at),
                )
            ],
            ignore_conflicts=True,  # ON CONFLICT (event_id) DO NOTHING
        )
