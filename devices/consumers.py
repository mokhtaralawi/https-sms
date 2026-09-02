import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from devices.models import Device
from core.utils import datetime_now

logger = logging.getLogger("httpsms.ws")


class DeviceConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket endpoint for Android gateway devices."""

    async def connect(self):
        self.device = None
        # Authenticate via query params: ?token=...&device_uuid=...
        token = self.scope.get("query_string", b"").decode()
        params = {}
        for pair in token.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v

        device_uuid = params.get("device_uuid", "")
        auth_token = params.get("token", "")

        self.device = await self.authenticate_device(device_uuid, auth_token)
        if self.device is None:
            await self.close(code=4001)
            return

        # Join device group
        self.device_group = f"device_{self.device.device_uuid}"
        await self.channel_layer.group_add(self.device_group, self.channel_name)

        # Mark online
        await self.mark_online()
        await self.accept()

        # Send current device state
        await self.send_json({
            "type": "device.state",
            "status": "connected",
            "device_uuid": str(self.device.device_uuid),
            "timestamp": datetime_now().isoformat(),
            "pending_sims": await self.get_sims(),
        })

        self.heartbeat_count = 0

    @database_sync_to_async
    def authenticate_device(self, device_uuid, auth_token):
        if not device_uuid or not auth_token:
            return None
        try:
            device = Device.objects.get(device_uuid=device_uuid, auth_token=auth_token)
        except Device.DoesNotExist:
            return None
        # Ensure customer is active
        if device.customer.status != "ACTIVE":
            return None
        return device

    @database_sync_to_async
    def mark_online(self):
        from core.utils import datetime_now
        ip_address = self.scope.get("client")
        ip = ip_address[0] if ip_address else None

        q = None
        try:
            qs = self.scope.get("query_string", b"").decode()
            params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
            battery_level = int(params.get("battery_level", 0)) if params.get("battery_level") else None
            network_type = params.get("network_type", "UNKNOWN")
            model = params.get("model", "")
            manufacturer = params.get("manufacturer", "")
            android_version = params.get("android_version", "")
            app_version = params.get("app_version", "")
        except Exception:
            battery_level = network_type = None

        from devices.models import Device as D
        try:
            device = D.objects.get(id=self.device.id)
            device.mark_online(
                ip_address=ip,
                battery_level=battery_level,
                network_type=network_type,
                model=model,
                manufacturer=manufacturer,
                android_version=android_version,
                app_version=app_version,
            )
        except Exception as exc:
            logger.warning("mark_online failed: %s", exc)

    @database_sync_to_async
    def get_sims(self):
        sims = list(self.device.sim_cards.filter(status="ACTIVE").values_list("slot", "phone_number", "carrier"))
        return [{"slot": s[0], "phone_number": s[1], "carrier": s[2]} for s in sims]

    @database_sync_to_async
    def touch_seen(self):
        from django.utils import timezone
        try:
            from devices.models import Device as D
            D.objects.filter(id=self.device.id).update(last_seen=timezone.now())
        except Exception:
            pass

    async def receive_json(self, content, **kwargs):
        if self.device is None:
            return
        msg_type = content.get("type")

        if msg_type == "heartbeat":
            self.heartbeat_count += 1
            await self.touch_seen()
            await self.send_json({"type": "heartbeat", "ack": True, "count": self.heartbeat_count})

        elif msg_type == "sms.result":
            await self.handle_sms_result(content.get("data") or content)

        elif msg_type == "sms.received":
            await self.handle_sms_received(content.get("data") or content)

        elif msg_type == "device.register":
            # Device reporting its SIMs and info
            await self.handle_device_register(content.get("data") or content)
            await self.send_json({"type": "device.register.ack"})

        elif msg_type == "ack":
            await self.touch_seen()

        else:
            await self.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    async def handle_sms_result(self, data):
        from messaging.tasks import handle_sms_result

        # Run sync celery task call in thread
        from asgiref.sync import sync_to_async
        await sync_to_async(handle_sms_result.run)(data)
        await self.send_json({"type": "sms.result.ack", "message_id": data.get("message_id")})

    async def handle_sms_received(self, data):
        from asgiref.sync import sync_to_async
        await sync_to_async(record_incoming_message)(data, self.device.id)
        await self.send_json({"type": "sms.received.ack", "message_id": data.get("message_id")})

    async def handle_device_register(self, data):
        await self.update_sims(data.get("sims", []))
        await self.touch_seen()

    @database_sync_to_async
    def update_sims(self, sims):
        from devices.models import SimCard

        existing_ids = []
        for idx, sim_data in enumerate(sims):
            slot = sim_data.get("slot", idx)
            phone_number = sim_data.get("phone_number", "")
            if not phone_number:
                continue
            sim, _ = SimCard.objects.update_or_create(
                device=self.device,
                slot=slot,
                defaults={
                    "phone_number": phone_number,
                    "carrier": sim_data.get("carrier", ""),
                    "country": sim_data.get("country", ""),
                    "status": "ACTIVE",
                },
            )
            existing_ids.append(sim.id)
        # Deactivate removed SIMs
        SimCard.objects.filter(device=self.device).exclude(id__in=existing_ids).update(status="REMOVED")

    async def sms_send(self, event):
        """Server-initiated send job pushed to the device (group message)."""
        await self.send_json(event["message"])

    async def disconnect(self, code):
        if self.device is not None:
            try:
                await self.channel_layer.group_discard(self.device_group, self.channel_name)
                await self.mark_offline()
            except Exception:
                pass

    @database_sync_to_async
    def mark_offline(self):
        from devices.models import Device as D
        try:
            device = D.objects.get(id=self.device.id)
            device.mark_offline()
        except Exception:
            pass

    async def websocket_disconnect(self, message):
        await self.disconnect(message.get("code", 1000))


def record_incoming_message(data, device_id):
    """
    Save an incoming SMS and fire webhooks (called in thread via sync_to_async).
    """
    from devices.models import Device, SimCard
    from messaging.models import IncomingMessage
    from webhooks.tasks import fire_webhook_event
    from usage.tasks import record_usage

    device = Device.objects.filter(id=device_id).first()
    if not device:
        return None

    to_number = data.get("to") or ""
    sim = None
    if to_number:
        sim = SimCard.objects.filter(device=device, phone_number=to_number).first()

    incoming = IncomingMessage.objects.create(
        customer=device.customer,
        device=device,
        sim_card=sim,
        from_number=data.get("from", ""),
        to_number=to_number,
        body=data.get("body", ""),
    )
    record_usage(str(device.customer_id), "RECEIVED", device_id=str(device.id),
                 sim_card_id=str(sim.id) if sim else None, message_id=str(incoming.id))

    fire_webhook_event.delay(str(device.customer_id), "message.received", {
        "message_id": incoming.public_id,
        "from": incoming.from_number,
        "to": incoming.to_number,
        "body": incoming.body,
    })
    return incoming
