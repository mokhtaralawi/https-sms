from unittest.mock import patch

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from devices.consumers import DeviceConsumer
from devices.models import Device
from messaging.models import IncomingMessage, Message, MessageAttempt
from tests.factories import BaseAPITestCase, create_sim, create_online_device


class WebSocketTests(BaseAPITestCase):

    async def _connect(self, device=None, raw_token=None):
        device = device or self.device
        token = raw_token or device.auth_token
        communicator = WebsocketCommunicator(
            DeviceConsumer.as_asgi(),
            f"/ws/device/?device_uuid={device.device_uuid}&token={token}",
        )
        connected, _ = await communicator.connect()
        return communicator, connected

    async def _device(self):
        return await sync_to_async(Device.objects.get)(id=self.device.id)

    async def test_authenticated_connect_marks_online(self):
        comm, connected = await self._connect()
        self.assertTrue(connected)
        msg = await comm.receive_json_from(timeout=2)
        self.assertEqual(msg["type"], "device.state")
        self.assertIn("pending_sims", msg)
        device = await self._device()
        self.assertEqual(device.status, "ONLINE")
        self.assertEqual(device.connection_status, "CONNECTED")
        await comm.disconnect()

    async def test_invalid_token_rejected(self):
        comm, connected = await self._connect(raw_token="bad_token")
        self.assertFalse(connected)

    async def test_heartbeat_updates_last_seen(self):
        comm, connected = await self._connect()
        await comm.receive_json_from(timeout=2)
        await comm.send_json_to({"type": "heartbeat"})
        resp = await comm.receive_json_from(timeout=2)
        self.assertEqual(resp["type"], "heartbeat")
        self.assertTrue(resp["ack"])
        device = await self._device()
        self.assertIsNotNone(device.last_seen)
        await comm.disconnect()

    async def test_sms_result_ack(self):
        msg = await sync_to_async(Message.objects.create)(
            customer=self.customer, api_key=self.api_key,
            recipient="+967700000001", body="Hi",
            status=Message.Status.SENDING,
        )
        comm, connected = await self._connect()
        await comm.receive_json_from(timeout=2)
        await comm.send_json_to({
            "type": "sms.result",
            "data": {"message_id": msg.public_id, "status": "delivered", "provider_message_id": "p001"},
        })
        resp = await comm.receive_json_from(timeout=2)
        self.assertEqual(resp["type"], "sms.result.ack")
        updated = await sync_to_async(Message.objects.get)(public_id=msg.public_id)
        self.assertEqual(updated.status, Message.Status.DELIVERED)
        await comm.disconnect()

    async def test_sms_result_failed_requeues(self):
        msg = await sync_to_async(Message.objects.create)(
            customer=self.customer, api_key=self.api_key,
            recipient="+967700000001", body="Retry",
            status=Message.Status.SENDING,
            attempts=1, max_attempts=3,
        )
        comm, connected = await self._connect()
        await comm.receive_json_from(timeout=2)
        with patch("messaging.tasks.process_message.delay") as mock_delay:
            await comm.send_json_to({
                "type": "sms.result",
                "data": {"message_id": msg.public_id, "status": "failed", "error_code": "net"},
            })
            resp = await comm.receive_json_from(timeout=2)
            self.assertEqual(resp["type"], "sms.result.ack")
        updated = await sync_to_async(Message.objects.get)(public_id=msg.public_id)
        # Requeued for retry
        self.assertEqual(updated.status, Message.Status.QUEUED)
        mock_delay.assert_called_once_with(str(msg.id))
        await comm.disconnect()

    async def test_sms_received_recorded(self):
        comm, connected = await self._connect()
        await comm.receive_json_from(timeout=2)
        await comm.send_json_to({
            "type": "sms.received",
            "data": {"message_id": "inc_1", "from": "+967700000001", "to": "+9677111222333", "body": "Hello back"},
        })
        resp = await comm.receive_json_from(timeout=2)
        self.assertEqual(resp["type"], "sms.received.ack")
        count = await sync_to_async(IncomingMessage.objects.filter(customer=self.customer).count)()
        self.assertEqual(count, 1)
        incoming = await sync_to_async(IncomingMessage.objects.get)(customer=self.customer)
        self.assertEqual(incoming.from_number, "+967700000001")
        await comm.disconnect()

    async def test_sms_send_push_received(self):
        comm, connected = await self._connect()
        await comm.receive_json_from(timeout=2)
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        await layer.group_send(
            f"device_{self.device.device_uuid}",
            {"type": "sms.send", "message": {
                "type": "sms.send", "message_id": "msg_test_push",
                "to": "+967700000001", "body": "Push me", "job_id": "job-1",
            }},
        )
        received = await comm.receive_json_from(timeout=2)
        self.assertEqual(received["type"], "sms.send")
        self.assertEqual(received["message_id"], "msg_test_push")
        await comm.disconnect()

    async def test_disconnect_marks_offline(self):
        comm, connected = await self._connect()
        await comm.receive_json_from(timeout=2)
        await comm.disconnect()
        device = await self._device()
        self.assertEqual(device.status, "OFFLINE")


class DeviceChannelTests(BaseAPITestCase):
    """Verify device state transitions used by the WebSocket connection."""

    def test_mark_online_offline(self):
        from unittest.mock import patch

        self.device.mark_online(ip_address="10.0.0.5")
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, "ONLINE")
        self.assertEqual(self.device.connection_status, "CONNECTED")
        self.assertEqual(self.device.ip_address, "10.0.0.5")

        with patch("webhooks.tasks.fire_webhook_event.delay"):
            self.device.mark_offline()
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, "OFFLINE")
        self.assertEqual(self.device.connection_status, "DISCONNECTED")

    def test_sim_management(self):
        from devices.models import SimCard
        sim = create_sim(self.device, phone_number="+9677888999000", slot=3)
        self.assertTrue(sim.can_send)

        sim.sms_capability = False
        sim.save()
        self.assertFalse(sim.can_send)

        sim.increment_usage()
        sim.refresh_from_db()
        self.assertEqual(sim.messages_sent, 1)