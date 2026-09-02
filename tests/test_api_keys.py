from api_keys.models import APIKey
from tests.factories import BaseAPITestCase, create_customer


class APIKeyTests(BaseAPITestCase):

    def test_create_api_key_returns_key_once(self):
        self.api_auth()
        resp = self.client.post("/api/v1/api-keys/", {
            "name": "Production",
            "environment": "LIVE",
        })
        self.assertEqual(resp.status_code, 201)
        key = resp.data["api_key"]["key"]
        self.assertTrue(key.startswith("sk_live_"))
        # Hashing check: raw key never stored
        stored = APIKey.objects.get(id=resp.data["api_key"]["id"])
        self.assertNotEqual(stored.hashed_key, key)

    def test_key_visible_only_once(self):
        self.api_auth()
        resp = self.client.post("/api/v1/api-keys/", {"name": "Visible", "environment": "TEST"})
        key_id = resp.data["api_key"]["id"]
        resp2 = self.client.get(f"/api/v1/api-keys/{key_id}/")
        self.assertIsNone(resp2.data["api_key"]["key"])

    def test_auth_with_valid_key(self):
        self.api_auth()
        resp = self.client.get("/api/v1/api-keys/")
        self.assertEqual(resp.status_code, 200)

    def test_auth_with_invalid_key(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer sk_live_invalid_key_123")
        resp = self.client.get("/api/v1/api-keys/")
        self.assertEqual(resp.status_code, 401)

    def test_revoke_key(self):
        self.api_auth()
        key = self.api_key
        resp = self.client.post(f"/api/v1/api-keys/{key.id}/revoke/")
        self.assertEqual(resp.status_code, 200)
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.status, APIKey.Status.REVOKED)
        self.assertIsNotNone(self.api_key.revoked_at)

    def test_revoked_key_cannot_authenticate(self):
        self.api_key.revoke()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        resp = self.client.get("/api/v1/api-keys/")
        self.assertEqual(resp.status_code, 401)

    def test_expired_key_cannot_authenticate(self):
        from datetime import timedelta
        from django.utils import timezone
        self.api_key.expires_at = timezone.now() - timedelta(days=1)
        self.api_key.save()
        self.api_auth()
        resp = self.client.get("/api/v1/api-keys/")
        self.assertEqual(resp.status_code, 401)

    def test_cannot_access_other_customer_keys(self):
        other = create_customer(name="Other", email="other@test.com")
        other_key, other_raw = APIKey.create_for_customer(other, name="Other key")
        self.api_auth()
        resp = self.client.get(f"/api/v1/api-keys/{other_key.id}/")
        self.assertEqual(resp.status_code, 404)