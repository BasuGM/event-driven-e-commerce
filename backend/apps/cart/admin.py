from django.contrib import admin

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    raw_id_fields = ["offer"]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "line_count", "updated_at"]
    search_fields = ["user__email", "user__username"]
    raw_id_fields = ["user"]
    inlines = [CartItemInline]

    @admin.display(description="Lines")
    def line_count(self, obj):
        return obj.items.count()
