import hashlib
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache

from core.utils import datetime_now


class OTPError(Exception):
    pass


class OTPService:
    """Create and verify one-time passwords with rate limiting."""

    SEND_LIMIT_SECONDS = 60  # one send per 60s per recipient

    @classmethod
    def send(cls, customer, recipient: str, purpose: str = "authentication") -> dict:
        """Generate an OTP, queue sending via SMS, and return delivery info."""
        from otp.models import OTPRequest, generate_otp_code
        from messaging.services.sender import send_sms  # noqa: F401 (to trigger ready check)
        from messaging.tasks import process_message

        # Rate limit per recipient
        rl_key = f"otp:send:{customer.id}:{recipient}"
        if cache.get(rl_key):
            raise OTPError("Please wait before requesting another code.")

        code = generate_otp_code()
        hashed = hashlib.sha256(code.encode("utf-8")).hexdigest()

        otp = OTPRequest.objects.create(
            customer=customer,
            recipient=recipient,
            purpose=purpose,
            hashed_code=hashed,
            code_prefix=code[:2],
            expires_at=datetime_now() + timedelta(seconds=settings.OTP_EXPIRY_SECONDS),
        )
        cache.set(rl_key, 1, timeout=cls.SEND_LIMIT_SECONDS)

        # Queue the SMS. We won't return the code to the client.
        body = f"Your verification code is {code}. Valid for {settings.OTP_EXPIRY_SECONDS // 60} minutes."

        # Enqueue a message via Celery
        result = send_sms(customer, recipient, body, purpose=f"otp:{purpose}", otp=otp)
        otp.message_id = result.get("message_id", "")
        otp.save(update_fields=["message_id"])

        return {"otp_id": str(otp.id), "message_id": otp.message_id}

    @classmethod
    def verify(cls, customer, recipient: str, code: str, otp_id: str = None, purpose: str = "authentication") -> bool:
        from otp.models import OTPRequest

        qs = OTPRequest.objects.filter(customer=customer, recipient=recipient, purpose=purpose)
        if otp_id:
            qs = qs.filter(id=otp_id)
        otp = qs.order_by("-created_at").first()
        if not otp:
            raise OTPError("No pending OTP found.")
        return otp.verify(code)


def create_otp_for_testing(customer, recipient, purpose="authentication"):
    """Helper for tests: returns (otp_obj, code)."""
    from otp.models import OTPRequest, generate_otp_code

    code = generate_otp_code()
    otp = OTPRequest.objects.create(
        customer=customer,
        recipient=recipient,
        purpose=purpose,
        hashed_code=hashlib.sha256(code.encode("utf-8")).hexdigest(),
        code_prefix=code[:2],
        expires_at=datetime_now() + timedelta(seconds=3600),
    )
    return otp, code
