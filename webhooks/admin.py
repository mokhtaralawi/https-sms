from django.contrib import admin

from webhooks.models import Webhook, WebhookDelivery


class WebhookDeliveryInline(admin.TabularInline):
    model = WebhookDelivery
    extra = 0
    readonly_fields = ["event", "status", "attempts", "response_status", "error", "created_at"]


@admin.register(Webhook)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ["name", "customer", "url", "status", "is_active", "success_count", "failure_count"]
    list_filter = ["status", "is_active"]
    search_fields = ["name", "url"]
    readonly_fields = ["secret", "created_at", "updated_at"]
    inlines = [WebhookDeliveryInline]


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ["event", "webhook", "status", "attempts", "response_status", "created_at"]
    list_filter = ["status", "event"]
    search_fields = ["webhook__name", "event"]