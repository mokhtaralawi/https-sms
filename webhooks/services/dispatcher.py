import json
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.utils import datetime_now

logger = logging.getLogger("httpsms.webhooks")


class WebhookDispatcher:
    """
    Dispatches event payloads to subscribed webhooks.
    """

    def __init__(self, customer, event: str, payload: dict):
        self.customer = customer
        self.event = event
        self.payload = payload

    def ensure_notified(self):
        """
        Queue a webhook delivery for every active subscribed webhook.
        """
        from webhooks.models import Webhook

        hooks = Webhook.objects.filter(
            customer=self.customer,
            is_active=True,
        )
        for hook in hooks:
            if not hook.subscribes_to(self.event):
                continue
            try:
                self._enqueue(hook)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to enqueue webhook %s: %s", hook.id, exc)

    def _enqueue(self, hook):
        from webhooks.models import WebhookDelivery
        from webhooks.tasks import send_webhook

        idem_key = f"{self.event}:{uuid.uuid4().hex}"
        delivery = WebhookDelivery.objects.create(
            webhook=hook,
            customer=self.customer,
            event=self.event,
            payload=self.payload,
            idempotency_key=idem_key,
            status=WebhookDelivery.Status.PENDING,
        )
        send_webhook.delay(str(delivery.id))


def build_webhook_payload(event: str, data: dict) -> dict:
    return {
        "event": event,
        "timestamp": datetime_now().isoformat(),
        "data": data,
    }
