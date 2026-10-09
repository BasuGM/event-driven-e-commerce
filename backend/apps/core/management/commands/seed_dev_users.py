import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

DEV_USERS = [
    # username, is_staff, is_superuser
    ("admin", True, True),
    ("staff", True, False),
    ("customer", False, False),
]


class Command(BaseCommand):
    help = "Create or refresh the dev-only accounts admin / staff / customer."

    def handle(self, *args, **options):
        if not getattr(settings, "ALLOW_DEV_SEED", False):
            raise CommandError("seed_dev_users only runs with dev/test settings (ALLOW_DEV_SEED).")
        password = os.environ.get("DEV_USER_PASSWORD", "devpass123")
        User = get_user_model()
        for username, is_staff, is_superuser in DEV_USERS:
            user, created = User.objects.update_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                    "is_staff": is_staff,
                    "is_superuser": is_superuser,
                    "is_active": True,
                },
            )
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(f"{'Created' if created else 'Updated'} dev user '{username}'")
        self.stdout.write(self.style.SUCCESS("Dev users ready (password from DEV_USER_PASSWORD)."))
