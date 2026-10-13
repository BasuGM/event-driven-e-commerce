from django.contrib import admin
from django.db.models import Count

from .models import Category, Offer, Product, Seller


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name_english", "name", "slug", "product_count"]
    search_fields = ["name", "name_english", "slug"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_product_count=Count("products"))

    @admin.display(ordering="_product_count", description="Products")
    def product_count(self, obj):
        return obj._product_count


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ["external_id", "city", "state", "zip_code_prefix"]
    list_filter = ["state"]
    search_fields = ["external_id", "city", "zip_code_prefix"]


class OfferInline(admin.TabularInline):
    model = Offer
    extra = 0
    raw_id_fields = ["seller"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "name", "category", "min_price", "rating_avg", "rating_count", "sales_count", "external_id",
    ]
    list_filter = ["category"]
    list_select_related = ["category"]
    search_fields = ["name", "slug", "external_id", "category__name", "category__name_english"]
    raw_id_fields = ["category"]
    readonly_fields = [
        "min_price", "rating_avg", "rating_count", "sales_count", "first_sold_at",
    ]
    inlines = [OfferInline]


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ["product", "seller", "price", "stock"]
    list_select_related = ["product", "seller"]
    search_fields = ["product__name", "product__external_id", "seller__external_id"]
    raw_id_fields = ["product", "seller"]
