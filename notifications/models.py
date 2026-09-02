from django.db import models
from django.utils import timezone

from core.models import UUIDModel, TimeStampedModel


class Notification(UUIDModel, TimeStampedModel):
    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        WEB = "WEB", "Web"

    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications")

    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.WEB)
    title = models.CharField(max_length=255)
    body = models.TextField()
    data = models.JSONField(default=dict, blank=True)

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "is_read"]),
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["channel"]),
        ]

    def __str__(self):
        return f"{self.channel} {self.title}"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])
