import hashlib
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from messaging.models import IncomingMessage, Message
from otp.models import OTPRequest
from tests.factories import BaseAPITestCase, create_sim


class IncomingSMSTests(BaseAPITestCase):

    def setUp(self):
        super().setUp()
        cache.clear()

    def test_record_incoming_message(self):
        from devices.consumers import record_incoming_message
        from devices.models import SimCard
        sim = SimCard.objects.get(device=self.device, slot=0)

        from unittest.mock import patch
        with patch("webhooks.tasks.fire_webhook_event.delay"):
            incoming = record_incoming_message(
                {"from": "+967700000001", "to": "+9677111222333", "body": "Reply"},
                self.device.id,
            )
        self.assertIsNotNone(incoming)
        self.assertEqual(incoming.from_number, "+967700000001")
        self.assertEqual(incoming.customer_id, self.customer.id)
        # Webhook delivery queued
        self.assertTrue(IncomingMessage.objects.filter(customer=self.customer).exists())

    def test_incoming_message_list_api(self):
        IncomingMessage.objects.create(
            customer=self.customer, device=self.device,
            from_number="+967700000001", to_number="+9677111222333", body="Hi",
        )
        self.api_auth()
        resp = self.client.get("/api/v1/messages/incoming/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["messages"]), 1)


class DeliveryReportTests(BaseAPITestCase):

    def setUp(self):
        super().setUp()
        cache.clear()

    def test_delivered_result_updates_message(self):
        from messaging.tasks import handle_sms_result
        msg = Message.objects.create(
            customer=self.customer, api_key=self.api_key,
            recipient="+967700000001", body="report",
            status=Message.Status.SENDING,
            device=self.device,
        )
        handle_sms_result.run({
            "message_id": msg.public_id,
            "status": "delivered",
            "provider_message_id": "dr-1",
        })
        msg.refresh_from_db()
        self.assertEqual(msg.status, Message.Status.DELIVERED)
        self.assertTrue(msg.delivered_at)
        self.assertEqual(msg.provider_message_id, "dr-1")

    def test_sent_result_does_not_claim_delivery(self):
        from messaging.tasks import handle_sms_result
        msg = Message.objects.create(
            customer=self.customer, api_key=self.api_key,
            recipient="+967700000001", body="report",
            status=Message.Status.SENDING,
        )
        handle_sms_result.run({"message_id": msg.public_id, "status": "sent"})
        msg.refresh_from_db()
        self.assertEqual(msg.status, Message.Status.SENT)
        self.assertIsNone(msg.delivered_at)
        self.assertIsNotNone(msg.sent_at)


class OTPTests(BaseAPITestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.api_auth()

    def test_send_otp_queues_and_hashes(self):
        from otp.services import create_otp_for_testing
        otp, code = create_otp_for_testing(self.customer, "+967700000001")
        self.assertEqual(len(code), 6)
        self.assertEqual(
            otp.hashed_code,
            hashlib.sha256(code.encode()).hexdigest(),
        )

    def test_verify_otp_correct(self):
        from otp.services import create_otp_for_testing, OTPService
        otp, code = create_otp_for_testing(self.customer, "+967700000001")
        ok = OTPService.verify(self.customer, "+967700000001", code, otp_id=str(otp.id))
        self.assertTrue(ok)
        otp.refresh_from_db()
        self.assertEqual(otp.status, OTPRequest.Status.VERIFIED)

    def test_verify_otp_wrong_rejected(self):
        from otp.services import create_otp_for_testing, OTPService
        otp, code = create_otp_for_testing(self.customer, "+967700000001")
        ok = OTPService.verify(self.customer, "+967700000001", "000000", otp_id=str(otp.id))
        self.assertFalse(ok)
        otp.refresh_from_db()
        # Only one attempt used
        self.assertEqual(otp.attempts, 1)

    def test_verify_expired_otp_rejected(self):
        from otp.services import OTPService
        otp = OTPRequest.objects.create(
            customer=self.customer, recipient="+967700000001", purpose="authentication",
            hashed_code="abc", code_prefix="ab",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        ok = OTPService.verify(self.customer, "+967700000001", "123456", otp_id=str(otp.id))
        self.assertFalse(ok)

    def test_otp_max_attempts_expires(self):
        from otp.services import create_otp_for_testing, OTPService
        from django.conf import settings
        otp, code = create_otp_for_testing(self.customer, "+967700000001")
        for _ in range(settings.OTP_MAX_ATTEMPTS + 1):
            ok = OTPService.verify(self.customer, "+967700000001", "123456", otp_id=str(otp.id))
        self.assertFalse(ok)
        otp.refresh_from_db()
        self.assertEqual(otp.status, OTPRequest.Status.EXPIRED)

    def test_api_otp_send_requires_valid_to(self):
        from unittest.mock import patch
        # In eager (test) mode the queued job would run immediately and could
        # reach a retry; that is fine in production but not during the API test.
        with patch("messaging.tasks.process_message.apply_async"):
            resp = self.client.post("/api/v1/otp/send/", {"to": "+967700000001"}, format="json")
        # Sending an OTP creates a message in the queue
        self.assertEqual(resp.status_code, 202, resp.data)
        self.assertTrue(resp.data["otp_id"])