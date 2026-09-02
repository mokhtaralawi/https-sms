import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache

from messaging.models import IncomingMessage, Message, MessageAttempt
from tests.factories import BaseAPITestCase, create_sim


class SendSMSTests(BaseAPITestCase):
    """Integration tests: API -> Queue -> Device -> Result."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.api_auth()

    def test_send_sms_queues_message(self):
        with patch("messaging.services.sender.process_message.apply_async") as mock:
            resp = self.client.post("/api/v1/messages/", {
                "to": "+967700000001",
                "message": "Hello SMS",
            }, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertTrue(resp.data["success"])
        message_id = resp.data["message_id"]
        msg = Message.objects.get(public_id=message_id)
        self.assertEqual(msg.status, Message.Status.QUEUED)
        self.assertEqual(msg.recipient, "+967700000001")
        self.assertEqual(msg.customer_id, self.customer.id)
        self.assertEqual(msg.api_key_id, self.api_key.id)
        mock.assert_called_once()

    def test_send_sms_requires_auth(self):
        self.client.credentials()
        resp = self.client.post("/api/v1/messages/", {
            "to": "+967700000001",
            "message": "Hello",
        }, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_send_sms_invalid_recipient(self):
        resp = self.client.post("/api/v1/messages/", {
            "to": "123",
            "message": "Hello",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_send_sms_missing_message(self):
        resp = self.client.post("/api/v1/messages/", {"to": "+967700000001"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_send_sms_over_1600_chars_rejected(self):
        resp = self.client.post("/api/v1/messages/", {
            "to": "+967700000001",
            "message": "x" * 1601,
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    # ---- Idempotency ----

    def test_idempotency_key_prevents_duplicate(self):
        with patch("messaging.services.sender.process_message.apply_async"):
            for _ in range(2):
                resp = self.client.post("/api/v1/messages/", {
                    "to": "+967700000001",
                    "message": "Same order",
                }, format="json", HTTP_IDEMPOTENCY_KEY="order-12345")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["duplicate"])
        # Only ONE message should exist
        self.assertEqual(Message.objects.filter(idempotency_key="order-12345").count(), 1)

    def test_same_body_without_idempotency_creates_two(self):
        with patch("messaging.services.sender.process_message.apply_async"):
            for _ in range(2):
                self.client.post("/api/v1/messages/", {
                    "to": "+967700000001",
                    "message": "Same",
                }, format="json")
        self.assertEqual(Message.objects.count(), 2)

    # ---- Bulk ----

    def test_bulk_sms_creates_message_per_recipient(self):
        with patch("messaging.services.sender.process_message.apply_async"):
            resp = self.client.post("/api/v1/messages/bulk/", {
                "recipients": ["+967700000001", "+967700000002"],
                "message": "Group message",
            }, format="json")
        self.assertEqual(resp.status_code, 202, resp.data)
        self.assertEqual(resp.data["count"], 2)
        group_messages = Message.objects.filter(is_bulk=True)
        self.assertEqual(group_messages.count(), 2)
        self.assertTrue(all(m.bulk_group_id == group_messages[0].bulk_group_id for m in group_messages))

    def test_bulk_sms_bad_number_rejected(self):
        resp = self.client.post("/api/v1/messages/bulk/", {
            "recipients": ["+967700000001", "bad"],
            "message": "Group",
        }, format="json")
        self.assertEqual(resp.status_code, 400)

    # ---- Message status query ----

    def test_message_list_with_api_key(self):
        msg = Message.objects.create(
            customer=self.customer, api_key=self.api_key,
            recipient="+967700000001", body="Hi",
        )
        resp = self.client.get("/api/v1/messages/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["messages"][0]["public_id"], msg.public_id)

    def test_message_detail(self):
        msg = Message.objects.create(
            customer=self.customer, api_key=self.api_key,
            recipient="+967700000001", body="Hi",
        )
        resp = self.client.get(f"/api/v1/messages/{msg.public_id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["message"]["public_id"], msg.public_id)

    def test_message_not_found(self):
        resp = self.client.get("/api/v1/messages/msg_nonexistent/")
        self.assertEqual(resp.status_code, 404)

    def test_cancel_queued_message(self):
        msg = Message.objects.create(
            customer=self.customer, api_key=self.api_key,
            recipient="+967700000001", body="Cancel me",
        )
        from webhooks.tasks import fire_webhook_event
        with patch.object(fire_webhook_event, "delay"):
            resp = self.client.delete(f"/api/v1/messages/{msg.public_id}/")
        self.assertEqual(resp.status_code, 200)
        msg.refresh_from_db()
        self.assertEqual(msg.status, Message.Status.CANCELLED)


class QueueIntegrationTests(BaseAPITestCase):
    """Test the Celery task pipeline with a fake channel layer."""

    def setUp(self):
        super().setUp()
        self.api_auth()

    @patch("messaging.tasks.async_to_sync")
    def test_process_message_dispatches_to_device(self, mock_async_to_sync):
        from messaging.services.sender import process_single_message

        # Create message (do NOT run the eager pipeline yet).
        with patch("messaging.services.sender.process_message.apply_async"):
            msg, err = process_single_message(
                self.customer, self.api_key, "+967700000001", "Integration test"
            )
        assert msg.status == Message.Status.QUEUED

        # Mock channel layer group_send. async_to_sync(group_send) then needs
        # only (group, event).
        sent = {}
        def fake_send(group, event):
            sent["group"] = group
            sent["event"] = event

        mock_async_to_sync.return_value = fake_send

        from messaging.tasks import process_message
        process_message.run(str(msg.id))

        msg.refresh_from_db()
        self.assertEqual(msg.status, Message.Status.SENDING)
        self.assertEqual(msg.device_id, self.device.id)
        self.assertTrue(msg.sending_at)
        self.assertEqual(sent["group"], f"device_{self.device.device_uuid}")
        self.assertEqual(sent["event"]["message"]["type"], "sms.send")

    def test_process_message_retries_when_no_device(self):
        from messaging.services.sender import process_single_message
        # Disconnect the device
        self.device.status = "OFFLINE"
        self.device.connection_status = "DISCONNECTED"
        self.device.save()

        with patch("messaging.services.sender.process_message.apply_async"):
            msg, err = process_single_message(
                self.customer, self.api_key, "+967700000001", "No device"
            )

        from celery.exceptions import Retry
        from messaging.tasks import process_message

        try:
            process_message.run(str(msg.id))
        except Retry:
            pass  # relocation scheduled in the real celery worker

        msg.refresh_from_db()
        self.assertEqual(msg.status, Message.Status.QUEUED)
        self.assertEqual(msg.attempts, 1)

        msg.refresh_from_db()
        self.assertEqual(msg.status, Message.Status.QUEUED)
        self.assertEqual(msg.attempts, 1)

    def test_handle_sms_result_sent(self, ):
        from messaging.tasks import handle_sms_result
        msg = Message.objects.create(
            customer=self.customer, api_key=self.api_key,
            recipient="+967700000001", body="Hi",
            status=Message.Status.SENDING,
        )
        handle_sms_result.run({
            "message_id": msg.public_id,
            "status": "sent",
            "provider_message_id": "android-abc",
        })
        msg.refresh_from_db()
        self.assertEqual(msg.status, Message.Status.SENT)
        self.assertEqual(msg.provider_message_id, "android-abc")

    def test_handle_sms_result_failed_then_retry(self):
        from messaging.tasks import handle_sms_result, process_message
        msg = Message.objects.create(
            customer=self.customer, api_key=self.api_key,
            recipient="+967700000001", body="Will fail once",
            status=Message.Status.SENDING, attempts=1, max_attempts=3,
        )
        with patch.object(process_message, "delay") as mock_delay:
            handle_sms_result.run({
                "message_id": msg.public_id,
                "status": "failed",
                "error_code": "network_error",
            })
        msg.refresh_from_db()
        self.assertEqual(msg.status, Message.Status.QUEUED)
        mock_delay.assert_called_once_with(str(msg.id))

    def test_handle_sms_result_failed_fatal(self):
        from messaging.tasks import handle_sms_result, process_message
        msg = Message.objects.create(
            customer=self.customer, api_key=self.api_key,
            recipient="+967700000001", body="Will die",
            status=Message.Status.SENDING, attempts=2, max_attempts=3,
        )
        with patch.object(process_message, "delay") as mock_delay:
            handle_sms_result.run({
                "message_id": msg.public_id,
                "status": "failed",
                "error_code": "permanent",
                "fatal": True,
            })
        msg.refresh_from_db()
        self.assertEqual(msg.status, Message.Status.FAILED)
        mock_delay.assert_not_called()

    def test_requeue_stale_sending(self):
        from datetime import timedelta
        from django.utils import timezone
        from messaging.tasks import requeue_stale_sending_messages, process_message

        msg = Message.objects.create(
            customer=self.customer, api_key=self.api_key,
            recipient="+967700000001", body="Stale",
            status=Message.Status.SENDING,
            sending_at=timezone.now() - timedelta(minutes=10),
        )
        with patch.object(process_message, "delay") as mock_delay:
            requeue_stale_sending_messages.run()
            mock_delay.assert_called_once_with(str(msg.id))
        msg.refresh_from_db()
        self.assertEqual(msg.status, Message.Status.QUEUED)

    def test_device_selection_round_robin(self):
        from devices.services.selection import DeviceSelectionEngine
        from tests.factories import create_online_device, create_sim

        device2 = create_online_device(self.customer, name="Device B")
        create_sim(device2, phone_number="+9677555666777", slot=0)
        engine = DeviceSelectionEngine(self.customer, policy="round_robin")
        device, sim = engine.select()
        self.assertIn(device.id, [self.device.id, device2.id])

    def test_device_selection_least_used(self):
        from devices.services.selection import DeviceSelectionEngine
        from devices.models import Device
        from tests.factories import create_online_device, create_sim

        device2 = create_online_device(self.customer, name="Device Low")
        create_sim(device2, phone_number="+9677555666777", slot=0)
        device2.refresh_from_db()
        # force messages_sent lower on device2's sim
        from devices.models import SimCard
        sim2 = SimCard.objects.get(device=device2)
        sim2.messages_sent = 0
        self.device.sim_cards.update(messages_sent=50)
        sim2.save()

        engine = DeviceSelectionEngine(self.customer, policy="least_used")
        device, sim = engine.select()
        self.assertEqual(device.id, device2.id)

    def test_device_selection_specific_policy(self):
        from devices.services.selection import DeviceSelectionEngine, DeviceSelectionError
        engine = DeviceSelectionEngine(self.customer, policy="specific_device", device_id=str(self.device.id))
        device, sim = engine.select()
        self.assertEqual(device.id, self.device.id)

    def test_device_selection_no_device_error(self):
        from devices.services.selection import DeviceSelectionEngine, DeviceSelectionError
        self.device.status = "OFFLINE"
        self.device.save()
        from devices.services.selection import DeviceSelectionEngine
        engine = DeviceSelectionEngine(self.customer, policy="least_used")
        with self.assertRaises(DeviceSelectionError):
            engine.select()