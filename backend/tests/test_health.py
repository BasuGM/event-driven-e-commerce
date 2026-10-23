from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.events.models import OutboxEvent

pytestmark = pytest.mark.django_db


def test_health_ok(api_client):
    with mock.patch("apps.core.views.check_redis", return_value=True):
        response = api_client.get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "db": "ok",
        "redis": "ok",
        "outbox": {"unpublished": 0, "oldest_unpublished_age_seconds": None},
    }


def test_health_reports_redis_down_with_503(api_client):
    with mock.patch("redis.Redis.ping", side_effect=ConnectionError("refused")):
        response = api_client.get("/api/health/")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "db": "ok",
        "redis": "error",
        "outbox": {"unpublished": 0, "oldest_unpublished_age_seconds": None},
    }


def test_health_reports_db_down_with_503(api_client):
    with (
        mock.patch("apps.core.views.check_db", return_value=False),
        mock.patch("apps.core.views.check_redis", return_value=True),
    ):
        response = api_client.get("/api/health/")

    assert response.status_code == 503
    assert response.json()["db"] == "error"
    assert response.json()["outbox"] is None


def test_health_reports_outbox_backlog_without_failing(api_client):
    """A stuck relay is visible, but a backlog alone isn't an outage (status stays ok)."""
    OutboxEvent.objects.create(
        event_type="OrderPlaced", aggregate_type="order", aggregate_id="a" * 32, payload={},
        occurred_at=timezone.now() - timedelta(seconds=90),
    )
    OutboxEvent.objects.create(event_type="OrderPaid", aggregate_type="order", aggregate_id="a" * 32, payload={})
    OutboxEvent.objects.create(
        event_type="OrderPaid", aggregate_type="order", aggregate_id="b" * 32, payload={},
        published_at=timezone.now(),
    )
    with mock.patch("apps.core.views.check_redis", return_value=True):
        response = api_client.get("/api/health/")

    assert response.status_code == 200
    outbox = response.json()["outbox"]
    assert outbox["unpublished"] == 2
    assert 90 <= outbox["oldest_unpublished_age_seconds"] < 120
