import uuid
from django.db import models
from django.utils import timezone


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_index=True)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class StatusModel(models.Model):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"
    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (SUSPENDED, "Suspended"),
        (DISABLED, "Disabled"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_active(self) -> bool:
        return self.status == self.ACTIVE
