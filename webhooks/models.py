import hashlib
import hmac
import json

from django.conf import settings
from django.db import models

from core.models import UUIDModel, TimeStampedModel
from core.utils import datetime_now


class Webhook(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DISABLED = "DISABLED", "Disabled"

    EVENT_TYPES = (
        "message.queued",
        "message.sending",
        "message.sent",
        "message.delivered",
        "message.failed",
        "message.received",
        "device.online",
        "device.offline",
    )

    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="webhooks")
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=128)
    events = models.JSONField(default=list, blank=True)  # list of event strings

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    is_active = models.BooleanField(default=True)

    version = models.CharField(max_length=10, default="v1")
    timeout = models.PositiveIntegerField(default=None, null=True, blank=True)
    max_retries = models.PositiveIntegerField(default=None, null=True, blank=True)

    last_sent_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    failure_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
        ]
        verbose_name = "ويب هوك"
        verbose_name_plural = "ويب هوكس"

    def __str__(self):
        return f"{self.name} ({self.url})"

    def subscribes_to(self, event: str) -> bool:
        return event in self.events or "*" in self.events

    def compute_signature(self, payload_str: str) -> str:
        """HMAC-SHA256 signature of the payload using the webhook secret."""
        return hmac.new(
            self.secret.encode("utf-8"),
            payload_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def notify_failure(self):
        self.failure_count += 1
        self.last_failure_at = datetime_now()
        self.save(update_fields=["failure_count", "last_failure_at", "updated_at"])

    def notify_success(self):
        self.success_count += 1
        self.last_success_at = datetime_now()
        self.last_sent_at = datetime_now()
        self.save(update_fields=["success_count", "last_success_at", "last_sent_at", "updated_at"])


class WebhookDelivery(UUIDModel, TimeStampedModel):
    EVENT_TYPES = sorted(set(Webhook.EVENT_TYPES))

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        DEAD = "DEAD", "Dead Letter"

    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name="deliveries")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="webhook_deliveries")

    event = models.CharField(max_length=30, db_index=True)
    payload = models.JSONField(default=dict)
    idempotency_key = models.CharField(max_length=128, db_index=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True, default="")
    error = models.CharField(max_length=1000, blank=True, default="")

    next_retry_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_retry_at"]),
            models.Index(fields=["webhook", "status"]),
        ]
        verbose_name = "تسليم ويب هوك"
        verbose_name_plural = "عمليات تسليم ويب هوك"

    def __str__(self):
        return f"{self.event} -> {self.webhook_id} ({self.status})"
