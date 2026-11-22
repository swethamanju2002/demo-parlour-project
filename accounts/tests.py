from django.test import TestCase
from django.urls import reverse

from .models import User


class AuthRoleTests(TestCase):
    def test_public_pages_load(self):
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 200)

    def test_register_creates_customer_only(self):
        r = self.client.post(reverse("accounts:register"), {
            "first_name": "Asha", "last_name": "K", "email": "asha@example.com", "phone": "9876543210",
            "username": "asha", "password1": "Str0ng!Pass#91", "password2": "Str0ng!Pass#91",
            "role": "admin", "is_superuser": "on",  # tampering attempt
        })
        self.assertRedirects(r, reverse("client:dashboard"))
        u = User.objects.get(username="asha")
        self.assertEqual(u.role, "customer")
        self.assertFalse(u.is_superuser)

    def test_role_separation(self):
        User.objects.create_user("cust", "c@x.com", "pw12345!x", role="customer")
        User.objects.create_user("boss", "b@x.com", "pw12345!x", role="admin")
        self.client.login(username="cust", password="pw12345!x")
        self.assertEqual(self.client.get(reverse("admin_panel:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("client:dashboard")).status_code, 200)
        self.client.logout()
        self.client.login(username="boss", password="pw12345!x")
        self.assertEqual(self.client.get(reverse("admin_panel:dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("client:dashboard")).status_code, 403)

    def test_anonymous_redirected_to_login(self):
        r = self.client.get(reverse("client:dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])

    def test_email_login(self):
        User.objects.create_user("meera", "meera@x.com", "pw12345!x")
        r = self.client.post(reverse("accounts:login"), {"username": "meera@x.com", "password": "pw12345!x"})
        self.assertEqual(r.status_code, 302)
