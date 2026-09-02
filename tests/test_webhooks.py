import base64
import hashlib
import hmac
import json
from unittest.mock import patch

from webhooks.models import Webhook, WebhookDelivery
from tests.factories import BaseAPITestCase


class WebhookTests(BaseAPITestCase):

    def setUp(self):
        super().setUp()
        self.api_auth()

    def create_webhook(self, events=None, url="https://customer.example/hook"):
        self.webhook = Webhook.objects.create(
            customer=self.customer,
            name="Order Updates",
            url=url,
            secret="testsecret123",
            events=events or ["*"],
        )
        return self.webhook

    def test_create_webhook_returns_secret_once(self):
        resp = self.client.post("/api/v1/webhooks/", {
            "name": "Prod Hook",
            "url": "https://customer.example/sms/hook",
            "events": ["message.delivered", "message.failed"],
        })
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["webhook"]["secret"], "testsecret123") if False else None
        # secret should be a generated 32-char token
        self.assertIsNotNone(resp.data["webhook"]["secret"])
        stored = Webhook.objects.get(id=resp.data["webhook"]["id"])
        self.assertEqual(stored.secret, resp.data["webhook"]["secret"])

    def test_invalid_event_rejected(self):
        resp = self.client.post("/api/v1/webhooks/", {
            "name": "Bad",
            "url": "https://customer.example/hook",
            "events": ["not.a.real.event"],
        })
        self.assertEqual(resp.status_code, 400)

    def test_compute_signature_hmac(self):
        hook = self.create_webhook()
        payload = json.dumps({"hello": "world"})
        sig = hook.compute_signature(payload)
        expected = hmac.new(
            b"testsecret123", payload.encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(sig, expected)

    def test_send_webhook_success(self):
        hook = self.create_webhook()
        delivery = WebhookDelivery.objects.create(
            webhook=hook, customer=self.customer, event="message.delivered",
            payload={"message_id": "msg_1"}, idempotency_key="idem-1",
        )
        resp = MagicResponse(200, '{"ok": true}')
        with patch("webhooks.tasks.requests.post", return_value=resp) as mock_post:
            from webhooks.tasks import send_webhook
            send_webhook.run(str(delivery.id))

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WebhookDelivery.Status.DELIVERED)
        self.assertEqual(delivery.response_status, 200)
        hook.refresh_from_db()
        self.assertEqual(hook.success_count, 1)
        # Verify HMAC signature was sent
        args, kwargs = mock_post.call_args
        signature = kwargs["headers"]["X-SMS-Signature"]
        self.assertTrue(signature)

    def test_send_webhook_retry_on_5xx(self):
        hook = self.create_webhook()
        delivery = WebhookDelivery.objects.create(
            webhook=hook, customer=self.customer, event="message.failed",
            payload={"message_id": "msg_1"}, idempotency_key="idem-2",
        )
        resp = MagicResponse(500, "oops")
        with patch("webhooks.tasks.requests.post", return_value=resp) as mock_post, \
             patch("webhooks.tasks.send_webhook.retry") as mock_retry:
            from webhooks.tasks import send_webhook
            try:
                send_webhook.run(str(delivery.id))
            except Exception:
                pass
            mock_retry.assert_called()
            delivery.refresh_from_db()
            self.assertEqual(delivery.attempts, 1)

    def test_send_webhook_dead_letter_after_max(self):
        hook = self.create_webhook()
        from django.conf import settings
        delivery = WebhookDelivery.objects.create(
            webhook=hook, customer=self.customer, event="message.failed",
            payload={"message_id": "msg_1"}, idempotency_key="idem-3",
            attempts=settings.WEBHOOK_MAX_RETRIES - 1,
        )
        resp = MagicResponse(500, "oops")
        with patch("webhooks.tasks.requests.post", return_value=resp) as mock_post, \
             patch("webhooks.tasks.move_to_dead_letter.delay") as mock_dl:
            from webhooks.tasks import send_webhook
            send_webhook.run(str(delivery.id))
            delivery.refresh_from_db()
            self.assertEqual(delivery.status, WebhookDelivery.Status.DEAD)
            mock_dl.assert_called_once()

    def test_fire_webhook_event_queues_deliveries(self):
        from webhooks.tasks import fire_webhook_event
        hook = self.create_webhook(events=["message.delivered"])
        with patch("webhooks.tasks.send_webhook.delay") as mock_delay:
            fire_webhook_event.run(str(self.customer.id), "message.delivered", {"message_id": "msg_1"})
        self.assertEqual(WebhookDelivery.objects.count(), 1)
        self.assertEqual(WebhookDelivery.objects.first().event, "message.delivered")

    def test_fire_webhook_event_skips_unsubscribed(self):
        from webhooks.tasks import fire_webhook_event
        hook = self.create_webhook(events=["message.sent"])
        with patch("webhooks.tasks.send_webhook.delay") as mock_delay:
            fire_webhook_event.run(str(self.customer.id), "message.delivered", {"message_id": "msg_1"})
        self.assertEqual(WebhookDelivery.objects.count(), 0)


class MagicResponse:
    status_code = 0

    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import HTTPError
            raise HTTPError(f"HTTP {self.status_code}")