import uuid

from django.db import models

from core.models import UUIDModel, TimeStampedModel
from core.utils import datetime_now


class Message(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        ASSIGNED = "ASSIGNED", "Assigned"
        SENDING = "SENDING", "Sending"
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"

    class Encoding(models.TextChoices):
        GSM_7BIT = "GSM_7BIT", "GSM 7-bit"
        UCS_2 = "UCS_2", "UCS-2"
        AUTO = "AUTO", "Auto"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    # Instead of using the UUIDModel id directly, we use an internal string id like msg_xxxx
    public_id = models.CharField(max_length=64, unique=True, editable=False, db_index=True)

    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="messages")
    api_key = models.ForeignKey("api_keys.APIKey", null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    device = models.ForeignKey("devices.Device", null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")
    sim_card = models.ForeignKey("devices.SimCard", null=True, blank=True, on_delete=models.SET_NULL, related_name="messages")

    recipient = models.CharField(max_length=20, db_index=True)
    sender = models.CharField(max_length=20, blank=True, default="")
    body = models.TextField()
    encoding = models.CharField(max_length=20, choices=Encoding.choices, default=Encoding.AUTO, db_index=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL, db_index=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)

    idempotency_key = models.CharField(max_length=128, blank=True, null=True, db_index=True)

    scheduled_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    queued_at = models.DateTimeField(null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    sending_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.CharField(max_length=500, blank=True, default="")

    provider_message_id = models.CharField(max_length=128, blank=True, default="")

    is_bulk = models.BooleanField(default=False)
    bulk_group_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["recipient"]),
            models.Index(fields=["idempotency_key", "customer"]),
            models.Index(fields=["device", "status"]),
        ]
        verbose_name = "رسالة"
        verbose_name_plural = "الرسائل"

    def __str__(self):
        return f"{self.public_id} -> {self.recipient} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = "msg_" + uuid.uuid4().hex[:16]
        super().save(*args, **kwargs)

    @classmethod
    def get_message_id(cls) -> str:
        return "msg_" + uuid.uuid4().hex[:16]

    # --- State transition helpers ---

    def transition(self, new_status, caller=None, **fields):
        """Set status and record the relevant timestamp."""
        self.status = new_status
        ts = datetime_now()
        mapping = {
            Message.Status.QUEUED: lambda: setattr(self, "queued_at", self.queued_at or ts),
            Message.Status.ASSIGNED: lambda: setattr(self, "assigned_at", ts),
            Message.Status.SENDING: lambda: setattr(self, "sending_at", ts),
            Message.Status.SENT: lambda: setattr(self, "sent_at", ts),
            Message.Status.DELIVERED: lambda: setattr(self, "delivered_at", ts),
            Message.Status.FAILED: lambda: setattr(self, "failed_at", ts),
            Message.Status.EXPIRED: lambda: setattr(self, "failed_at", ts),
        }
        mapper = mapping.get(new_status)
        if mapper:
            mapper()
        for key, value in fields.items():
            setattr(self, key, value)
        return self


class MessageAttempt(UUIDModel, TimeStampedModel):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attempt_records")
    device = models.ForeignKey("devices.Device", null=True, blank=True, on_delete=models.SET_NULL, related_name="message_attempts")
    sim_card = models.ForeignKey("devices.SimCard", null=True, blank=True, on_delete=models.SET_NULL, related_name="message_attempts")
    attempt_number = models.PositiveIntegerField(default=1)

    status = models.CharField(max_length=20, choices=Message.Status.choices, default=Message.Status.QUEUED, db_index=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.CharField(max_length=500, blank=True, default="")
    provider_message_id = models.CharField(max_length=128, blank=True, default="")

    # WebSocket job tracking: the device ack id
    device_job_id = models.CharField(max_length=128, blank=True, default="")

    response_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["attempt_number"]
        indexes = [
            models.Index(fields=["message", "status"]),
        ]
        verbose_name = "محاولة إرسال"
        verbose_name_plural = "محاولات الإرسال"

    def __str__(self):
        return f"Attempt {self.attempt_number} for {self.message_id} ({self.status})"


class IncomingMessage(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        WEBHOOK_SENT = "WEBHOOK_SENT", "Webhook Sent"
        WEBHOOK_FAILED = "WEBHOOK_FAILED", "Webhook Failed"
        IGNORED = "IGNORED", "Ignored"

    public_id = models.CharField(max_length=64, unique=True, editable=False, db_index=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="incoming_messages")
    device = models.ForeignKey("devices.Device", null=True, blank=True, on_delete=models.SET_NULL, related_name="incoming_messages")
    sim_card = models.ForeignKey("devices.SimCard", null=True, blank=True, on_delete=models.SET_NULL, related_name="incoming_messages")

    from_number = models.CharField(max_length=20, db_index=True)
    to_number = models.CharField(max_length=20, db_index=True)
    body = models.TextField()
    received_at = models.DateTimeField(default=datetime_now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED, db_index=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["customer", "received_at"]),
            models.Index(fields=["from_number"]),
        ]
        verbose_name = "رسالة واردة"
        verbose_name_plural = "الرسائل الواردة"

    def __str__(self):
        return f"From {self.from_number} to {self.to_number}"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = "inc_" + uuid.uuid4().hex[:16]
        super().save(*args, **kwargs)
