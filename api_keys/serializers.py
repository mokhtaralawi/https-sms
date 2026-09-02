from rest_framework import serializers

from api_keys.models import APIKey


class APIKeySerializer(serializers.ModelSerializer):
    key = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = APIKey
        fields = [
            "id", "name", "key_prefix", "key", "environment", "status",
            "last_used_at", "expires_at", "revoked_at", "created_at",
        ]
        read_only_fields = ["id", "key_prefix", "key", "environment", "status",
                            "last_used_at", "expires_at", "revoked_at", "created_at"]

    def get_key(self, obj):
        # Only present on creation (populated by the create view); otherwise None.
        key = getattr(obj, "_raw_key", None)
        return key


class APIKeyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ["name", "environment", "expires_at"]

    def validate_environment(self, value):
        if value not in [APIKey.Environment.TEST, APIKey.Environment.LIVE]:
            raise serializers.ValidationError("Environment must be TEST or LIVE.")
        return value


class APIKeyRevokeSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)