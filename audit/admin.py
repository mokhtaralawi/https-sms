from django.contrib import admin

from audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "user", "customer", "resource_type", "created_at"]
    list_filter = ["action"]
    search_fields = ["user__email", "resource_id"]
    readonly_fields = [f.name for f in AuditLog._meta.fields]