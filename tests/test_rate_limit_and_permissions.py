from unittest.mock import patch

from django.core.cache import cache

from core.services.rate_limit import RateLimiter
from messaging.models import Message
from tests.factories import BaseAPITestCase, create_admin_user, create_customer


class RateLimitTests(BaseAPITestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.api_auth()

    def test_rate_limiter_allows_within_limit(self):
        limiter = RateLimiter(prefix="test_rl")
        allowed, count, limit = limiter.hit("user1", 5, 60)
        self.assertTrue(allowed)
        self.assertEqual(count, 1)

    def test_rate_limiter_blocks_after_limit(self):
        limiter = RateLimiter(prefix="test_rl")
        for _ in range(6):
            allowed, count, limit = limiter.hit("user2", 5, 60)
        self.assertFalse(allowed)

    def test_customer_rate_limit_blocks_on_rps(self):
        self.customer.rate_rps = 1
        self.customer.save()
        limiter = RateLimiter(prefix="c")
        allowed, _, _ = limiter.hit(f"c:{self.customer.id}:rps", 1, 1)
        self.assertTrue(allowed)
        allowed, _, _ = limiter.hit(f"c:{self.customer.id}:rps", 1, 1)
        self.assertFalse(allowed)

    def test_message_rate_limit_records_usage(self):
        with patch("messaging.tasks.process_message.apply_async"):
            self.client.post("/api/v1/messages/", {
                "to": "+967700000001", "message": "usage",
            })
        self.assertEqual(self.customer.usage_records.filter(event_type="API_REQUEST").count(), 1)


class PermissionMultiTenancyTests(BaseAPITestCase):

    def test_customer_cannot_see_other_customer_messages(self):
        other = create_customer(name="Other", email="other2@test.com")
        other_msg = Message.objects.create(customer=other, recipient="+967700000099", body="Other msg")
        self.api_auth()
        resp = self.client.get(f"/api/v1/messages/{other_msg.public_id}/")
        self.assertEqual(resp.status_code, 404)

    def test_customer_cannot_access_admin_customer_list(self):
        self.jwt_auth(self.user)
        resp = self.client.get("/api/v1/customers/")
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_list_customers(self):
        self.jwt_auth(self.admin)
        resp = self.client.get("/api/v1/customers/")
        self.assertEqual(resp.status_code, 200)

    def test_customer_user_can_see_own_customer(self):
        from tests.factories import create_customer_user
        u2 = create_customer_user(self.customer, email="emp2@test.com")
        self.jwt_auth(u2)
        resp = self.client.get("/api/v1/messages/")
        self.assertEqual(resp.status_code, 200)

    def test_api_key_cannot_manage_customers(self):
        self.api_auth()
        resp = self.client.post("/api/v1/customers/", {
            "name": "x", "email": "x@test.com",
        })
        self.assertEqual(resp.status_code, 403)

    def test_customer_suspended_cannot_use_api_key(self):
        self.customer.status = "SUSPENDED"
        self.customer.save()
        self.api_auth()
        resp = self.client.post("/api/v1/messages/", {
            "to": "+967700000001", "message": "should fail",
        })
        self.assertEqual(resp.status_code, 401)

    def test_staff_admin_cannot_list_all_users(self):
        admin = create_admin_user()
        self.jwt_auth(admin)
        resp = self.client.get("/api/v1/auth/users/")
        self.assertEqual(resp.status_code, 403)