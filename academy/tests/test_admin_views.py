from django.test import TestCase
from django.urls import reverse
from accounts.models import User


class AcademyAdminAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="academy-admin", email="academy-admin@example.com",
            password="TestPass123!", role=User.Role.ADMIN,
        )
        self.customer = User.objects.create_user(
            username="academy-customer", email="academy-customer@example.com",
            password="TestPass123!", role=User.Role.CUSTOMER,
        )

    def test_admin_can_open_academy_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_panel:academy_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_customer_cannot_open_academy_dashboard(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("admin_panel:academy_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("admin_panel:academy_dashboard"))
        self.assertEqual(response.status_code, 302)
