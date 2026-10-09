from pathlib import Path

import pytest
from rest_framework.test import APIClient

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "olist"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def olist_dir():
    return FIXTURES_DIR
