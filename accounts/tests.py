from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from enquiries.models import Enquiry
from services.models import Service, ServiceCategory
from staff.models import StaffProfile


class AuthRoleTests(TestCase):

    def test_public_pages_load(self):
        self.assertEqual(
            self.client.get(reverse("core:home")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("accounts:login")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("accounts:register")).status_code, 200
        )

    def test_register_creates_customer_only(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "first_name": "Asha",
                "last_name": "K",
                "email": "asha@example.com",
                "phone": "9876543210",
                "username": "asha",
                "password1": "Str0ng!Pass#91",
                "password2": "Str0ng!Pass#91",
                "role": "admin",
                "is_superuser": "on",
            },
        )

        self.assertRedirects(
            response, reverse("client:dashboard")
        )

        user = User.objects.get(username="asha")

        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(user.is_superuser)

    def test_role_separation(self):
        User.objects.create_user(
            "cust", "c@x.com", "pw12345!x",
            role=User.Role.CUSTOMER,
        )
        User.objects.create_user(
            "boss", "b@x.com", "pw12345!x",
            role=User.Role.ADMIN,
        )

        self.client.login(
            username="cust", password="pw12345!x"
        )

        self.assertEqual(
            self.client.get(
                reverse("admin_panel:dashboard")
            ).status_code,
            403,
        )

        self.assertEqual(
            self.client.get(
                reverse("client:dashboard")
            ).status_code,
            200,
        )

        self.client.logout()

        self.client.login(
            username="boss", password="pw12345!x"
        )

        self.assertEqual(
            self.client.get(
                reverse("admin_panel:dashboard")
            ).status_code,
            200,
        )

        self.assertEqual(
            self.client.get(
                reverse("client:dashboard")
            ).status_code,
            403,
        )

    def test_staff_cannot_access_admin_dashboard(self):
        User.objects.create_user(
            "staffuser", "staff@example.com", "pw12345!x",
            role=User.Role.STAFF,
        )

        self.client.login(
            username="staffuser", password="pw12345!x"
        )

        response = self.client.get(
            reverse("admin_panel:dashboard")
        )

        self.assertEqual(response.status_code, 403)

    def test_staff_post_login_redirects_to_home(self):
        User.objects.create_user(
            "staffuser", "staff@example.com", "pw12345!x",
            role=User.Role.STAFF,
        )

        self.client.login(
            username="staffuser", password="pw12345!x"
        )

        response = self.client.get(
            reverse("accounts:post_login")
        )

        self.assertRedirects(
            response, reverse("core:home")
        )

    def test_admin_post_login_redirects_to_admin_dashboard(self):
        User.objects.create_user(
            "boss", "boss@example.com", "pw12345!x",
            role=User.Role.ADMIN,
        )

        self.client.login(
            username="boss", password="pw12345!x"
        )

        response = self.client.get(
            reverse("accounts:post_login")
        )

        self.assertRedirects(
            response, reverse("admin_panel:dashboard")
        )

    def test_dashboard_shows_real_database_counts(self):
        admin = User.objects.create_user(
            "boss", "boss@example.com", "pw12345!x",
            role=User.Role.ADMIN,
        )

        User.objects.create_user(
            "customer1", "customer@example.com", "pw12345!x",
            role=User.Role.CUSTOMER,
        )

        category = ServiceCategory.objects.create(
            name="Skin Care",
            is_active=True,
        )

        Service.objects.create(
            category=category,
            name="Signature Facial",
            description="Test service",
            price=Decimal("1500.00"),
            duration_minutes=60,
            is_active=True,
        )

        StaffProfile.objects.create(
            name="Dhanya",
            title="Senior Beautician",
            is_active=True,
        )

        Enquiry.objects.create(
            name="Meera",
            phone="9876543210",
            interested_in="Skin Care",
            message="I would like to know more.",
        )

        self.client.force_login(admin)

        response = self.client.get(
            reverse("admin_panel:dashboard")
        )

        self.assertEqual(response.status_code, 200)

        stats = response.context["stats"]

        self.assertEqual(stats["customers"], 1)
        self.assertEqual(stats["services"], 1)
        self.assertEqual(stats["beauticians"], 1)
        self.assertEqual(stats["new_enquiries"], 1)

        self.assertEqual(
            response.context["status_rows"][0]["label"],
            "Pending",
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(
            reverse("client:dashboard")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "/accounts/login/",
            response["Location"],
        )

    def test_email_login(self):
        User.objects.create_user(
            "meera", "meera@x.com", "pw12345!x"
        )

        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "meera@x.com",
                "password": "pw12345!x",
            },
        )

        self.assertEqual(response.status_code, 302)