from django.conf import settings
from django.db import models

from apps.catalog.models import Offer

MAX_LINE_QUANTITY = 10


class Cart(models.Model):
    """One server-side cart per user. It never reserves stock; checkout does."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Cart of {self.user}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveSmallIntegerField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "offer"], name="uniq_cart_offer"),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=MAX_LINE_QUANTITY),
                name="cart_item_quantity_1_to_10",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.offer}"
