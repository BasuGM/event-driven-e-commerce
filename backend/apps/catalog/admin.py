from django.contrib import admin
from django.db.models import Count

from .models import Category, Product, Seller


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name_english", "name", "product_count"]
    search_fields = ["name", "name_english"]

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


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["external_id", "category", "weight_g", "photos_qty"]
    list_filter = ["category"]
    list_select_related = ["category"]
    search_fields = ["external_id", "category__name", "category__name_english"]
    raw_id_fields = ["category"]
