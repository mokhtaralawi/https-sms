import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import UUIDModel, TimeStampedModel


def generate_api_key(environment) -> tuple:
    """
    Generate a new API key.

    Returns (raw_key, hashed_key, prefix)
    """
    if environment == "LIVE":
        prefix = "sk_live_"
    else:
        prefix = "sk_test_"
    raw = prefix + secrets.token_urlsafe(32)
    hashed = hash_api_key(raw)
    return raw, hashed, prefix


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class APIKey(UUIDModel, TimeStampedModel):
    class Environment(models.TextChoices):
        TEST = "TEST", "Test"
        LIVE = "LIVE", "Live"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        REVOKED = "REVOKED", "Revoked"
        EXPIRED = "EXPIRED", "Expired"

    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=255)
    key_prefix = models.CharField(max_length=20, editable=False)
    hashed_key = models.CharField(max_length=64, unique=True, editable=False, db_index=True)
    environment = models.CharField(max_length=10, choices=Environment.choices, default=Environment.LIVE, db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["environment", "status"]),
        ]
        verbose_name = "مفتاح API"
        verbose_name_plural = "مفاتيح API"

    def __str__(self):
        return f"{self.key_prefix}{self.name} ({self.environment})"

    @property
    def is_active(self) -> bool:
        if self.status != self.Status.ACTIVE:
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        return True

    def touch_used(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at", "updated_at"])

    def revoke(self):
        self.status = self.Status.REVOKED
        self.revoked_at = timezone.now()
        self.save(update_fields=["status", "revoked_at", "updated_at"])

    @classmethod
    def create_for_customer(cls, customer, name, environment="LIVE", expires_in_days=None):
        raw, hashed, prefix = generate_api_key(environment)
        obj = cls.objects.create(
            customer=customer,
            name=name,
            key_prefix=prefix,
            hashed_key=hashed,
            environment=environment,
            expires_at=(timezone.now() + timedelta(days=expires_in_days)) if expires_in_days else None,
        )
        return obj, raw

    @classmethod
    def find_by_raw_key(cls, raw_key: str):
        if not raw_key:
            return None
        hashed = hash_api_key(raw_key)
        try:
            return cls.objects.get(hashed_key=hashed)
        except cls.DoesNotExist:
            return None
