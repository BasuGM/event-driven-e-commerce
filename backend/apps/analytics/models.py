"""Analytics projections: one row per (day, source[, key]), recomputed from orders (never
incremented). day = the order's purchase date in America/Sao_Paulo (Olist is Brazilian local
time); every table is keyed by purchase day, delivery stats included.

Revenue (gmv, revenue, paid_orders) counts only orders that reached approved or later
(approved, invoiced, processing, shipped, delivered). `orders` and `canceled_orders` count every
placed order.
"""

from django.db import models

MONEY = {"max_digits": 14, "decimal_places": 2}  # sums of order money (12,2) need headroom
SOURCES = [("olist", "olist"), ("app", "app"), ("replay", "replay")]


class DailySales(models.Model):
    day = models.DateField()
    source = models.CharField(max_length=10, choices=SOURCES)
    orders = models.PositiveIntegerField(help_text="Every placed order")
    canceled_orders = models.PositiveIntegerField(help_text="Canceled or unavailable")
    paid_orders = models.PositiveIntegerField(help_text="Reached approved or later")
    gmv = models.DecimalField(**MONEY, help_text="Items + freight of paid orders")
    items = models.PositiveIntegerField(help_text="Units on paid orders")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["day", "source"], name="uniq_daily_sales")]


class CategorySales(models.Model):
    day = models.DateField()
    source = models.CharField(max_length=10, choices=SOURCES)
    category = models.ForeignKey("catalog.Category", null=True, on_delete=models.CASCADE, related_name="+")
    revenue = models.DecimalField(**MONEY, help_text="Item prices on paid orders (freight isn't per category)")
    units = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["day", "source", "category"], name="uniq_category_sales", nulls_distinct=False
            )
        ]


class StateSales(models.Model):
    day = models.DateField()
    source = models.CharField(max_length=10, choices=SOURCES)
    state = models.CharField(max_length=2, help_text="Shipping state, else the customer's")
    orders = models.PositiveIntegerField()
    gmv = models.DecimalField(**MONEY)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["day", "source", "state"], name="uniq_state_sales")]


class DeliveryStats(models.Model):
    day = models.DateField(help_text="Purchase day")
    source = models.CharField(max_length=10, choices=SOURCES)
    delivered = models.PositiveIntegerField()
    delivery_seconds_total = models.BigIntegerField(help_text="Sum of purchase -> delivery")
    late = models.PositiveIntegerField(help_text="Delivered after the estimated date")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["day", "source"], name="uniq_delivery_stats")]
