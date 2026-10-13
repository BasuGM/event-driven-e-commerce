"""Query-parameter validation and filtering for the product list."""

from __future__ import annotations

import re

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F, QuerySet
from rest_framework import serializers

from .models import Category

ORDERINGS = {
    "popular": [F("sales_count").desc(), F("rating_count").desc()],
    "price": [F("min_price").asc(nulls_last=True)],
    "-price": [F("min_price").desc(nulls_last=True)],
    "rating": [F("rating_avg").desc(nulls_last=True), F("rating_count").desc()],
    "newest": [F("first_sold_at").desc(nulls_last=True)],
}


class ProductListQuerySerializer(serializers.Serializer):
    """Validates /api/products/ query params (bad values -> 400) and documents them in OpenAPI."""

    category = serializers.SlugField(required=False, help_text="Category slug")
    q = serializers.CharField(
        required=False, max_length=100, allow_blank=True,
        help_text="Search product and category names (prefix match, e.g. 'duv cov')",
    )
    min_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False)
    max_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False)
    min_rating = serializers.DecimalField(
        max_digits=3, decimal_places=2, min_value=1, max_value=5, required=False
    )
    in_stock = serializers.BooleanField(
        required=False, allow_null=True, default=None, help_text="true = only products you can buy"
    )
    ordering = serializers.ChoiceField(
        choices=list(ORDERINGS), required=False,
        help_text="Default: relevance when searching, otherwise popular",
    )

    def validate_category(self, value: str) -> str:
        if not Category.objects.filter(slug=value).exists():
            raise serializers.ValidationError(f"Unknown category '{value}'.")
        return value

    def validate(self, attrs):
        low, high = attrs.get("min_price"), attrs.get("max_price")
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError({"max_price": ["Must be greater than or equal to min_price."]})
        return attrs


def prefix_search_query(text: str) -> SearchQuery | None:
    """'duv cov' -> to_tsquery('english', 'duv:* & cov:*'). Only word chars reach to_tsquery."""
    words = re.findall(r"\w+", text.lower())
    if not words:
        return None
    return SearchQuery(" & ".join(f"{w}:*" for w in words), search_type="raw", config="english")


def filter_products(queryset: QuerySet, params: dict) -> QuerySet:
    if slug := params.get("category"):
        queryset = queryset.filter(category__slug=slug)
    if (low := params.get("min_price")) is not None:
        queryset = queryset.filter(min_price__gte=low)
    if (high := params.get("max_price")) is not None:
        queryset = queryset.filter(min_price__lte=high)
    if (rating := params.get("min_rating")) is not None:
        queryset = queryset.filter(rating_avg__gte=rating)
    if params.get("in_stock") is True:
        # min_price is only set when at least one offer has stock
        queryset = queryset.filter(min_price__isnull=False)
    elif params.get("in_stock") is False:
        queryset = queryset.filter(min_price__isnull=True)

    ordering = params.get("ordering")
    query = prefix_search_query(params.get("q") or "")
    if query is not None:
        queryset = queryset.filter(search_vector=query)
        if ordering is None:
            queryset = queryset.annotate(rank=SearchRank(F("search_vector"), query))
            return queryset.order_by(F("rank").desc(), "id")
    # id last so pages never overlap or skip rows when sort keys tie
    return queryset.order_by(*ORDERINGS[ordering or "popular"], "id")
