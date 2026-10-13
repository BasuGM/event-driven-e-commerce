from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.orders.models import Review

from .enrichment import GROUPS
from .models import Category, Offer, Product

CATEGORY_GROUPS = sorted(GROUPS)

# Every serializer here is output-only: read_only_fields = fields makes drf-spectacular mark all
# fields as required (always present) in responses, so the TS types have no needless `?`.


class CategoryRefSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)
    group = serializers.ChoiceField(
        choices=CATEGORY_GROUPS, read_only=True, help_text="Drives the placeholder image"
    )

    class Meta:
        model = Category
        fields = ["slug", "label", "group"]
        read_only_fields = fields


class CategorySerializer(CategoryRefSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta(CategoryRefSerializer.Meta):
        fields = [*CategoryRefSerializer.Meta.fields, "product_count"]
        read_only_fields = fields


class ProductListSerializer(serializers.ModelSerializer):
    category = CategoryRefSerializer(read_only=True, allow_null=True)
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "slug", "name", "category", "image_url", "min_price", "in_stock",
            "rating_avg", "rating_count",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.BooleanField())
    def get_in_stock(self, obj: Product) -> bool:
        return obj.min_price is not None


class OfferSerializer(serializers.ModelSerializer):
    seller_id = serializers.CharField(source="seller.external_id", read_only=True)
    seller_city = serializers.CharField(source="seller.city", read_only=True)
    seller_state = serializers.CharField(source="seller.state", read_only=True)
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Offer
        # The exact stock number stays private; buyers only need availability.
        fields = ["id", "seller_id", "seller_city", "seller_state", "price", "in_stock"]
        read_only_fields = fields


class DimensionsSerializer(serializers.Serializer):
    weight_g = serializers.IntegerField(allow_null=True)
    length_cm = serializers.IntegerField(allow_null=True)
    width_cm = serializers.IntegerField(allow_null=True)
    height_cm = serializers.IntegerField(allow_null=True)


class ProductDetailSerializer(ProductListSerializer):
    dimensions = DimensionsSerializer(source="*", read_only=True)
    offers = OfferSerializer(many=True, read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = [
            *ProductListSerializer.Meta.fields, "description", "dimensions", "sales_count",
            "photos_qty", "offers",
        ]
        read_only_fields = fields


class ProductReviewSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="comment_title")
    message = serializers.CharField(source="comment_message")

    class Meta:
        model = Review
        fields = ["id", "score", "title", "message", "created_date"]
        read_only_fields = fields
