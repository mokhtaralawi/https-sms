from rest_framework import serializers

from audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "action", "resource_type", "resource_id", "user", "user_email",
                  "customer", "ip_address", "status_code", "created_at", "metadata"]
        read_only_fields = fields