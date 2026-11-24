import datetime as dt
import json
from decimal import Decimal
from unittest.mock import patch

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from bookings import availability as av
from bookings import workflow as _wf
from bookings.models import Booking, BookingItem
from bookings.tests import MON, SUN, TUE, WED, EngineCase, at
from offers.models import Offer
from services.models import Service

FETCH = {"x-requested-with": "fetch"}


class PortalCase(EngineCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.alice)

    def get(self, name, **params):
        return self.client.get(reverse(name), params)

    def post_book(self, **over):
        body = {"services": [self.facial.pk], "start": at(TUE, "12:00").isoformat(), "staff": self.A.pk, **over}
        return self.client.post(reverse("client:api_book"), json.dumps(body), content_type="application/json")

    def past_booking(self, who, days_ago, status="completed"):
        start = at(MON, "11:00") - dt.timedelta(days=days_ago)
        b = Booking.objects.create(public_id=f"DQ-OLD-{who.pk}{days_ago:03d}", customer=who, staff=self.A, start=start,
                                   end=start + dt.timedelta(hours=1), status=status, total_price=Decimal("2200"), total_minutes=60)
        BookingItem.objects.create(booking=b, service=self.facial, service_name="Facial", unit_price=Decimal("2200"), duration_minutes=60)
        return b


