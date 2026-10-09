from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["external_id", "city", "state", "zip_code_prefix"]
    list_filter = ["state"]
    search_fields = ["external_id", "city", "zip_code_prefix"]
