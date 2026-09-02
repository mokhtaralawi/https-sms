import random
from typing import Optional

from django.db.models import Count, Q

from devices.models import Device, SimCard


class DeviceSelectionError(Exception):
    pass


class DeviceSelectionEngine:
    """
    Selects the best device+SIM to send a message, based on policy.
    """

    # Policies
    ROUND_ROBIN = "round_robin"
    LEAST_USED = "least_used"
    SPECIFIC_DEVICE = "specific_device"
    SPECIFIC_SIM = "specific_sim"
    CARRIER_BASED = "carrier_based"

    def __init__(self, customer, policy: str = "least_used", device_id: Optional[str] = None,
                 sim_id: Optional[str] = None, carrier: Optional[str] = None):
        self.customer = customer
        self.policy = policy or "least_used"
        self.device_id = device_id
        self.sim_id = sim_id
        self.carrier = carrier

    def select(self) -> tuple:
        """
        Returns a tuple (device, sim_card) or raises DeviceSelectionError.
        """
        # Filter eligible devices
        devices = Device.objects.filter(
            customer=self.customer,
            status=Device.Status.ONLINE,
            connection_status=Device.ConnectionStatus.CONNECTED,
        )

        if self.policy == self.SPECIFIC_DEVICE and self.device_id:
            devices = devices.filter(id=self.device_id)

        devices = devices.annotate(num_sims=Count("sim_cards"))

        if self.policy == self.SPECIFIC_SIM and self.sim_id:
            sims_qs = SimCard.objects.filter(
                id=self.sim_id, device__customer=self.customer, status=SimCard.Status.ACTIVE
            )
            sim = sims_qs.first()
            if not sim:
                raise DeviceSelectionError("Requested SIM is not available.")
            return sim.device, sim

        if self.policy == self.CARRIER_BASED and self.carrier:
            sims_qs = SimCard.objects.filter(
                device__customer=self.customer,
                device__status=Device.Status.ONLINE,
                device__connection_status=Device.ConnectionStatus.CONNECTED,
                carrier__iexact=self.carrier,
                status=SimCard.Status.ACTIVE,
                sms_capability=True,
            )
            sim = sims_qs.order_by("messages_sent").first()
            if not sim:
                raise DeviceSelectionError(f"No SIM on carrier '{self.carrier}' is available.")
            return sim.device, sim

        devices = devices.filter(num_sims__gt=0)
        if not devices.exists():
            raise DeviceSelectionError("No online device with a SIM card is available.")

        device = None
        if self.policy == self.ROUND_ROBIN:
            device = random.choice(list(devices))
        elif self.policy == self.SPECIFIC_DEVICE and self.device_id:
            device = devices.filter(id=self.device_id).first()
            if not device:
                raise DeviceSelectionError("Requested device is not available.")
        else:  # least_used default: prefer the device with the least total SIM usage
            from django.db.models import Sum

            devices = devices.annotate(total_sim_usage=Sum("sim_cards__messages_sent"))
            device = devices.order_by("total_sim_usage", "last_seen").first()

        if device is None:
            raise DeviceSelectionError("No eligible device found.")

        # Find an eligible SIM on the chosen device (least used first)
        sim = (
            SimCard.objects.filter(
                device=device,
                status=SimCard.Status.ACTIVE,
                sms_capability=True,
            )
            .order_by("messages_sent")
            .first()
        )
        if not sim:
            raise DeviceSelectionError("Chosen device has no sendable SIM.")

        return device, sim
