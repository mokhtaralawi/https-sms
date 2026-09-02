from rest_framework import serializers

from otp.models import OTPRequest


class OTPSendSerializer(serializers.Serializer):
    to = serializers.CharField(max_length=20)
    purpose = serializers.CharField(required=False, default="authentication")
    length = serializers.IntegerField(min_value=4, max_value=8, required=False)

    def validate_to(self, value):
        value = value.strip()
        if not value.startswith("+"):
            value = "+" + value
        if len(value) < 8:
            raise serializers.ValidationError("Invalid phone number.")
        return value


class OTPVerifySerializer(serializers.Serializer):
    to = serializers.CharField(max_length=20)
    code = serializers.CharField(min_length=4, max_length=8)
    otp_id = serializers.CharField(required=False)
    purpose = serializers.CharField(required=False, default="authentication")

    def validate_to(self, value):
        value = value.strip()
        if not value.startswith("+"):
            value = "+" + value
        return value


class OTPResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = OTPRequest
        fields = ["id", "recipient", "purpose", "status", "created_at", "expires_at", "message_id"]