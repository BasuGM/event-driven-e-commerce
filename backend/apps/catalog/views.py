from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics

from apps.orders.models import Review

from .filters import ProductListQuerySerializer, filter_products
from .models import Category, Offer, Product
from .pagination import ReviewPagination, StrictPageNumberPagination
from .serializers import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductReviewSerializer,
)


class PublicMixin:
    authentication_classes: list = []
    permission_classes: list = []


@extend_schema(summary="Categories that have at least one product")
class CategoryListView(PublicMixin, generics.ListAPIView):
    serializer_class = CategorySerializer
    pagination_class = None

    def get_queryset(self):
        return (
            Category.objects.annotate(product_count=Count("products"))
            .filter(product_count__gt=0)
            .order_by("name_english")
        )


@extend_schema(summary="Browse, filter and search products", parameters=[ProductListQuerySerializer])
class ProductListView(PublicMixin, generics.ListAPIView):
    serializer_class = ProductListSerializer
    pagination_class = StrictPageNumberPagination

    def get_queryset(self):
        params = ProductListQuerySerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        return filter_products(Product.objects.select_related("category"), params.validated_data)


@extend_schema(summary="Product detail with offers")
class ProductDetailView(PublicMixin, generics.RetrieveAPIView):
    serializer_class = ProductDetailSerializer
    lookup_field = "slug"
    queryset = Product.objects.select_related("category").prefetch_related(
        Prefetch("offers", queryset=Offer.objects.select_related("seller").order_by("price", "id"))
    )


@extend_schema(summary="Reviews of orders containing this product, newest first")
class ProductReviewListView(PublicMixin, generics.ListAPIView):
    serializer_class = ProductReviewSerializer
    pagination_class = ReviewPagination

    def get_queryset(self):
        product = get_object_or_404(Product.objects.only("id"), slug=self.kwargs["slug"])
        # One Olist review can cover several orders (one Review row each) and an order can hold
        # the product twice: DISTINCT ON the Olist review ID shows each review once.
        return (
            Review.objects.filter(order__items__product=product)
            .order_by("-created_date", "external_id", "id")
            .distinct("created_date", "external_id")
        )
