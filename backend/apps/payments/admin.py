from django.contrib import admin

from .models import PaymentIntent, ProviderEvent


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentIntent)
class PaymentIntentAdmin(ReadOnlyAdmin):
    """Flagged refunds: filter by "needs refund". (There's no refund logic yet.)"""

    list_display = ["created_at", "provider_payment_id", "order", "amount", "currency", "status", "needs_refund", "refund_reason"]
    list_filter = ["needs_refund", "status", "provider"]
    search_fields = ["provider_payment_id", "order__external_id"]
    list_select_related = ["order"]
    ordering = ["-created_at"]


@admin.register(ProviderEvent)
class ProviderEventAdmin(ReadOnlyAdmin):
    list_display = ["received_at", "provider_event_id", "type", "outcome", "payment_intent"]
    list_filter = ["outcome", "type", "provider"]
    search_fields = ["provider_event_id", "payment_intent__provider_payment_id"]
    ordering = ["-received_at"]
