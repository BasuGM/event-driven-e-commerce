from django.contrib import admin

from .models import IdempotencyKey


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ["key", "user", "response_status", "order", "created_at", "expires_at"]
    list_filter = ["response_status"]
    search_fields = ["key", "user__email", "order__external_id"]
    list_select_related = ["user", "order"]
    # An audit record: inspect, never edit
    readonly_fields = [f.name for f in IdempotencyKey._meta.fields]

    def has_add_permission(self, request):
        return False
