from django.db import models

from core.models import UUIDModel, TimeStampedModel
from core.utils import datetime_now


class UsageRecord(UUIDModel, TimeStampedModel):
    class EventType(models.TextChoices):
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        RECEIVED = "RECEIVED", "Received"
        API_REQUEST = "API_REQUEST", "API Request"

    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="usage_records")
    device = models.ForeignKey("devices.Device", null=True, blank=True, on_delete=models.SET_NULL, related_name="usage_records")
    sim_card = models.ForeignKey("devices.SimCard", null=True, blank=True, on_delete=models.SET_NULL, related_name="usage_records")
    api_key = models.ForeignKey("api_keys.APIKey", null=True, blank=True, on_delete=models.SET_NULL, related_name="usage_records")
    message_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    event_type = models.CharField(max_length=20, choices=EventType.choices, db_index=True)
    occurred_at = models.DateTimeField(default=datetime_now, db_index=True)
    count = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["customer", "occurred_at"]),
            models.Index(fields=["customer", "event_type", "occurred_at"]),
            models.Index(fields=["device", "occurred_at"]),
            models.Index(fields=["sim_card", "occurred_at"]),
        ]
        verbose_name = "سجل استخدام"
        verbose_name_plural = "سجلات الاستخدام"

    def __str__(self):
        return f"{self.event_type} x{self.count} for {self.customer_id}"


class UsageSummary(UUIDModel, TimeStampedModel):
    class Period(models.TextChoices):
        DAILY = "DAILY", "Daily"
        MONTHLY = "MONTHLY", "Monthly"

    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="usage_summaries")
    period = models.CharField(max_length=10, choices=Period.choices)
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)

    sent = models.PositiveIntegerField(default=0)
    delivered = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    received = models.PositiveIntegerField(default=0)
    api_requests = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ["customer", "period", "period_start"]
        ordering = ["-period_start"]
        verbose_name = "ملخص استخدام"
        verbose_name_plural = "ملخصات الاستخدام"

    def __str__(self):
        return f"{self.customer_id} {self.period} {self.period_start}"
