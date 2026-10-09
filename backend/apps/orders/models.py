from django.db import models

from apps.catalog.models import Product, Seller
from apps.customers.models import Customer

MONEY = {"max_digits": 12, "decimal_places": 2}


class Order(models.Model):
    class Status(models.TextChoices):
        CREATED = "created"
        APPROVED = "approved"
        INVOICED = "invoiced"
        PROCESSING = "processing"
        SHIPPED = "shipped"
        DELIVERED = "delivered"
        CANCELED = "canceled"
        UNAVAILABLE = "unavailable"

    external_id = models.CharField(max_length=32, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    olist_customer_id = models.CharField(
        max_length=32, unique=True, help_text="Olist's per-order customer_id"
    )
    status = models.CharField(max_length=20, choices=Status.choices)
    purchased_at = models.DateTimeField()
    approved_at = models.DateTimeField(null=True, blank=True)
    delivered_carrier_at = models.DateTimeField(null=True, blank=True)
    delivered_customer_at = models.DateTimeField(null=True, blank=True)
    estimated_delivery_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-purchased_at"]
        indexes = [
            models.Index(fields=["purchased_at"]),
            # Also serves status-only filters (leftmost column), so no separate status index
            models.Index(fields=["status", "purchased_at"]),
        ]

    def __str__(self) -> str:
        return self.external_id


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    item_number = models.PositiveSmallIntegerField(help_text="Olist order_item_id (1, 2, ...)")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    seller = models.ForeignKey(Seller, on_delete=models.PROTECT, related_name="order_items")
    shipping_limit_at = models.DateTimeField()
    price = models.DecimalField(**MONEY)
    freight_value = models.DecimalField(**MONEY)

    class Meta:
        ordering = ["order", "item_number"]
        constraints = [
            models.UniqueConstraint(fields=["order", "item_number"], name="uniq_order_item_number")
        ]

    def __str__(self) -> str:
        return f"{self.order.external_id} #{self.item_number}"


class Payment(models.Model):
    class PaymentType(models.TextChoices):
        CREDIT_CARD = "credit_card"
        BOLETO = "boleto"
        VOUCHER = "voucher"
        DEBIT_CARD = "debit_card"
        NOT_DEFINED = "not_defined"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    sequential = models.PositiveSmallIntegerField()
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices, db_index=True)
    installments = models.PositiveSmallIntegerField()
    value = models.DecimalField(**MONEY)

    class Meta:
        ordering = ["order", "sequential"]
        constraints = [
            models.UniqueConstraint(fields=["order", "sequential"], name="uniq_payment_sequential")
        ]

    def __str__(self) -> str:
        return f"{self.order.external_id} payment {self.sequential}"


class Review(models.Model):
    """One row per (review, order). Olist sometimes attaches one review to several orders."""

    external_id = models.CharField(max_length=32, db_index=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="reviews")
    score = models.PositiveSmallIntegerField()
    comment_title = models.CharField(max_length=255, blank=True)
    comment_message = models.TextField(blank=True)
    created_date = models.DateField()
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_date"]
        constraints = [
            models.UniqueConstraint(fields=["external_id", "order"], name="uniq_review_per_order"),
            models.CheckConstraint(
                condition=models.Q(score__gte=1, score__lte=5), name="review_score_1_to_5"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.external_id} ({self.score}★)"
