from django.contrib import admin

from usage.models import UsageRecord, UsageSummary


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ["event_type", "customer", "device", "sim_card", "occurred_at"]
    list_filter = ["event_type"]
    search_fields = ["customer__name"]
    readonly_fields = ["id", "created_at"]


@admin.register(UsageSummary)
class UsageSummaryAdmin(admin.ModelAdmin):
    list_display = ["customer", "period", "period_start", "sent", "delivered", "failed", "received"]
    list_filter = ["period"]
    search_fields = ["customer__name"]