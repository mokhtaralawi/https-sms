from django.contrib import admin

from devices.models import Device, SimCard


class SimCardInline(admin.TabularInline):
    model = SimCard
    extra = 0


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ["device_uuid", "name", "customer", "model", "status", "connection_status", "last_seen", "battery_level"]
    list_filter = ["status", "connection_status", "network_type"]
    search_fields = ["device_uuid", "name", "model"]
    readonly_fields = ["device_uuid", "auth_token", "created_at", "updated_at"]
    inlines = [SimCardInline]


@admin.register(SimCard)
class SimCardAdmin(admin.ModelAdmin):
    list_display = ["phone_number", "device", "slot", "carrier", "country", "status", "messages_sent", "last_seen"]
    list_filter = ["status", "carrier"]
    search_fields = ["phone_number", "carrier"]