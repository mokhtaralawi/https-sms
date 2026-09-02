from django.contrib import admin

from messaging.models import IncomingMessage, Message, MessageAttempt

class MessageAttemptInline(admin.TabularInline):
    model = MessageAttempt
    extra = 0
    readonly_fields = ["attempt_number", "status", "error_code", "error_message", "created_at"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["public_id", "recipient", "status", "priority", "device", "sim_card", "created_at"]
    list_filter = ["status", "priority", "encoding"]
    search_fields = ["public_id", "recipient", "body"]
    readonly_fields = ["public_id", "queued_at", "assigned_at", "sending_at", "sent_at",
                       "delivered_at", "failed_at", "created_at", "updated_at"]
    inlines = [MessageAttemptInline]

    def has_change_permission(self, request, obj=None):
        # Read-only for safety in admin to avoid accidental mutation
        return True


@admin.register(MessageAttempt)
class MessageAttemptAdmin(admin.ModelAdmin):
    list_display = ["message", "attempt_number", "device", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["message__public_id"]


@admin.register(IncomingMessage)
class IncomingMessageAdmin(admin.ModelAdmin):
    list_display = ["public_id", "from_number", "to_number", "status", "received_at"]
    list_filter = ["status"]
    search_fields = ["public_id", "from_number", "body"]