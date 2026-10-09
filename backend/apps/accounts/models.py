from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Project user model.

    Empty for now; defining it up front means we can add fields later without the painful
    mid-project swap away from ``auth.User``.
    """
