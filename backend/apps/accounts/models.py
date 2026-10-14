from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    """Project user model. Customers log in by email; ``username`` mirrors it for new users."""

    class Meta(AbstractUser.Meta):
        constraints = [
            # Case-insensitive unique email; blank emails (e.g. createsuperuser without one) allowed.
            models.UniqueConstraint(
                Lower("email"), condition=~models.Q(email=""), name="uniq_user_email_ci"
            )
        ]

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.email or self.username
