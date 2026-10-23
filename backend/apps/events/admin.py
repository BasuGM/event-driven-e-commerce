from django.contrib import admin

from .models import OutboxEvent, ProcessedEvent


class Unpublished(admin.SimpleListFilter):
    title = "published"
    parameter_name = "published"

    def lookups(self, request, model_admin):
        return [("no", "Unpublished"), ("yes", "Published")]

    def queryset(self, request, queryset):
        if self.value() == "no":
            return queryset.filter(published_at__isnull=True)
        if self.value() == "yes":
            return queryset.filter(published_at__isnull=False)
        return queryset


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ["occurred_at", "event_type", "aggregate_type", "aggregate_id", "published_at", "attempts"]
    list_filter = [Unpublished, "event_type"]
    search_fields = ["aggregate_id", "id"]
    ordering = ["-occurred_at"]

    # Read-only: events are written by services and published by the relay
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(admin.ModelAdmin):
    list_display = ["processed_at", "consumer", "event_id"]
    list_filter = ["consumer"]
    search_fields = ["event_id"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
