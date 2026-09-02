import base64
import hashlib
import hmac
import json
import logging
import requests
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from core.utils import datetime_now

logger = logging.getLogger("httpsms.webhooks")


def compute_signature(secret: str, payload_str: str) -> str:
    """HMAC SHA-256 signature header value."""
    digest = hmac.new(secret.encode("utf-8"), payload_str.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


@shared_task
def fire_webhook_event(customer_id, event: str, payload: dict):
    """Queue webhook deliveries for an event."""
    from webhooks.services.dispatcher import WebhookDispatcher
    from customers.models import Customer

    customer = Customer.objects.filter(id=customer_id).first()
    if not customer:
        return
    WebhookDispatcher(customer, event, payload).ensure_notified()


@shared_task(
    bind=True,
    max_retries=settings.WEBHOOK_MAX_RETRIES,
    default_retry_delay=settings.WEBHOOK_BASE_DELAY,
    time_limit=30,
)
def send_webhook(self, delivery_id: str):
    from webhooks.models import WebhookDelivery

    try:
        delivery = WebhookDelivery.objects.select_related("webhook").get(id=delivery_id)
    except WebhookDelivery.DoesNotExist:
        return

    hook = delivery.webhook
    if not hook.is_active or hook.status != hook.Status.ACTIVE:
        delivery.status = WebhookDelivery.Status.FAILED
        delivery.error = "Webhook disabled"
        delivery.save(update_fields=["status", "error"])
        return

    payload = delivery.payload
    if isinstance(payload, dict):
        payload = {**payload, "timestamp": datetime_now().isoformat()}
    payload_str = json.dumps(payload, separators=(",", ":"))

    try:
        headers = {
            "Content-Type": "application/json",
            "X-SMS-Signature": compute_signature(hook.secret, payload_str),
            "X-SMS-Event": delivery.event,
            "X-SMS-Delivery-Id": str(delivery.idempotency_key),
        }
        timeout = hook.timeout or settings.WEBHOOK_TIMEOUT
        resp = requests.post(hook.url, data=payload_str, headers=headers, timeout=timeout)

        if resp.status_code < 400:
            delivery.attempts += 1
            delivery.status = WebhookDelivery.Status.DELIVERED
            delivery.response_status = resp.status_code
            delivery.response_body = resp.text[:2000]
            delivery.delivered_at = datetime_now()
            delivery.save()
            hook.notify_success()
            logger.info("Webhook delivered idempotency=%s status=%s", delivery.idempotency_key, resp.status_code)
        else:
            raise requests.HTTPError(f"HTTP {resp.status_code}")
    except Exception as exc:
        delivery.attempts += 1
        delivery.error = str(exc)[:1000]
        delivery.save(update_fields=["attempts", "error"])
        hook.notify_failure()

        if delivery.attempts >= settings.WEBHOOK_MAX_RETRIES:
            delivery.status = WebhookDelivery.Status.DEAD
            delivery.save(update_fields=["status"])
            logger.error("Webhook moved to dead letter: %s", delivery.id)
            # Optionally queue for manual review / alerting
            move_to_dead_letter.delay(str(delivery.id))
            return

        # Exponential backoff
        backoff = settings.WEBHOOK_BASE_DELAY * (2 ** delivery.attempts)
        delivery.next_retry_at = datetime_now() + timedelta(seconds=backoff)
        delivery.save(update_fields=["next_retry_at"])
        raise self.retry(exc=exc, countdown=backoff)


@shared_task()
def move_to_dead_letter(delivery_id: str):
    """Dead Letter Queue handling - could send a notification to admins."""
    from webhooks.models import WebhookDelivery

    try:
        delivery = WebhookDelivery.objects.select_related("webhook").get(id=delivery_id)
    except WebhookDelivery.DoesNotExist:
        return
    logger.error("Dead letter webhook: %s event=%s webhook=%s", delivery.id, delivery.event, delivery.webhook.url)
