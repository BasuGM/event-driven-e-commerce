"""Read-side querysets for the orders API (constant query counts)."""

from decimal import Decimal

from django.db.models import Count, DecimalField, F, OuterRef, Prefetch, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from .models import Order, OrderItem, Reservation

MONEY = DecimalField(max_digits=12, decimal_places=2)
ZERO = Value(Decimal("0.00"), output_field=MONEY)


def orders_with_totals(user):
    """The user's orders with totals and reservation expiry as annotations (one query).

    Only items are joined for the aggregates; the reservation expiry is a correlated subquery,
    because a second join would multiply item rows and inflate the sums.
    """
    active_expiry = (
        Reservation.objects.filter(order=OuterRef("pk"), status=Reservation.Status.ACTIVE)
        .order_by("expires_at")
        .values("expires_at")[:1]
    )
    return (
        Order.objects.filter(customer__user=user)
        .annotate(
            item_count=Count("items"),
            items_total=Coalesce(Sum("items__price"), ZERO),
            freight_total=Coalesce(Sum("items__freight_value"), ZERO),
            total=F("items_total") + F("freight_total"),
            reservation_expires_at=Subquery(active_expiry),
        )
        .order_by("-purchased_at", "-id")
    )


def order_detail(user):
    return orders_with_totals(user).prefetch_related(
        Prefetch(
            "items",
            queryset=OrderItem.objects.select_related("product__category", "seller").order_by("item_number"),
        ),
        "status_history",
    )
