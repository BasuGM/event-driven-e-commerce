from django.conf import settings


def test_tests_run_with_test_settings():
    assert settings.SETTINGS_MODULE.endswith(".test")
