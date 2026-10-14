import re
from collections import OrderedDict
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalog.serializers import CategoryRefSerializer

from .models import Order, OrderStatusHistory

BR_STATES = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR",
    "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]


class ShippingAddressSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=120)
    street = serializers.CharField(max_length=200, help_text="Street, number and complement")
    city = serializers.CharField(max_length=100)
    state = serializers.ChoiceField(choices=BR_STATES)
    zip_code = serializers.RegexField(r"^\d{5}-?\d{3}$", help_text="CEP, e.g. 01310-100")

    def validate_zip_code(self, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        return f"{digits[:5]}-{digits[5:]}"


class CheckoutSerializer(serializers.Serializer):
    shipping = ShippingAddressSerializer()


class PaySerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["success", "fail"])


class ErrorLineSerializer(serializers.Serializer):
    offer_id = serializers.IntegerField()
    product = serializers.CharField()
    requested = serializers.IntegerField()
    available = serializers.IntegerField()


class DomainErrorSerializer(serializers.Serializer):
    """Body of every 409 (and empty-cart 400) from the order flow."""

    code = serializers.ChoiceField(
        choices=["out_of_stock", "reservation_expired", "invalid_transition", "idempotency_conflict", "empty_cart"]
    )
    detail = serializers.CharField()
    lines = ErrorLineSerializer(many=True, required=False)
    current_status = serializers.CharField(required=False)


class StatusHistorySerializer(serializers.ModelSerializer):
    # Blank for the first row (the order didn't exist before "created")
    from_status = serializers.ChoiceField(choices=Order.Status.choices, allow_blank=True)

    class Meta:
        model = OrderStatusHistory
        fields = ["from_status", "to_status", "reason", "created_at"]
        read_only_fields = fields


class OrderLineSerializer(serializers.Serializer):
    product_slug = serializers.CharField()
    product_name = serializers.CharField()
    category = CategoryRefSerializer(allow_null=True)
    seller_id = serializers.CharField()
    seller_city = serializers.CharField()
    seller_state = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit_freight = serializers.DecimalField(max_digits=12, decimal_places=2)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2)


class ShippingSerializer(serializers.Serializer):
    full_name = serializers.CharField(source="shipping_name")
    street = serializers.CharField(source="shipping_street")
    city = serializers.CharField(source="shipping_city")
    state = serializers.CharField(source="shipping_state")
    zip_code = serializers.CharField(source="shipping_zip")


class OrderListSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="external_id")
    item_count = serializers.IntegerField()
    items_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    freight_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    reservation_expires_at = serializers.DateTimeField(allow_null=True)

    class Meta:
        model = Order
        fields = [
            "id", "status", "purchased_at", "item_count", "items_total", "freight_total", "total",
            "reservation_expires_at",
        ]
        read_only_fields = fields


class OrderDetailSerializer(serializers.ModelSerializer):
    """Expects an order from ``selectors.orders_with_totals()`` with items (product, category,
    seller), status history and reservations prefetched.

    Money comes from DB annotations through DecimalFields: a Decimal returned by a
    SerializerMethodField would be rendered as a JSON float by DRF's encoder.
    """

    id = serializers.CharField(source="external_id")
    lines = serializers.SerializerMethodField()
    item_count = serializers.IntegerField()
    items_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    freight_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    shipping = ShippingSerializer(source="*")
    status_history = StatusHistorySerializer(many=True)
    reservation_expires_at = serializers.DateTimeField(allow_null=True)
    can_pay = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    payments_enabled = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "status", "purchased_at", "approved_at", "lines", "item_count", "items_total",
            "freight_total", "total", "shipping", "status_history", "reservation_expires_at",
            "can_pay", "can_cancel", "payments_enabled",
        ]
        read_only_fields = fields

    @extend_schema_field(OrderLineSerializer(many=True))
    def get_lines(self, order):
        # Olist-style storage is one row per unit; group units back into display lines.
        lines: OrderedDict = OrderedDict()
        for item in order.items.all():
            key = (item.product_id, item.seller_id, item.price, item.freight_value)
            if key not in lines:
                lines[key] = {
                    "product_slug": item.product.slug,
                    "product_name": item.product.name,
                    "category": item.product.category,
                    "seller_id": item.seller.external_id[:8],
                    "seller_city": item.seller.city,
                    "seller_state": item.seller.state,
                    "quantity": 0,
                    "unit_price": item.price,
                    "unit_freight": item.freight_value,
                    "line_total": Decimal("0.00"),
                }
            lines[key]["quantity"] += 1
            lines[key]["line_total"] += item.price
        return OrderLineSerializer(lines.values(), many=True).data

    def _expired(self, order) -> bool:
        expires = order.reservation_expires_at
        return expires is not None and expires <= timezone.now()

    def get_can_pay(self, order) -> bool:
        return order.status == Order.Status.CREATED and not self._expired(order)

    def get_can_cancel(self, order) -> bool:
        return order.status == Order.Status.CREATED

    def get_payments_enabled(self, order) -> bool:
        return settings.ALLOW_FAKE_PAYMENTS
