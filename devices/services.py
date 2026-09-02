import logging

from django.db.models import F

from devices.models import Device, SimCard
from messaging.models import Message

logger = logging.getLogger("httpsms.devices")

SELECTION_ROUND_ROBIN = "round_robin"
SELECTION_LEAST_USED = "least_used"
SELECTION_SPECIFIC_DEVICE = "specific_device"
SELECTION_SPECIFIC_SIM = "specific_sim"
SELECTION_CARRIER = "carrier"


class DeviceSelectionError(Exception):
    pass


class DeviceSelector:
    """Selects the best available device/SIM for a given message."""

    def __init__(self, message: Message):
        self.message = message
        self.customer = message.customer

    def _candidate_devices(self):
        return (
            Device.objects.filter(customer=self.customer, status=Device.ONLINE)
            .exclude(status__in=[Device.SUSPENDED, Device.BLOCKED])
            .select_related("customer")
        )

    def _has_send_sim(self, device: Device) -> bool:
        return (
            SimCard.objects.filter(
                device=device,
                status=SimCard.ACTIVE,
                sms_capability__in=[SimCard.SEND, SimCard.SEND_RECEIVE],
            ).exists()
        )

    def select(self, policy=SELECTION_ROUND_ROBIN, device_id=None, sim_id=None, carrier=None):
        """Return (device, sim_card) candidates for the message."""
        devices = self._candidate_devices()
        if not devices.exists():
            raise DeviceSelectionError("No online devices available for this customer.")

        selected_device = None
        if policy == SELECTION_SPECIFIC_DEVICE and device_id:
            selected_device = devices.filter(id=device_id).first()
        elif policy == SELECTION_CARRIER and carrier:
            selected_device = self._select_by_carrier(devices, carrier)
        elif policy == SELECTION_LEAST_USED:
            selected_device = self._least_used(devices)
        else:
            selected_device = self._round_robin(devices)

        if selected_device is None:
            raise DeviceSelectionError("No device matches selection criteria.")

        sim = self._pick_sim(selected_device, sim_id, carrier)
        if sim is None:
            raise DeviceSelectionError("Selected device has no available SIM for sending.")
        return selected_device, sim

    def _round_robin(self, devices):
        # pick device that has been used least recently (approximation of round robin)
        return (
            devices.filter(simcards__status=SimCard.ACTIVE)
            .annotate(last_use=F("messages__sent_at"))
            .order_by("-last_use")
            .first()
            or self._first_with_sim(devices)
        )

    def _least_used(self, devices):
        from django.db.models import Count

        return (
            devices.annotate(usage_count=Count("messages"))
            .order_by("usage_count")
            .first()
        )

    def _select_by_carrier(self, devices, carrier):
        sim = (
            SimCard.objects.filter(
                device__in=devices,
                status=SimCard.ACTIVE,
                carrier__iexact=carrier,
                sms_capability__in=[SimCard.SEND, SimCard.SEND_RECEIVE],
            )
            .select_related("device")
            .order_by("device__last_seen")
            .first()
        )
        return sim.device if sim else None

    def _first_with_sim(self, devices):
        for device in devices:
            if self._has_send_sim(device):
                return device
        return None

    def _pick_sim(self, device, sim_id=None, carrier=None):
        qs = SimCard.objects.filter(
            device=device,
            status=SimCard.ACTIVE,
            sms_capability__in=[SimCard.SEND, SimCard.SEND_RECEIVE],
        )
        if sim_id:
            return qs.filter(id=sim_id).order_by("slot").first()
        if carrier:
            return qs.filter(carrier__iexact=carrier).order_by("slot").first()
        return qs.order_by("slot").first()


class DeviceManager:
    """Manages device WebSocket communication and message dispatch."""

    @staticmethod
    def get_online(device_id) -> Device | None:
        return Device.objects.filter(
            id=device_id, status=Device.ONLINE
        ).first()

    @staticmethod
    def dispatch(device_id, message_id, recipient, body):
        """Send an sms.send job to a device via its WebSocket channel."""
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        channel_name = f"device_{device_id}"
        async_to_sync(channel_layer.group_send)(
            channel_name,
            {
                "type": "sms.send",
                "message_id": message_id,
                "to": recipient,
                "body": body,
            },
        )
