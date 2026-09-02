import logging
from datetime import timedelta
from uuid import uuid4

from asgiref.sync import async_to_sync
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.utils import datetime_now

logger = logging.getLogger("httpsms.messaging")


def _get_redis_for_channel():
    """Obtain a Redis client usable to publish to the device channel."""
    from redis import Redis
    from django.core.cache import cache

    try:
        return cache.client.get_client()
    except Exception:
        pass

    # Build from settings URL
    from urllib.parse import urlparse

    url = urlparse(settings.REDIS_URL)
    return Redis(host=url.hostname, port=url.port or 6379, db=int(url.path.lstrip("/") or 0))


@shared_task
def process_message(message_id: str):
    """
    Core job: select a device, assign the message, and dispatch the SMS job
    to the device over the WebSocket channel.
    """
    from messaging.models import Message, MessageAttempt
    from devices.services.selection import DeviceSelectionEngine, DeviceSelectionError

    requeue_countdown = None
    attempt = None
    message = None

    with transaction.atomic():
        message = Message.objects.select_for_update().filter(id=message_id, status=Message.Status.QUEUED).first()
        if not message:
            logger.info("process_message: message %s not in QUEUED state", message_id)
            return

        # Expiration check
        if message.expires_at and message.expires_at <= datetime_now():
            message.transition(Message.Status.EXPIRED, error_code="expired", error_message="Message expired")
            message.save()
            _notify_message_event(message, "message.failed")
            return

        # Device selection
        policy = message.device_id and "specific_device" or "least_used"
        engine = DeviceSelectionEngine(
            customer=message.customer,
            policy=policy,
            device_id=str(message.device_id) if message.device_id else None,
            sim_id=str(message.sim_card_id) if message.sim_card_id else None,
        )

        try:
            device, sim = engine.select()
        except DeviceSelectionError:
            # Requeue later if no device right now; otherwise fail.
            message.attempts += 1
            message.save(update_fields=["attempts"])
            if message.attempts >= message.max_attempts:
                message.transition(Message.Status.FAILED, error_code="no_device",
                                   error_message="No device available after retries")
                message.save()
                _notify_message_event(message, "message.failed")
                return
            requeue_countdown = 10 * (2 ** message.attempts)
            return

        # Assign message to device+sim
        message.attempts += 1
        message.device = device
        message.sim_card = sim
        message.transition(Message.Status.ASSIGNED)
        message.save()

        attempt = MessageAttempt.objects.create(
            message=message,
            device=device,
            sim_card=sim,
            attempt_number=message.attempts,
            status=Message.Status.ASSIGNED,
        )

    if requeue_countdown is not None:
        # Saved successfully (committed above); now ask Celery for a retry.
        raise process_message.retry(countdown=requeue_countdown)

    # Dispatch job to device (outside the lock)
    sent_ok = _dispatch_to_device(message, attempt)
    if sent_ok:
        return
    # If dispatch failed to reach device channel, mark attempt and retry
    attempt.status = Message.Status.FAILED
    attempt.error_message = "Device channel unavailable"
    attempt.save(update_fields=["status", "error_message"])

    if message.attempts >= message.max_attempts:
        message.transition(Message.Status.FAILED, error_code="channel_unavailable",
                           error_message="Could not reach device")
        message.save()
        _notify_message_event(message, "message.failed")
    else:
        message.device = None
        message.sim_card = None
        message.transition(Message.Status.QUEUED)
        message.save()
        raise process_message.retry(countdown=15 * (2 ** message.attempts))


