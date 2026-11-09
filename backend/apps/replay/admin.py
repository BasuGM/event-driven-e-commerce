from django.contrib import admin

from .models import ReplayRun


@admin.register(ReplayRun)
class ReplayRunAdmin(admin.ModelAdmin):
    list_display = ["id", "status", "date_from", "date_to", "speed", "orders_created", "steps_applied", "started_at", "finished_at"]
    list_filter = ["status"]
    readonly_fields = [f.name for f in ReplayRun._meta.fields]
