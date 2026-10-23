"""Startup gate for the relay and consumers: wait for `make migrate` instead of erroring.

On a fresh `make up` (or after `make reset` drops the schema) these services can start before
the events tables exist. They wait here, logging once, rather than logging a traceback every
retry. Consumers must not start early: they'd fail every event they read and dead-letter it.
"""

from __future__ import annotations

import logging
import threading

from django.db import DatabaseError, close_old_connections, connection

logger = logging.getLogger(__name__)

EVENT_TABLES = frozenset({"events_outboxevent", "events_processedevent"})
POLL_SECONDS = 2.0


def missing_event_tables() -> set[str]:
    try:
        return set(EVENT_TABLES - set(connection.introspection.table_names()))
    except DatabaseError:
        return set(EVENT_TABLES)  # can't tell yet (database starting up): not ready


def wait_for_event_tables(stop: threading.Event, *, who: str) -> bool:
    """Block until the events tables exist (True) or ``stop`` is set (False)."""
    if not missing_event_tables():
        return True
    logger.info("%s: waiting for the events tables (run `make migrate`)", who)
    while not stop.wait(POLL_SECONDS):
        close_old_connections()
        if not missing_event_tables():
            logger.info("%s: events tables found, starting", who)
            return True
    return False