class ApiAccessTests(PortalCase):
    ENDPOINTS = ("client:api_services", "client:api_dates", "client:api_slots", "client:api_staff", "client:api_summary")

    def test_anonymous_gets_json_401_not_a_redirect(self):
        self.client.logout()
        for name in self.ENDPOINTS:
            r = self.client.get(reverse(name))
            self.assertEqual((r.status_code, r.json()["code"]), (401, "auth_required"), name)
        self.assertEqual(self.client.post(reverse("client:api_book"), "{}", content_type="application/json").status_code, 401)

    def test_salon_team_cannot_use_customer_api(self):
        User.objects.create_user("emp", "emp@x.com", "pw12345!x", role="staff")
        self.client.login(username="emp", password="pw12345!x")
        for name in self.ENDPOINTS:
            self.assertEqual(self.get(name).status_code, 403, name)

    def test_wrong_method_is_405(self):
        self.assertEqual(self.client.post(reverse("client:api_services")).status_code, 405)
        self.assertEqual(self.client.get(reverse("client:api_book")).status_code, 405)

    def test_book_requires_csrf_token(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        body = json.dumps({"services": [self.facial.pk], "start": at(TUE, "12:00").isoformat()})
        self.assertEqual(strict.post(reverse("client:api_book"), body, content_type="application/json").status_code, 403)
        self.assertEqual(Booking.objects.count(), 0)


class WizardReadTests(PortalCase):
    def test_services_lists_only_bookable_active(self):
        data = self.get("client:api_services").json()
        names = [s["name"] for c in data["categories"] for s in c["services"]]
        self.assertEqual(sorted(names), ["Colour", "Cut", "Facial", "Peel"])      # "Course" is enquiry-only
        Service.objects.filter(pk=self.cut.pk).update(is_active=False)
        names = [s["name"] for c in self.get("client:api_services").json()["categories"] for s in c["services"]]
        self.assertNotIn("Cut", names)
        facial = next(s for c in data["categories"] for s in c["services"] if s["name"] == "Facial")
        self.assertEqual((facial["price"], facial["duration_minutes"], facial["duration_label"]), ("2200.00", 60, "1 h"))

    def test_dates(self):
        r = self.get("client:api_dates", services=f"{self.facial.pk}", staff=self.A.pk).json()
        self.assertIn(TUE.isoformat(), r["dates"])
        self.assertNotIn(SUN.isoformat(), r["dates"])
        self.assertEqual(r["total_minutes"], 60)
        self.assertEqual(r["window"]["first"], MON.isoformat())
        self.assertEqual(self.get("client:api_dates", services="").status_code, 400)
        self.assertEqual(self.get("client:api_dates", services="abc").json()["code"], "bad_service")
        r = self.get("client:api_dates", services=f"{self.facial.pk},{self.cut.pk}")
        self.assertEqual((r.status_code, r.json()["code"]), (400, "no_staff"))
        self.assertEqual(self.get("client:api_dates", services=f"{self.facial.pk}", staff=self.C.pk).json()["code"], "bad_staff")

    def test_slots_show_available_and_unavailable(self):
        wf_book = lambda: self.post_book()
        self.assertEqual(wf_book().status_code, 201)
        r = self.get("client:api_slots", services=self.facial.pk, date=TUE.isoformat(), staff=self.A.pk).json()
        by = {s["time"]: s for s in r["slots"]}
        self.assertTrue(by["10:00"]["available"] and by["11:00"]["available"] and by["13:00"]["available"])
        self.assertFalse(by["11:15"]["available"] or by["12:00"]["available"] or by["12:45"]["available"])
        self.assertEqual(by["10:00"]["label"], "10:00 AM")
        self.assertEqual(by["13:00"]["label"], "1:00 PM")
        self.assertTrue(by["10:00"]["start"].endswith("+05:30"))
        any_ = {s["time"]: s for s in self.get("client:api_slots", services=self.facial.pk, date=TUE.isoformat()).json()["slots"]}
        self.assertEqual(any_["12:00"]["staff_ids"], [self.B.pk])            # salon-wide: Kavya still free
        self.assertEqual(self.get("client:api_slots", services=self.facial.pk, date="nope").json()["code"], "bad_date")
        self.assertEqual(self.get("client:api_slots", services=self.facial.pk, date=SUN.isoformat()).json()["slots"], [])
        self.assertEqual(self.get("client:api_slots", services=self.facial.pk, date="2026-11-22").json()["slots"], [])

    def test_staff_endpoint(self):
        r = self.get("client:api_staff", services=self.facial.pk).json()
        self.assertEqual([p["name"] for p in r["staff"]], ["Dhanya", "Kavya"])
        self.assertTrue(r["any_available"] and all(p["available"] for p in r["staff"]))
        self.post_book(start=at(TUE, "12:00").isoformat())
        r = self.get("client:api_staff", services=self.facial.pk, start=at(TUE, "12:00").isoformat()).json()
        self.assertEqual({p["name"]: p["available"] for p in r["staff"]}, {"Dhanya": False, "Kavya": True})
        r = self.get("client:api_staff", services=self.facial.pk, start=at(TUE, "20:00").isoformat()).json()
        self.assertFalse(r["any_available"])
        self.assertEqual(self.get("client:api_staff", services=f"{self.facial.pk},{self.cut.pk}").json()["code"], "no_staff")

    def test_summary_is_computed_from_the_database(self):
        r = self.get("client:api_summary", services=f"{self.facial.pk},{self.peel.pk}", staff=self.A.pk,
                     start=at(TUE, "10:00").isoformat(), price="1", total_price="1", total_minutes="5").json()   # tampering ignored
        self.assertEqual((r["total_price"], r["total_minutes"], r["assignment"], r["staff"]["name"]), ("3200.00", 90, "specific", "Dhanya"))
        self.assertEqual((r["time_label"], r["end"][11:16]), ("10:00 AM", "11:30"))
        auto = self.get("client:api_summary", services=self.facial.pk).json()
        self.assertEqual((auto["assignment"], auto["staff"]), ("auto", None))
        self.post_book()
        r = self.get("client:api_summary", services=self.facial.pk, staff=self.A.pk, start=at(TUE, "12:00").isoformat())
        self.assertEqual((r.status_code, r.json()["code"]), (409, "slot_unavailable"))
        r = self.get("client:api_summary", services=self.facial.pk, start="garbage")
        self.assertEqual(r.json()["code"], "bad_time")


class BookEndpointTests(PortalCase):
    def test_success_payload_and_database_state(self):
        r = self.post_book(notes="First visit")
        self.assertEqual(r.status_code, 201)
        b = r.json()["booking"]
        self.assertRegex(b["public_id"], r"^DQ-\d{6}-[A-Z0-9]{4}$")
        self.assertEqual((b["status"], b["total_price"], b["total_minutes"], b["staff"]["name"], b["can_change"]), ("pending", "2200.00", 60, "Dhanya", True))
        self.assertEqual(b["url"], reverse("client:booking_detail", args=[b["public_id"]]))
        row = Booking.objects.get(public_id=b["public_id"])
        self.assertEqual((row.customer, row.notes, row.items.count()), (self.alice, "First visit", 1))

    def test_client_supplied_money_status_and_owner_are_ignored(self):
        r = self.post_book(price="1", total_price="1.00", total_minutes=5, status="confirmed", customer=self.bob.pk,
                           end=at(TUE, "12:05").isoformat(), unit_price="1", items=[{"price": 1}])
        self.assertEqual(r.status_code, 201)
        row = Booking.objects.get()
        self.assertEqual((row.status, row.customer, row.total_price, row.total_minutes), ("pending", self.alice, Decimal("2200.00"), 60))
        self.assertEqual(row.end - row.start, dt.timedelta(hours=1))

    def test_conflicts_are_409_and_leave_one_booking(self):
        self.assertEqual(self.post_book().status_code, 201)
        self.client.force_login(self.bob)
        r = self.post_book()
        self.assertEqual((r.status_code, r.json()["code"]), (409, "slot_unavailable"))
        self.client.force_login(self.alice)
        r = self.post_book(staff=self.B.pk, start=at(TUE, "12:30").isoformat())
        self.assertEqual((r.status_code, r.json()["code"]), (409, "customer_overlap"))
        self.assertEqual(Booking.objects.count(), 1)

    def test_validation_errors_are_400(self):
        cases = [({"services": []}, "no_service"), ({"services": "1"}, "no_service"), ({"services": [self.academy.pk]}, "bad_service"),
                 ({"start": "tomorrow"}, "bad_time"), ({"start": None}, "bad_time"), ({"start": 12345}, "bad_time"),
                 ({"staff": self.C.pk}, "bad_staff"), ({"staff": "zzz"}, "bad_staff"), ({"staff": [1]}, "bad_staff"),
                 ({"start": at(SUN, "11:00").isoformat()}, "slot_unavailable")]
        for over, code in cases:
            r = self.post_book(**over)
            self.assertEqual(r.json()["code"], code, over)
            self.assertIn(r.status_code, (400, 409))
        self.assertEqual(Booking.objects.count(), 0)

    def test_malformed_bodies(self):
        url = reverse("client:api_book")
        for body, ctype in (("{not json", "application/json"), ("[1,2]", "application/json"), ("services=1", "application/x-www-form-urlencoded")):
            r = self.client.post(url, body, content_type=ctype)
            self.assertEqual((r.status_code, r.json()["code"]), (400, "bad_request"), body)

    def test_any_staff_choice_is_recorded(self):
        r = self.post_book(staff="any")
        self.assertTrue(r.json()["booking"]["any_staff"])


class PageTests(PortalCase):
    def test_pages_need_a_customer_login(self):
        names = ["client:dashboard", "client:book", "client:bookings", "client:offers", "client:billing"]
        self.client.logout()
        for n in names:
            r = self.client.get(reverse(n))
            self.assertEqual(r.status_code, 302, n)
            self.assertTrue(r["Location"].startswith("/accounts/login/?next="))
        User.objects.create_user("emp", "emp@x.com", "pw12345!x", role="admin")
        self.client.login(username="emp", password="pw12345!x")
        for n in names:
            self.assertEqual(self.client.get(reverse(n)).status_code, 403, n)

    def test_dashboard_shows_only_my_data(self):
        mine_pending = wf_book(self, self.alice, TUE, "12:00")
        mine_confirmed = wf_book(self, self.alice, WED, "12:00")
        Booking.objects.filter(pk=mine_confirmed.pk).update(status="confirmed")
        theirs = wf_book(self, self.bob, TUE, "15:00")
        done = self.past_booking(self.alice, 5)
        self.past_booking(self.bob, 6)
        cancelled = wf_book(self, self.alice, WED, "15:00")
        Booking.objects.filter(pk=cancelled.pk).update(status="cancelled")
        r = self.get("client:dashboard")
        self.assertEqual(r.status_code, 200)
        c = r.context
        self.assertEqual([b.pk for b in c["upcoming"]], [mine_pending.pk, mine_confirmed.pk])
        self.assertEqual([b.pk for b in c["pending"]], [mine_pending.pk])
        self.assertEqual([b.pk for b in c["confirmed"]], [mine_confirmed.pk])
        self.assertEqual(c["next_booking"].pk, mine_pending.pk)
        self.assertEqual([b.pk for b in c["completed"]], [done.pk])
        self.assertEqual({b.pk for b in c["history"]}, {done.pk, cancelled.pk})
        self.assertEqual([d for d, _ in c["timeline"]], [TUE, WED])
        self.assertNotContains(r, theirs.public_id)
        self.assertEqual(c["totals"], {"all": 4, "completed": 1})
        self.assertEqual(c["invoices"], [])

    def test_dashboard_empty_state_and_offers(self):
        today = timezone.localdate()
        Offer.objects.create(title="Live", summary="s", discount_value=10, valid_from=today - dt.timedelta(days=1), valid_to=today + dt.timedelta(days=5))
        Offer.objects.create(title="Expired", summary="s", discount_value=10, valid_from=today - dt.timedelta(days=9), valid_to=today - dt.timedelta(days=2))
        Offer.objects.create(title="Off", summary="s", discount_value=10, valid_from=today - dt.timedelta(days=1), valid_to=today + dt.timedelta(days=5), is_active=False)
        r = self.get("client:dashboard")
        self.assertContains(r, "Nothing booked yet")
        self.assertEqual([o.title for o in r.context["offers"]], ["Live"])
        self.assertEqual([o.title for o in self.get("client:offers").context["offers"]], ["Live"])

    def test_service_param_hands_off_to_wizard(self):
        r = self.get("client:dashboard", service=self.facial.pk)
        self.assertRedirects(r, f"{reverse('client:book')}?service={self.facial.pk}", fetch_redirect_response=False)
        self.assertEqual(self.get("client:book", service=self.facial.pk).context["preselect_service"], self.facial.pk)
        for bad in (self.academy.pk, 99999, "abc", ""):
            self.assertIsNone(self.get("client:book", service=bad).context["preselect_service"], bad)
        self.assertEqual(self.get("client:dashboard", service="abc").status_code, 200)

    def test_history_tabs_and_pagination(self):
        for d in range(1, 13):
            self.past_booking(self.alice, d)
        self.past_booking(self.bob, 3)
        up = wf_book(self, self.alice, TUE, "12:00")
        self.assertEqual([b.pk for b in self.get("client:bookings").context["page"]], [up.pk])
        r = self.get("client:bookings", tab="past")
        self.assertEqual((len(r.context["page"]), r.context["page"].paginator.num_pages), (10, 2))
        self.assertEqual(len(self.get("client:bookings", tab="past", page=2).context["page"]), 2)
        self.assertEqual(self.get("client:bookings", tab="all").context["page"].paginator.count, 13)
        self.assertEqual(self.get("client:bookings", tab="junk").context["tab"], "all")

    def test_detail_is_private(self):
        mine = wf_book(self, self.alice, TUE, "12:00")
        theirs = wf_book(self, self.bob, TUE, "15:00")
        r = self.client.get(reverse("client:booking_detail", args=[mine.public_id]))
        self.assertContains(r, mine.public_id)
        self.assertContains(r, "Cancel appointment")
        self.assertEqual(self.client.get(reverse("client:booking_detail", args=[theirs.public_id])).status_code, 404)
        self.assertEqual(self.client.get(reverse("client:booking_detail", args=["DQ-NOPE"])).status_code, 404)
        with patch("bookings.availability._now", return_value=at(TUE, "10:00")):   # inside the 4 h window
            self.assertNotContains(self.client.get(reverse("client:booking_detail", args=[mine.public_id])), "Cancel appointment")

    def test_billing_page_ready_for_phase_5(self):
        self.assertContains(self.get("client:billing"), "No invoices yet")


class ChangeEndpointTests(PortalCase):
    def setUp(self):
        super().setUp()
        self.b = wf_book(self, self.alice, TUE, "12:00")
        self.cancel = reverse("client:booking_cancel", args=[self.b.public_id])
        self.resched = reverse("client:booking_reschedule", args=[self.b.public_id])

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.cancel).status_code, 405)
        self.assertEqual(self.client.get(self.resched).status_code, 405)

    def test_form_cancel_redirects_with_message(self):
        r = self.client.post(self.cancel, follow=True)
        self.assertContains(r, "Your booking has been cancelled.")
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, "cancelled")

    def test_json_cancel_and_reschedule(self):
        r = self.client.post(self.resched, {"note": "Later please"}, headers=FETCH)
        self.assertEqual((r.status_code, r.json()["booking"]["reschedule_requested"]), (200, True))
        r = self.client.post(self.resched, headers=FETCH)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "already_requested"))
        r = self.client.post(self.cancel, headers=FETCH)
        self.assertEqual((r.json()["booking"]["status"], r.json()["booking"]["can_change"]), ("cancelled", False))
        self.assertEqual(self.client.post(self.cancel, headers=FETCH).json()["code"], "not_changeable")

    def test_other_customers_cannot_touch_it(self):
        self.client.force_login(self.bob)
        for url in (self.cancel, self.resched):
            r = self.client.post(url, headers=FETCH)
            self.assertEqual((r.status_code, r.json()["code"]), (404, "not_found"))
            r = self.client.post(url)                                   # plain form post: message + redirect, no change
            self.assertRedirects(r, reverse("client:bookings"), fetch_redirect_response=False)
        self.b.refresh_from_db()
        self.assertEqual((self.b.status, self.b.reschedule_requested_at), ("pending", None))

    def test_cutoff_enforced_over_http(self):
        with patch("bookings.availability._now", return_value=at(TUE, "09:00")):
            r = self.client.post(self.cancel, headers=FETCH)
            self.assertEqual((r.status_code, r.json()["code"]), (409, "too_late"))
            r = self.client.post(self.cancel, follow=True)
            self.assertContains(r, "Changes are only possible up to 4 hours")
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, "pending")


