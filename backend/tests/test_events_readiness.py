"""The relay and consumers wait (quietly) for migrations instead of erroring."""

import logging
import threading
from unittest import mock

import pytest

from apps.events import readiness
from apps.events.readiness import missing_event_tables, wait_for_event_tables

pytestmark = pytest.mark.django_db


def test_tables_exist_after_migrations():
    assert missing_event_tables() == set()
    assert wait_for_event_tables(threading.Event(), who="Relay") is True


def test_waits_logging_once_then_starts(caplog, monkeypatch):
    monkeypatch.setattr(readiness, "POLL_SECONDS", 0)
    checks = iter([{"events_outboxevent"}] * 4 + [set()])
    with mock.patch.object(readiness, "missing_event_tables", side_effect=lambda: next(checks)):
        with caplog.at_level(logging.INFO, logger="apps.events.readiness"):
            assert wait_for_event_tables(threading.Event(), who="Relay") is True

    assert [r.getMessage() for r in caplog.records] == [
        "Relay: waiting for the events tables (run `make migrate`)",
        "Relay: events tables found, starting",
    ]
    assert all(r.levelno == logging.INFO for r in caplog.records)


def test_stopping_while_waiting_returns_false(monkeypatch):
    monkeypatch.setattr(readiness, "POLL_SECONDS", 0)
    stop = threading.Event()
    stop.set()
    with mock.patch.object(readiness, "missing_event_tables", return_value={"events_outboxevent"}):
        assert wait_for_event_tables(stop, who="Consumers") is False
