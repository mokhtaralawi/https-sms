from rest_framework import serializers

from usage.models import UsageRecord, UsageSummary


class UsageRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageRecord
        fields = ["id", "event_type", "occurred_at", "count", "device_id",
                  "sim_card_id", "api_key_id", "message_id", "metadata"]
        read_only_fields = fields


class UsageSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageSummary
        fields = ["id", "period", "period_start", "period_end", "sent", "delivered",
                  "failed", "received", "api_requests"]
        read_only_fields = fields