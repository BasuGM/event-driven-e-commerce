from django.contrib import admin

from .models import Order, OrderItem, Payment, Review


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ["product", "seller"]


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


class ReviewInline(admin.StackedInline):
    model = Review
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["external_id", "customer", "status", "purchased_at", "delivered_customer_at"]
    list_filter = ["status", "purchased_at"]
    list_select_related = ["customer"]
    search_fields = ["external_id", "olist_customer_id", "customer__external_id"]
    raw_id_fields = ["customer"]
    date_hierarchy = "purchased_at"
    inlines = [OrderItemInline, PaymentInline, ReviewInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["order", "item_number", "product", "seller", "price", "freight_value"]
    list_select_related = ["order", "product", "seller"]
    search_fields = ["order__external_id", "product__external_id", "seller__external_id"]
    raw_id_fields = ["order", "product", "seller"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["order", "sequential", "payment_type", "installments", "value"]
    list_filter = ["payment_type"]
    list_select_related = ["order"]
    search_fields = ["order__external_id"]
    raw_id_fields = ["order"]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["external_id", "order", "score", "comment_title", "created_date"]
    list_filter = ["score", "created_date"]
    list_select_related = ["order"]
    search_fields = ["external_id", "order__external_id", "comment_title", "comment_message"]
    raw_id_fields = ["order"]
