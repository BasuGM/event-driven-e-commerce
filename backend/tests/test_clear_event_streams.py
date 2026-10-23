from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.events.streams import dlq_stream, stream_name


def test_deletes_only_the_event_streams(events_redis):
    events_redis.xadd(stream_name("order"), {"id": "1"})
    events_redis.xgroup_create(stream_name("order"), "product_stats", id="0")
    events_redis.xadd(dlq_stream(), {"id": "2"})
    events_redis.set("celery-task-meta-123", "x")  # a non-event key in the same DB
    events_redis.set("test-events:not-a-stream", "x")  # same prefix, but not a stream

    out = StringIO()
    call_command("clear_event_streams", stdout=out)

    assert "Deleted 2 event stream(s)" in out.getvalue()
    assert not events_redis.exists(stream_name("order"), dlq_stream())
    assert events_redis.get("celery-task-meta-123") == "x"
    assert events_redis.get("test-events:not-a-stream") == "x"
    events_redis.delete("celery-task-meta-123")


def test_refuses_outside_dev_settings(settings):
    settings.ALLOW_DEV_SEED = False
    with pytest.raises(CommandError, match="dev/test settings"):
        call_command("clear_event_streams")
