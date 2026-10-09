from unittest import mock

import pytest

pytestmark = pytest.mark.django_db


def test_health_ok(api_client):
    with mock.patch("apps.core.views.check_redis", return_value=True):
        response = api_client.get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "redis": "ok"}


def test_health_reports_redis_down_with_503(api_client):
    with mock.patch("redis.Redis.ping", side_effect=ConnectionError("refused")):
        response = api_client.get("/api/health/")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "ok", "redis": "error"}


def test_health_reports_db_down_with_503(api_client):
    with (
        mock.patch("apps.core.views.check_db", return_value=False),
        mock.patch("apps.core.views.check_redis", return_value=True),
    ):
        response = api_client.get("/api/health/")

    assert response.status_code == 503
    assert response.json()["db"] == "error"
