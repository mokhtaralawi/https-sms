from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from devices.models import Device, SimCard


class SimCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = SimCard
        fields = ["id", "device", "slot", "phone_number", "carrier", "country",
                  "status", "sms_capability", "receive_capability", "last_seen",
                  "messages_sent", "created_at"]
        read_only_fields = ["id", "messages_sent", "last_seen", "created_at"]


class DeviceSerializer(serializers.ModelSerializer):
    sim_cards = SimCardSerializer(many=True, read_only=True)

    class Meta:
        model = Device
        fields = [
            "id", "device_uuid", "customer", "name", "model", "manufacturer",
            "android_version", "app_version", "status", "connection_status",
            "last_seen", "battery_level", "network_type", "ip_address",
            "selection_policy", "created_at", "sim_cards",
        ]
        read_only_fields = [
            "id", "device_uuid", "customer", "status", "connection_status", "last_seen",
            "ip_address", "created_at",
        ]


class DeviceRegisterSerializer(serializers.Serializer):
    """Issued to the Android app once; contains token + uuid."""
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    model = serializers.CharField(required=False, allow_blank=True, max_length=255)
    manufacturer = serializers.CharField(required=False, allow_blank=True, max_length=255)
    android_version = serializers.CharField(required=False, allow_blank=True, max_length=64)
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=20)

    def validate_phone_number(self, value):
        if not value:
            return value
        digits = "".join(ch for ch in value if ch.isdigit() or ch == "+")
        if not any(ch.isdigit() for ch in digits):
            raise ValidationError("phone_number must contain digits")
        return digits[:20]