from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from enquiries.models import Enquiry
from offers.models import Offer
from services.models import Service


class PublicSiteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def test_all_public_pages_render(self):
        for name in ["core:home", "core:about", "core:contact", "services:list", "gallery:list", "offers:list"]:
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 200, name)

    def test_services_come_from_database(self):
        r = self.client.get(reverse("services:list"))
        for s in Service.objects.active():
            self.assertContains(r, s.name)

    def test_inactive_service_hidden(self):
        s = Service.objects.first(); s.is_active = False; s.save()
        self.assertNotContains(self.client.get(reverse("services:list")), s.name)

    def test_expired_offers_not_shown(self):
        r = self.client.get(reverse("offers:list"))
        self.assertContains(r, "Grand Opening")
        self.assertNotContains(r, "Glow Facial Week")
        o = Offer.objects.get(title="Grand Opening: 15% off")
        o.valid_to = timezone.localdate() - timedelta(days=1); o.save()
        self.assertNotContains(self.client.get(reverse("offers:list")), "Grand Opening")

    def test_enquiry_saved_and_honeypot_blocks_bots(self):
        data = {"name": "Lakshmi", "phone": "9876543210", "message": "Bridal trial dates?"}
        r = self.client.post(reverse("core:contact"), data, headers={"x-requested-with": "fetch"})
        self.assertJSONEqual(r.content, {"ok": True, "message": "Thanks, we have your message and will call you soon."})
        self.assertTrue(Enquiry.objects.filter(name="Lakshmi", status="new").exists())
        n = Enquiry.objects.count()
        r = self.client.post(reverse("core:contact"), {**data, "website": "spam"}, headers={"x-requested-with": "fetch"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Enquiry.objects.count(), n)

    def test_enquiry_validation_errors(self):
        r = self.client.post(reverse("core:contact"), {"name": "", "phone": "x", "message": ""}, headers={"x-requested-with": "fetch"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("phone", r.json()["errors"])
