from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from customers.models import Customer
from otp.models import OTPRequest
from otp.services import OTPService

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    OTP_EXPIRY_SECONDS=300,
)
class RegistrationFlowTest(TestCase):
    def test_register_sends_email_otp_and_activates(self):
        # Render registration page
        resp = self.client.get(reverse("webapp:register"))
        self.assertEqual(resp.status_code, 200)

        # Submit registration -> email OTP sent, redirect to otp page
        resp = self.client.post(reverse("webapp:register"), {
            "email": "user@gmail.com",
            "password": "secretpass123",
            "password_confirm": "secretpass123",
            "full_name": "Test User",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("webapp:otp"))

        # No user created yet
        self.assertFalse(User.objects.filter(email="user@gmail.com").exists())

        # An OTPRequest exists for the recipient
        otp = OTPRequest.objects.filter(recipient="user@gmail.com", purpose="registration").first()
        self.assertIsNotNone(otp)

        # Get the code from the OTP service's in-memory helper: regenerate for test
        code = "123456"
        # The real code is hashed; verify_email uses stored hash. Simulate by verifying wrong code
        # -> should fail
        resp = self.client.post(reverse("webapp:otp"), {"code": "000000"})
        self.assertContains(resp, "غير صحيح")

        # Now verify with the correct code by fetching it from email backend
        from django.core import mail
        self.assertEqual(len(mail.outbox), 1)
        # Parse the code from the message body
        body = mail.outbox[0].body
        lines = body.splitlines()
        code = None
        for line in lines:
            if "verification code is" in line:
                code = "".join(ch for ch in line if ch.isdigit())
                break
        self.assertIsNotNone(code)

        resp = self.client.post(reverse("webapp:otp"), {"code": code})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("webapp:dashboard"))

        # User + customer + api key created, and user is authenticated
        user = User.objects.get(email="user@gmail.com")
        self.assertTrue(user.is_active)
        self.assertEqual(user.customer.name, "Test User")
        self.assertTrue(resp.wsgi_request.user.is_authenticated)

    def test_register_rejects_duplicate_email(self):
        user = User.objects.create_user(email="dup@gmail.com", password="secretpass123")
        resp = self.client.post(reverse("webapp:register"), {
            "email": "DUP@gmail.com",
            "password": "secretpass123",
            "password_confirm": "secretpass123",
        })
        self.assertContains(resp, "مسجل مسبقاً")

    def test_register_password_mismatch(self):
        resp = self.client.post(reverse("webapp:register"), {
            "email": "x@gmail.com",
            "password": "secretpass123",
            "password_confirm": "different",
        })
        self.assertContains(resp, "غير متطابقتين")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LoginLogoutTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="login@gmail.com", password="secretpass123")

    def test_login_and_logout(self):
        resp = self.client.post(reverse("webapp:login"), {
            "email": "login@gmail.com", "password": "secretpass123",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("webapp:dashboard"))

        resp = self.client.get(reverse("webapp:dashboard"))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get(reverse("webapp:logout"))
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse("webapp:dashboard"))
        self.assertEqual(resp.status_code, 302)
