from django.db import models

from core.models import UUIDModel, TimeStampedModel
from core.utils import datetime_now


class AuditLog(TimeStampedModel):
    ACTIONS = (
        ("login", "Login"),
        ("logout", "Logout"),
        ("api_key.create", "API Key created"),
        ("api_key.revoke", "API Key revoked"),
        ("device.register", "Device registered"),
        ("device.remove", "Device removed"),
        ("message.create", "Message created"),
        ("message.cancel", "Message cancelled"),
        ("webhook.create", "Webhook created"),
        ("settings.change", "Settings changed"),
        ("read", "Read"),
        ("other", "Other"),
    )

    action = models.CharField(max_length=50, db_index=True)
    resource_type = models.CharField(max_length=50, blank=True, default="")
    resource_id = models.CharField(max_length=64, blank=True, null=True)
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    status_code = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]
        verbose_name = "سجل تدقيق"
        verbose_name_plural = "سجلات التدقيق"

    def __str__(self):
        return f"{self.action} @ {self.created_at}"
