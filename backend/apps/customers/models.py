from django.db import models


class Customer(models.Model):
    """A real person. ``external_id`` is Olist's ``customer_unique_id``.

    Olist issues a fresh ``customer_id`` for every order; that per-order ID lives on
    ``orders.Order.olist_customer_id``. Address fields come from the person's latest order.
    """

    external_id = models.CharField(max_length=32, unique=True)
    zip_code_prefix = models.CharField(max_length=5)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, db_index=True)

    def __str__(self) -> str:
        return f"{self.external_id[:8]} ({self.city}/{self.state})"
