from django.contrib import admin

from customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "company_name", "email", "status", "plan", "created_at"]
    list_filter = ["status", "plan", "timezone"]
    search_fields = ["name", "company_name", "email", "phone"]
    readonly_fields = ["id", "created_at", "updated_at"]