from django.contrib import admin

from notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "channel", "customer", "user", "is_read", "created_at"]
    list_filter = ["channel", "is_read"]
    search_fields = ["title"]