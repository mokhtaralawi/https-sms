import uuid

from django.db import models

from core.models import UUIDModel, TimeStampedModel
from core.utils import datetime_now


class Device(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        OFFLINE = "OFFLINE", "Offline"
        SUSPENDED = "SUSPENDED", "Suspended"
        BLOCKED = "BLOCKED", "Blocked"

    class ConnectionStatus(models.TextChoices):
        CONNECTED = "CONNECTED", "Connected"
        DISCONNECTED = "DISCONNECTED", "Disconnected"
        STALE = "STALE", "Stale"

    class NetworkType(models.TextChoices):
        WIFI = "WIFI", "WiFi"
        MOBILE = "MOBILE", "Mobile"
        ETHERNET = "ETHERNET", "Ethernet"
        UNKNOWN = "UNKNOWN", "Unknown"

    device_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="devices")

    name = models.CharField(max_length=255, blank=True, default="")
    model = models.CharField(max_length=255, blank=True, default="")
    manufacturer = models.CharField(max_length=255, blank=True, default="")
    android_version = models.CharField(max_length=64, blank=True, default="")
    app_version = models.CharField(max_length=64, blank=True, default="")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OFFLINE, db_index=True)
    connection_status = models.CharField(max_length=20, choices=ConnectionStatus.choices, default=ConnectionStatus.DISCONNECTED, db_index=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    battery_level = models.PositiveSmallIntegerField(null=True, blank=True)
    network_type = models.CharField(max_length=20, choices=NetworkType.choices, default=NetworkType.UNKNOWN)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    # Device authentication token (used in WebSocket)
    auth_token = models.CharField(max_length=128, null=True, blank=True)

    # Selection policy preference
    selection_policy = models.CharField(max_length=30, default="least_used")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["status", "last_seen"]),
        ]
        verbose_name = "جهاز"
        verbose_name_plural = "الأجهزة"

    def __str__(self):
        return f"{self.name or self.device_uuid} ({self.status})"

    def mark_online(self, ip_address=None, **kwargs):
        self.connection_status = self.ConnectionStatus.CONNECTED
        self.status = self.Status.ONLINE
        self.last_seen = datetime_now()
        if ip_address:
            self.ip_address = ip_address
        if kwargs.get("battery_level") is not None:
            self.battery_level = kwargs["battery_level"]
        if kwargs.get("network_type"):
            self.network_type = kwargs["network_type"]
        if kwargs.get("model"):
            self.model = kwargs["model"]
        if kwargs.get("manufacturer"):
            self.manufacturer = kwargs["manufacturer"]
        if kwargs.get("android_version"):
            self.android_version = kwargs["android_version"]
        if kwargs.get("app_version"):
            self.app_version = kwargs["app_version"]
        self.save(update_fields=["connection_status", "status", "last_seen", "ip_address",
                                 "battery_level", "network_type", "model", "manufacturer",
                                 "android_version", "app_version", "updated_at"])

    def mark_offline(self):
        if self.status != self.Status.OFFLINE:
            from webhooks.tasks import fire_webhook_event
            self.connection_status = self.ConnectionStatus.DISCONNECTED
            self.status = self.Status.OFFLINE
            self.save(update_fields=["connection_status", "status", "updated_at"])
            try:
                fire_webhook_event.delay(
                    customer_id=str(self.customer_id),
                    event="device.offline",
                    payload={
                        "device_uuid": str(self.device_uuid),
                        "device_id": str(self.id),
                        "timestamp": datetime_now().isoformat(),
                    },
                )
            except Exception:
                pass


class SimCard(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        REMOVED = "REMOVED", "Removed"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="sim_cards")
    slot = models.PositiveSmallIntegerField(null=True, blank=True)
    phone_number = models.CharField(max_length=20, db_index=True)

    carrier = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=3, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    sms_capability = models.BooleanField(default=True)  # can send SMS
    receive_capability = models.BooleanField(default=True)  # can receive SMS

    last_seen = models.DateTimeField(null=True, blank=True)
    messages_sent = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["device", "slot"]
        indexes = [
            models.Index(fields=["device", "status"]),
            models.Index(fields=["phone_number"]),
        ]
        verbose_name = "شريحة SIM"
        verbose_name_plural = "شرائح SIM"

    def __str__(self):
        return f"{self.phone_number} ({self.carrier})"

    @property
    def can_send(self) -> bool:
        return self.status == self.Status.ACTIVE and self.sms_capability

    def increment_usage(self):
        self.messages_sent += 1
        self.last_seen = datetime_now()
        self.save(update_fields=["messages_sent", "last_seen"])
