import hashlib
import secrets

from django.conf import settings
from django.db import models

from core.models import UUIDModel, TimeStampedModel
from core.utils import datetime_now


class OTPRequest(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        EXPIRED = "EXPIRED", "Expired"
        USED = "USED", "Used"

    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="otp_requests")
    recipient = models.CharField(max_length=20, db_index=True)
    purpose = models.CharField(max_length=50, default="authentication")

    hashed_code = models.CharField(max_length=64, editable=False)
    code_prefix = models.CharField(max_length=8, blank=True, default="")

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    message_id = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "recipient"]),
            models.Index(fields=["status", "expires_at"]),
        ]
        verbose_name = "طلب رمز تحقق"
        verbose_name_plural = "طلبات رمز التحقق"

    def __str__(self):
        return f"{self.recipient} {self.purpose} ({self.status})"

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= datetime_now()

    def verify(self, code: str) -> bool:
        if self.status != self.Status.PENDING or self.is_expired:
            return False
        if self.attempts >= settings.OTP_MAX_ATTEMPTS:
            self.status = self.Status.EXPIRED
            self.save(update_fields=["status"])
            return False

        hashed = hashlib.sha256(code.encode("utf-8")).hexdigest()
        self.attempts += 1
        if hashed == self.hashed_code:
            self.status = self.Status.VERIFIED
            self.used_at = datetime_now()
            self.save(update_fields=["status", "used_at", "attempts"])
            return True
        self.save(update_fields=["attempts"])
        return False


def generate_otp_code(length=None) -> str:
    length = length or settings.OTP_CODE_LENGTH
    # Avoid leading-zero issues; use secrets for randomness
    return "".join(str(secrets.randbelow(10)) for _ in range(length))
