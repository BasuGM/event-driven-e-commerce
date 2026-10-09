import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_stats_empty_db(api_client):
    response = api_client.get("/api/stats/")

    assert response.status_code == 200
    assert response.json() == {"products": 0, "orders": 0, "customers": 0, "sellers": 0}


def test_stats_counts_imported_rows(api_client, olist_dir):
    call_command("import_olist", "--size", "large", "--data-dir", str(olist_dir), stdout=None)

    response = api_client.get("/api/stats/")

    assert response.json() == {"products": 3, "orders": 5, "customers": 4, "sellers": 2}
