from django.urls import reverse

from tests.factories import BaseAPITestCase, create_customer, create_customer_user


class AuthenticationTests(BaseAPITestCase):

    def test_register_creates_customer_and_user(self):
        resp = self.client.post("/api/v1/auth/register/", {
            "email": "new@test.com",
            "password": "strongpass123",
            "full_name": "New User",
            "company_name": "New Company",
        })
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["success"])
        self.assertEqual(resp.data["user"]["email"], "new@test.com")
        self.assertIn("api_key", resp.data)
        self.assertTrue(resp.data["api_key"]["key"].startswith("sk_live_"))

        from api_keys.models import APIKey
        from accounts.models import User
        from customers.models import Customer
        user = User.objects.get(email="new@test.com")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertIsNotNone(user.customer)
        self.assertTrue(Customer.objects.filter(name="New User").exists())
        self.assertTrue(APIKey.objects.filter(customer=user.customer).exists())

    def test_login_jwt(self):
        resp = self.client.post("/api/v1/auth/login/", {
            "email": self.user.email,
            "password": "customerpass123",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_login_wrong_password(self):
        resp = self.client.post("/api/v1/auth/login/", {
            "email": self.user.email,
            "password": "wrong",
        })
        self.assertEqual(resp.status_code, 401)

    def test_me_requires_auth(self):
        self.client.credentials()
        resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(resp.status_code, 401)

    def test_me_with_jwt(self):
        self.jwt_auth(self.user)
        resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["user"]["email"], self.user.email)

    def test_refresh_token(self):
        resp = self.client.post("/api/v1/auth/login/", {
            "email": self.user.email,
            "password": "customerpass123",
        })
        refresh = resp.data["refresh"]
        resp2 = self.client.post("/api/v1/auth/refresh/", {"refresh": refresh})
        self.assertEqual(resp2.status_code, 200)
        self.assertIn("access", resp2.data)

    def test_audit_login_logged(self):
        from audit.models import AuditLog
        self.client.post("/api/v1/auth/login/", {
            "email": self.user.email,
            "password": "customerpass123",
        })
        self.assertTrue(AuditLog.objects.filter(action="login").exists())