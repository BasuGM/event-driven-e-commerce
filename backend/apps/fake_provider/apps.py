from django.apps import AppConfig


class FakeProviderConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fake_provider"
