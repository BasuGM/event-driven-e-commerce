from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "recipient", "status", "attempts", "sent_at"]
    list_filter = ["status", "kind"]
    search_fields = ["recipient", "event_id", "subject"]
    readonly_fields = [f.name for f in Notification._meta.fields]

    def has_add_permission(self, request):
        return False
