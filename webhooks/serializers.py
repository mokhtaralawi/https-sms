from django.utils.crypto import get_random_string
from rest_framework import serializers

from webhooks.models import Webhook, WebhookDelivery


class WebhookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = [
            "id", "name", "url", "secret", "events", "status", "is_active",
            "version", "timeout", "max_retries", "last_sent_at", "last_success_at",
            "last_failure_at", "failure_count", "success_count", "created_at",
        ]
        read_only_fields = [
            "id", "secret", "last_sent_at", "last_success_at", "last_failure_at",
            "failure_count", "success_count", "created_at", "status",
        ]

    def validate_events(self, value):
        valid = set(self.Meta.model.EVENT_TYPES)
        if "*" in value:
            return ["*"]
        if not value:
            raise serializers.ValidationError("At least one event is required.")
        for e in value:
            if e not in valid:
                raise serializers.ValidationError(f"Unknown event: {e}")
        return value


class WebhookCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = ["name", "url", "events", "version", "timeout", "max_retries"]

    def validate_events(self, value):
        valid = set(Webhook.EVENT_TYPES)
        if "*" in value:
            return ["*"]
        if not value:
            raise serializers.ValidationError("At least one event is required.")
        for e in value:
            if e not in valid:
                raise serializers.ValidationError(f"Unknown event: {e}")
        return value

    def create(self, validated_data):
        validated_data["secret"] = get_random_string(32)
        return super().create(validated_data)


class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = ["id", "event", "status", "attempts", "response_status", "error",
                  "next_retry_at", "delivered_at", "created_at"]
        read_only_fields = fields