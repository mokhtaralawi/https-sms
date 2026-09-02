from rest_framework import serializers

from messaging.models import IncomingMessage, Message, MessageAttempt


class MessageCreateSerializer(serializers.Serializer):
    to = serializers.CharField(max_length=20)
    message = serializers.CharField(max_length=1600)
    priority = serializers.ChoiceField(choices=Message.Priority.choices, default=Message.Priority.NORMAL, required=False)
    scheduled_at = serializers.DateTimeField(required=False)
    expires_at = serializers.DateTimeField(required=False)
    max_attempts = serializers.IntegerField(min_value=1, max_value=10, required=False)
    device_id = serializers.CharField(required=False, allow_null=True)
    sim_id = serializers.CharField(required=False, allow_null=True)
    sender = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_to(self, value):
        value = value.strip()
        if not value.startswith("+") and not value.startswith("00"):
            value = "+" + value
        if len(value) < 8 or len(value) > 16:
            raise serializers.ValidationError("Invalid recipient phone number.")
        if not all(c.isdigit() or c == "+" for c in value):
            raise serializers.ValidationError("Recipient may only contain digits and a leading +.")
        return value


class MessageBulkCreateSerializer(serializers.Serializer):
    recipients = serializers.ListField(child=serializers.CharField(max_length=20), allow_empty=False)
    message = serializers.CharField(max_length=1600)
    priority = serializers.ChoiceField(choices=Message.Priority.choices, default=Message.Priority.NORMAL, required=False)
    scheduled_at = serializers.DateTimeField(required=False)
    expires_at = serializers.DateTimeField(required=False)

    def validate_recipients(self, value):
        if len(value) > 1000:
            raise serializers.ValidationError("Too many recipients (max 1000).")
        cleaned = []
        for item in value:
            item = item.strip()
            if not item.startswith("+") and not item.startswith("00"):
                item = "+" + item
            if len(item) < 8 or len(item) > 16:
                raise serializers.ValidationError("Invalid recipient phone number.")
            if not all(c.isdigit() or c == "+" for c in item):
                raise serializers.ValidationError("Recipient may only contain digits and a leading +.")
            cleaned.append(item)
        return cleaned


class MessageSerializer(serializers.ModelSerializer):
    attempts_count = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id", "public_id", "recipient", "sender", "body", "encoding", "priority",
            "status", "attempts", "max_attempts", "error_code", "error_message",
            "device_id", "sim_card_id", "scheduled_at", "queued_at", "sent_at",
            "delivered_at", "failed_at", "created_at", "attempts_count", "bulk_group_id",
        ]
        read_only_fields = fields

    def get_attempts_count(self, obj):
        return obj.attempt_records.count()


class MessageAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageAttempt
        fields = ["id", "attempt_number", "status", "error_code", "error_message",
                  "device", "sim_card", "provider_message_id", "created_at", "response_at"]
        read_only_fields = fields
        depth = 0


class IncomingMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomingMessage
        fields = ["id", "public_id", "from_number", "to_number", "body", "received_at",
                  "status", "device_id", "sim_card_id"]
        read_only_fields = fields


class MessageCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)