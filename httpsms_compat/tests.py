from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from api_keys.models import APIKey
from customers.models import Customer
from devices.models import Device, SimCard


class CompatViewsTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Test", status=Customer.ACTIVE, phone="+966500000001"
        )
        api_key, self.raw = APIKey.create_for_customer(
            self.customer, name="test", environment="LIVE"
        )
        self.device = Device.objects.create(
            customer=self.customer,
            name="Phone",
            status=Device.Status.ONLINE,
            connection_status=Device.ConnectionStatus.CONNECTED,
        )
        self.sim = SimCard.objects.create(
            device=self.device,
            slot=0,
            phone_number="+966500000001",
            status=SimCard.Status.ACTIVE,
        )
        self.client = APIClient()

    def _headers(self):
        return {"HTTP_X_API_KEY": self.raw}

    def test_heartbeat_found(self):
        resp = self.client.get(
            "/heartbeats", {"owner": "+966500000001"}, **self._headers()
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"][0]["phone"], "+966500000001")

    def test_heartbeat_not_found(self):
        resp = self.client.get(
            "/heartbeats", {"owner": "+966599999999"}, **self._headers()
        )
        self.assertEqual(resp.status_code, 404)

    def test_heartbeat_invalid_key(self):
        resp = self.client.get("/heartbeats", {"owner": "+966500000001"},
                               HTTP_X_API_KEY="sk_live_wrong")
        self.assertEqual(resp.status_code, 401)

    def test_send_message(self):
        resp = self.client.post(
            "/messages/send",
            {"from": "+966500000001", "to": "+966511111111", "content": "Hello"},
            format="json",
            **self._headers(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("id", resp.json()["data"])
