import logging
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from core.utils import datetime_now
from messaging.tasks import process_message

logger = logging.getLogger("httpsms.messaging")


class MessageValidationError(APIException):
    status_code = 400
    default_detail = "Invalid message."
    default_code = "invalid_message"


class CustomerSuspended(APIException):
    status_code = 403
    default_detail = "Customer account is suspended."
    default_code = "customer_suspended"


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_phone_number(value: str) -> str:
    """Normalize a loosely-entered phone number to E.164-ish form.

    - Strips spaces, dashes, dots, parentheses.
    - Converts Arabic-Indic (٠-٩) and Persian (۰-۹) digits to Latin.
    - Converts a leading "00" to "+".
    - Preserves an existing leading "+".
    """
    if not value:
        return value
    s = value.strip()
    s = s.translate(_ARABIC_DIGITS).translate(_PERSIAN_DIGITS)
    s = "".join(ch for ch in s if ch.isdigit() or ch == "+" or ch == "*")
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.isdigit():
        s = "+" + s
    return s


def validate_recipient(recipient: str) -> str:
    """Basic E.164-ish validation for a phone number (tolerant normalization)."""
    recipient = normalize_phone_number(recipient)
    if len(recipient) < 8 or len(recipient) > 16:
        raise MessageValidationError({"to": "Invalid recipient phone number."})
    if not all(c.isdigit() or c in ("+", "*") for c in recipient):
        raise MessageValidationError({"to": "Recipient may only contain digits and a leading +."})
    if recipient.count("+") > 1 or (recipient.startswith("+") and len(recipient) < 8):
        raise MessageValidationError({"to": "Invalid recipient phone number."})
    return recipient


def validate_body(body) -> str:
    if not body or not body.strip():
        raise MessageValidationError({"message": "Message body is required."})
    if len(body) > 1600:
        raise MessageValidationError({"message": "Message body exceeds 1600 characters."})
    return body


def process_single_message(customer, api_key, to, body, *, priority="NORMAL",
                           scheduled_at=None, expires_at=None, idempotency_key=None,
                           max_attempts=None, is_bulk=False, bulk_group_id=None,
                           device_id=None, sim_id=None):
    """
    Create a Message and enqueue it for delivery.

    Returns (message, error) where error is an exception or None.
    """
    from messaging.models import Message
    from usage.tasks import record_usage

    # Idempotency: reusing the same key returns the existing message
    if idempotency_key:
        existing = Message.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
        if existing:
            return existing, None

    to = validate_recipient(to)
    body = validate_body(body)

    # Rate limiting

    from core.services.rate_limit import rate_limiter
    # Only count production messages toward limits
    allowed, metric = rate_limiter.check_customer_limits(customer)
    if not allowed:
        raise APIException(
            {"error": f"Rate limit exceeded: {metric}"}
        )

    message = Message(
        customer=customer,
        api_key=api_key,
        recipient=to,
        body=body,
        priority=priority,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts or 3,
        scheduled_at=scheduled_at,
        expires_at=expires_at or (datetime_now() + timedelta(days=1)),
        is_bulk=is_bulk,
        bulk_group_id=bulk_group_id,
        device_id=device_id,
        sim_card_id=sim_id,
    )
    message.transition(Message.Status.QUEUED)
    message.save()

    record_usage(str(customer.id), "API_REQUEST", api_key_id=str(api_key.id) if api_key else None)

    # Enqueue to Celery
    if scheduled_at:
        eta = scheduled_at
        process_message.apply_async(args=[str(message.id)], eta=eta)
    else:
        process_message.apply_async(args=[str(message.id)], priority=_celery_priority(priority))

    return message, None


def process_bulk_message(customer, api_key, recipients, body, *, priority="NORMAL",
                         idempotency_key=None, expires_at=None, max_attempts=None):
    """
    Create one Message per recipient and enqueue them all.
    """
    from messaging.models import Message

    bulk_group_id = uuid.uuid4()
    bulk_public = "bulk_" + uuid.uuid4().hex[:12]

    # Validate all recipients up-front
    validated = []
    for to in recipients:
        validated.append(validate_recipient(to))

    if idempotency_key:
        existing = Message.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
        if existing:
            return [existing], bulk_public, None

    messages = []
    for to in validated:
        message, err = process_single_message(
            customer,
            api_key,
            to,
            body,
            priority=priority,
            expires_at=expires_at or (datetime_now() + timedelta(days=1)),
            idempotency_key=(idempotency_key + f":{to}") if idempotency_key else None,
            max_attempts=max_attempts,
            is_bulk=True,
            bulk_group_id=bulk_group_id,
        )
        messages.append(message)

    # Store the bulk idempotency marker on first message
    if idempotency_key and messages:
        first = Message.objects.filter(customer=customer, bulk_group_id=bulk_group_id).first()
        if first:
            first.idempotency_key = idempotency_key
            first.save(update_fields=["idempotency_key"])

    return messages, bulk_public, None


def _celery_priority(priority: str) -> int:
    mapping = {"LOW": 5, "NORMAL": 4, "HIGH": 2, "URGENT": 0}
    return mapping.get(priority, 4)


def send_sms(customer, recipient, body, **kwargs):
    """Programmatic helper used by OTP service."""
    message, err = process_single_message(
        customer,
        api_key=None,
        to=recipient,
        body=body,
        priority=kwargs.get("priority", "NORMAL"),
        idempotency_key=kwargs.get("idempotency_key"),
    )
    return {"message_id": message.public_id, "status": message.status}


from datetime import timedelta  # noqa: E402