def _dispatch_to_device(message, attempt) -> bool:
    """Send the SMS job to a device via its WebSocket channel group."""
    try:
        from messaging.models import Message
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return False

        job_id = str(uuid4())
        attempt.device_job_id = job_id
        attempt.save(update_fields=["device_job_id"])

        message.transition(Message.Status.SENDING, sending_at=datetime_now())
        message.save(update_fields=["status", "sending_at"])
        _notify_message_event(message, "message.sending")

        payload = {
            "type": "sms.send",
            "message_id": message.public_id,
            "to": message.recipient,
            "body": message.body,
            "job_id": job_id,
            "sim_slot": message.sim_card.slot if message.sim_card else None,
        }

        async_to_sync(channel_layer.group_send)(
            f"device_{message.device.device_uuid}",
            {"type": "sms.send", "message": payload},
        )
        return True
    except Exception as exc:
        logger.warning("Failed to dispatch to device %s: %s", message.device_id, exc)
        return False


def _notify_message_event(message, event: str):
    """Fire webhook for a message event."""
    from webhooks.tasks import fire_webhook_event

    payload = {
        "message_id": message.public_id,
        "status": message.status,
        "recipient": message.recipient,
        "customer_id": str(message.customer_id),
    }
    try:
        fire_webhook_event.delay(str(message.customer_id), event, payload)
    except Exception as exc:  # pragma: no cover
        logger.warning("Webhook fire failed: %s", exc)


@shared_task
def requeue_stale_sending_messages():
    """
    Find messages stuck in SENDING (device disconnected mid-send) and requeue them.
    """
    from messaging.models import Message

    cutoff = datetime_now() - timedelta(minutes=5)
    stale = Message.objects.filter(status=Message.Status.SENDING, sending_at__lte=cutoff)
    for message in stale:
        message.device = None
        message.sim_card = None
        message.transition(Message.Status.QUEUED)
        message.save()
        process_message.delay(str(message.id))


@shared_task
def check_expired_messages():
    from messaging.models import Message

    now = datetime_now()
    expired = Message.objects.filter(expires_at__lte=now, status__in=[
        Message.Status.QUEUED, Message.Status.ASSIGNED, Message.Status.SENDING
    ])
    for message in expired:
        message.transition(Message.Status.EXPIRED, error_code="expired", error_message="Message expired")
        message.save()
        _notify_message_event(message, "message.failed")


@shared_task
def handle_sms_result(result):
    """
    Handle the result of an SMS send received from an Android device.

    result keys: message_id (public id), status, provider_message_id, error_code, error_message
    """
    from messaging.models import Message, MessageAttempt

    public_id = result.get("message_id")
    if not public_id:
        return

    message = Message.objects.filter(public_id=public_id).select_for_update().first()
    if not message:
        return

    inbound_status = result.get("status", "").lower()
    if inbound_status == "sent":
        message.provider_message_id = result.get("provider_message_id", message.provider_message_id)
        message.transition(Message.Status.SENT)
        message.save()
        _notify_message_event(message, "message.sent")
    elif inbound_status == "delivered":
        message.provider_message_id = result.get("provider_message_id", message.provider_message_id)
        message.transition(Message.Status.DELIVERED)
        message.save()
        _notify_message_event(message, "message.delivered")
    elif inbound_status in ("failed", "error"):
        _message_failed(message, result)
    else:
        # Unknown status, treat as sent
        message.transition(Message.Status.SENT)
        message.save()
        _notify_message_event(message, "message.sent")


def _message_failed(message, result):
    from messaging.models import Message
    from webhooks.tasks import fire_webhook_event

    message.attempts += 1  # account for the attempt that just failed
    attempt_status = result.get("status", "failed")
    message.error_code = result.get("error_code", attempt_status)
    message.error_message = result.get("error_message", "Device reported failure")[:500]

    if message.attempts >= message.max_attempts or result.get("fatal"):
        message.transition(Message.Status.FAILED)
        message.save()
        fire_webhook_event.delay(
            str(message.customer_id), "message.failed",
            {"message_id": message.public_id, "status": "failed", "recipient": message.recipient}
        )
    else:
        message.transition(Message.Status.QUEUED, device=None, sim_card=None)
        message.save()
        process_message.delay(str(message.id))
