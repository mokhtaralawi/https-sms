from django.contrib import admin

from otp.models import OTPRequest

@admin.register(OTPRequest)
class OTPRequestAdmin(admin.ModelAdmin):
    list_display = ["recipient", "purpose", "customer", "status", "attempts", "created_at", "expires_at"]
    list_filter = ["status", "purpose"]
    search_fields = ["recipient"]