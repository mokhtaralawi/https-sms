from django.db import models

from core.models import UUIDModel, TimeStampedModel, StatusModel


class Customer(UUIDModel, TimeStampedModel, StatusModel):
    name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    timezone = models.CharField(max_length=64, default="UTC")

    # Default rate limits can be overridden per customer
    rate_rps = models.PositiveIntegerField(default=None, null=True, blank=True)
    rate_per_min = models.PositiveIntegerField(default=None, null=True, blank=True)
    rate_per_hour = models.PositiveIntegerField(default=None, null=True, blank=True)
    rate_per_day = models.PositiveIntegerField(default=None, null=True, blank=True)
    rate_per_month = models.PositiveIntegerField(default=None, null=True, blank=True)

    # Subscription / plan
    plan = models.CharField(max_length=50, default="free")
    max_devices = models.PositiveIntegerField(default=10)
    max_api_keys = models.PositiveIntegerField(default=10)

    owner = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_customers",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["email"]),
        ]
        verbose_name_plural = "Customers"

    def __str__(self):
        return self.name

    def get_rate_limits(self) -> dict:
        from django.conf import settings

        return {
            "rps": self.rate_rps or settings.RATE_LIMIT_DEFAULT_RPS,
            "per_min": self.rate_per_min or settings.RATE_LIMIT_DEFAULT_PER_MIN,
            "per_hour": self.rate_per_hour or settings.RATE_LIMIT_DEFAULT_PER_HOUR,
            "per_day": self.rate_per_day or settings.RATE_LIMIT_DEFAULT_PER_DAY,
            "per_month": self.rate_per_month or settings.RATE_LIMIT_DEFAULT_PER_MONTH,
        }
