from django.contrib import admin

from api_keys.models import APIKey

@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ["name", "customer", "key_prefix", "environment", "status", "last_used_at", "created_at"]
    list_filter = ["environment", "status"]
    search_fields = ["name", "key_prefix"]
    readonly_fields = ["id", "hash_preview", "created_at", "updated_at"]

    def hash_preview(self, obj):
        return f"{obj.hashed_key[:16]}..." if obj.hashed_key else ""

    hash_preview.short_description = "Key hash (preview)"