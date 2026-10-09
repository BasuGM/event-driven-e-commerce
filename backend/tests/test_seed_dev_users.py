import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command

pytestmark = pytest.mark.django_db


def test_seed_dev_users_is_idempotent(monkeypatch):
    monkeypatch.setenv("DEV_USER_PASSWORD", "s3cret-pass")
    call_command("seed_dev_users")
    call_command("seed_dev_users")

    User = get_user_model()
    assert User.objects.count() == 3
    admin, staff, customer = (User.objects.get(username=u) for u in ("admin", "staff", "customer"))
    assert admin.is_superuser and admin.is_staff
    assert staff.is_staff and not staff.is_superuser
    assert not customer.is_staff
    assert customer.check_password("s3cret-pass")


def test_seed_dev_users_refuses_outside_dev(settings):
    settings.ALLOW_DEV_SEED = False
    with pytest.raises(CommandError, match="dev/test"):
        call_command("seed_dev_users")
