"""Shared test factories and base test case."""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api_keys.models import APIKey
from customers.models import Customer
from devices.models import Device, SimCard

User = get_user_model()


def create_superadmin(email="admin@test.com", password="adminpass123"):
    return User.objects.create_superuser(email=email, password=password)


def create_customer(name="Acme Corp", email="acme@test.com", status=Customer.ACTIVE):
    return Customer.objects.create(name=name, company_name=name, email=email, status=status)


def create_customer_user(customer, email="customer@test.com", password="customerpass123"):
    return User.objects.create_user(
        email=email, password=password, role=User.Role.CUSTOMER, customer=customer
    )


def create_admin_user(email="operator@test.com", password="adminer123"):
    return User.objects.create_user(
        email=email, password=password, role=User.Role.ADMIN, is_staff=True
    )


def create_api_key(customer, name="Default", environment="LIVE"):
    key, raw = APIKey.create_for_customer(customer, name=name, environment=environment)
    return key, raw


def create_online_device(customer, name="Device A", policy="least_used"):
    device = Device.objects.create(
        customer=customer,
        name=name,
        auth_token=uuid.uuid4().hex,
        status=Device.Status.ONLINE,
        connection_status=Device.ConnectionStatus.CONNECTED,
        selection_policy=policy,
    )
    return device


def create_sim(device, phone_number="+967700000001", slot=0, carrier="Yemen Mobile"):
    return SimCard.objects.create(
        device=device,
        slot=slot,
        phone_number=phone_number,
        carrier=carrier,
        status=SimCard.Status.ACTIVE,
    )


class BaseAPITestCase(TestCase):
    """Base case with a customer, user, API key and online device."""

    def setUp(self):
        self.client = APIClient()
        self.admin = create_superadmin()
        self.customer = create_customer()
        self.user = create_customer_user(self.customer)
        self.api_key, self.raw_key = create_api_key(self.customer)
        self.device = create_online_device(self.customer)
        for idx, number in enumerate(["+9677111222333", "+9677444555666"]):
            create_sim(self.device, phone_number=number, slot=idx)

    def api_auth(self, raw_key=None):
        """Attach the API key header to the client."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_key or self.raw_key}")

    def jwt_auth(self, user, password="customerpass123"):
        from accounts.models import User

        if user.role == User.Role.CUSTOMER:
            password = "customerpass123"
        elif user.role == User.Role.SUPER_ADMIN:
            password = "adminpass123"
        elif user.role == User.Role.ADMIN:
            password = "adminer123"
        resp = self.client.post("/api/v1/auth/login/", {"email": user.email, "password": password})
        token = resp.data.get("access")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return token

    def tearDown(self):
        self.client.credentials()