def wf_book(case, who, day, hhmm, services=None, staff=None):
    return _wf.create_booking(customer=who, service_ids=[s.pk for s in (services or [case.facial])],
                              start=at(day, hhmm), staff_id=(staff or case.A).pk)


class UiContractTests(PortalCase):
    """Server-rendered pieces the portal scripts and no-JS fallback rely on."""

    def test_wizard_shell_wires_every_endpoint_and_sets_csrf_cookie(self):
        r = self.get("client:book", service=self.facial.pk)
        html = r.content.decode()
        for attr, name in (("data-api-services", "client:api_services"), ("data-api-dates", "client:api_dates"), ("data-api-slots", "client:api_slots"),
                           ("data-api-staff", "client:api_staff"), ("data-api-summary", "client:api_summary"), ("data-api-book", "client:api_book")):
            self.assertIn(f'{attr}="{reverse(name)}"', html)
        self.assertIn(f'data-preselect="{self.facial.pk}"', html)
        self.assertIn('data-cancel-hours="4"', html)
        self.assertIn("csrftoken", r.cookies)                                  # the wizard POSTs JSON with X-CSRFToken
        self.assertIn("js/portal/wizard.js", html)
        self.assertIn("<noscript>", html)
        self.assertNotIn("js/portal/wizard.js", self.get("client:dashboard").content.decode())
        self.assertIn("js/portal/portal.js", self.get("client:dashboard").content.decode())

    def test_every_portal_page_has_nav_confirm_dialog_and_assets(self):
        for name in ("client:dashboard", "client:bookings", "client:offers", "client:billing", "client:book"):
            html = self.get(name).content.decode()
            self.assertIn("css/portal/portal.css", html, name)
            self.assertIn('id="confirm-dialog"', html, name)
            self.assertIn('class="portal-nav"', html, name)
            self.assertEqual(html.count('aria-current="page"'), 1, name)

    def test_dashboard_greeting_follows_salon_time(self):
        for hhmm, word in (("08:00", "Good morning"), ("13:00", "Good afternoon"), ("19:00", "Good evening")):
            with patch("bookings.availability._now", return_value=at(MON, hhmm)):
                r = self.get("client:dashboard")
            self.assertEqual(r.context["greeting"], word)
            self.assertContains(r, word)
        self.assertContains(r, "<h1 class=\"p-rise\">alice<em>")

    def test_dashboard_ticket_timeline_and_status_classes(self):
        b = wf_book(self, self.alice, TUE, "12:00")
        r = self.get("client:dashboard")
        self.assertContains(r, 'class="ticket"')
        self.assertContains(r, "status status-pending")
        self.assertContains(r, b.public_id)
        self.assertContains(r, 'data-count="1"')

    def test_booking_list_counts_and_empty_state(self):
        r = self.get("client:bookings")
        self.assertEqual(r.context["counts"], {"upcoming": 0, "past": 0, "all": 0})
        self.assertContains(r, "No upcoming visits.")
        wf_book(self, self.alice, TUE, "12:00")
        self.past_booking(self.alice, 3)
        self.past_booking(self.bob, 3)
        self.assertEqual(self.get("client:bookings").context["counts"], {"upcoming": 1, "past": 1, "all": 2})

    def test_detail_forms_work_without_javascript(self):
        b = wf_book(self, self.alice, TUE, "12:00")
        html = self.client.get(reverse("client:booking_detail", args=[b.public_id])).content.decode()
        self.assertIn(f'action="{reverse("client:booking_cancel", args=[b.public_id])}"', html)
        self.assertIn(f'action="{reverse("client:booking_reschedule", args=[b.public_id])}"', html)
        self.assertEqual(html.count("data-action-form"), 2)
        self.assertEqual(html.count("csrfmiddlewaretoken"), 2)
        self.assertIn('data-confirm-title="Cancel this appointment?"', html)
        self.assertIn("status-lg", html)

    def test_detail_states(self):
        b = wf_book(self, self.alice, TUE, "12:00")
        url = reverse("client:booking_detail", args=[b.public_id])
        self.assertContains(self.client.get(url), '<li class="done">')            # "Requested" step reached
        wf_request = __import__("bookings.workflow", fromlist=["x"]).request_reschedule
        wf_request(b.public_id, self.alice, "Later please")
        r = self.client.get(url)
        self.assertContains(r, "Reschedule requested")
        self.assertNotContains(r, 'name="note"')                                   # cannot ask twice
        Booking.objects.filter(pk=b.pk).update(status="cancelled")
        r = self.client.get(url)
        self.assertContains(r, "was cancelled")
        self.assertNotContains(r, "Cancel appointment")
        self.assertNotContains(r, '<ol class="progress"')

    def test_wizard_script_never_injects_server_text_as_html(self):
        import pathlib
        js = (pathlib.Path(__file__).resolve().parent.parent / "static/js/portal/wizard.js").read_text()
        self.assertEqual(js.count("innerHTML"), 2, "only the static check-mark SVG (plus its comment) may use innerHTML")
        portal = (pathlib.Path(__file__).resolve().parent.parent / "static/js/portal/portal.js").read_text()
        self.assertNotIn("innerHTML", portal)
