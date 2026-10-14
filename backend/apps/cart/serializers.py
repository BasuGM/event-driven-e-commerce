from rest_framework import serializers

from apps.catalog.serializers import CategoryRefSerializer

from .models import MAX_LINE_QUANTITY


class CartProductSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    category = CategoryRefSerializer(allow_null=True)


class CartSellerSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="First 8 chars of the Olist seller id")
    city = serializers.CharField()
    state = serializers.CharField()


class CartLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    offer_id = serializers.IntegerField()
    product = CartProductSerializer()
    seller = CartSellerSerializer()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit_freight = serializers.DecimalField(max_digits=12, decimal_places=2)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    line_freight = serializers.DecimalField(max_digits=12, decimal_places=2)
    available = serializers.IntegerField(help_text="Units currently in stock (not reserved for you)")
    warning = serializers.ChoiceField(
        choices=["out_of_stock", "insufficient_stock"], allow_null=True,
        help_text="Set when checkout would fail for this line right now",
    )


class CartSerializer(serializers.Serializer):
    lines = CartLineSerializer(many=True)
    item_count = serializers.IntegerField(help_text="Total units")
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    freight_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    can_checkout = serializers.BooleanField()


class AddCartItemSerializer(serializers.Serializer):
    offer_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_LINE_QUANTITY, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_LINE_QUANTITY)
