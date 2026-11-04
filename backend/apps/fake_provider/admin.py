from django.contrib import admin

from .models import FakeEvent, FakeIntent


@admin.register(FakeIntent)
class FakeIntentAdmin(admin.ModelAdmin):
    list_display = ["created_at", "id", "reference", "amount", "status", "expires_at"]
    search_fields = ["id", "reference"]


@admin.register(FakeEvent)
class FakeEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "id", "type", "intent", "delivery_attempts", "last_status"]
    search_fields = ["id", "intent__id"]
