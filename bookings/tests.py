import datetime as dt
import re
from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from accounts.models import User
from bookings import availability as av
from bookings import workflow as wf
from bookings.availability import BookingError
from bookings.models import Booking
from core.models import BusinessHour, Holiday
from services.models import Service, ServiceCategory
from staff.models import StaffLeave, StaffProfile, StaffSchedule

NOW = av.aware(dt.date(2026, 11, 23), dt.time(8, 0))   # Monday 23 Nov 2026, 08:00 IST
MON, TUE, WED, SAT, SUN = (dt.date(2026, 11, d) for d in (23, 24, 25, 28, 29))


def at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return av.aware(day, dt.time(h, m))


def times(slots):
    return [s.start.astimezone(av.timezone.get_current_timezone()).strftime("%H:%M") for s in slots]


class EngineCase(TestCase):
    """Salon open Mon-Sat 10:00-19:30. Dhanya (A) and Kavya (B) do facials; Priya (C) does hair."""

    @classmethod
    def setUpTestData(cls):
        for wd in range(7):
            BusinessHour.objects.create(weekday=wd, opens=None if wd == 6 else dt.time(10), closes=None if wd == 6 else dt.time(19, 30), is_closed=wd == 6)
        skin, hair = (ServiceCategory.objects.create(name=n) for n in ("Skin Care", "Hair Care"))
        cls.facial = Service.objects.create(category=skin, name="Facial", description="x", price=Decimal("2200"), duration_minutes=60)
        cls.peel = Service.objects.create(category=skin, name="Peel", description="x", price=Decimal("1000"), duration_minutes=30)
        cls.colour = Service.objects.create(category=hair, name="Colour", description="x", price=Decimal("4200"), duration_minutes=120)
        cls.cut = Service.objects.create(category=hair, name="Cut", description="x", price=Decimal("700"), duration_minutes=45)
        cls.academy = Service.objects.create(category=hair, name="Course", description="x", price=Decimal("25000"), duration_minutes=60, is_bookable=False)
        cls.A = StaffProfile.objects.create(name="Dhanya", title="t", order=0)
        cls.B = StaffProfile.objects.create(name="Kavya", title="t", order=1)
        cls.C = StaffProfile.objects.create(name="Priya", title="t", order=2)
        cls.A.services.add(cls.facial, cls.peel, cls.colour)
        cls.B.services.add(cls.facial, cls.peel)
        cls.C.services.add(cls.cut, cls.colour)
        for s, end in ((cls.A, dt.time(19, 30)), (cls.B, dt.time(14, 0)), (cls.C, dt.time(19, 30))):
            for wd in range(6):
                StaffSchedule.objects.create(staff=s, weekday=wd, start_time=dt.time(10), end_time=end)
        cls.alice = User.objects.create_user("alice", "alice@x.com", "pw12345!x")
        cls.bob = User.objects.create_user("bob", "bob@x.com", "pw12345!x")

    def setUp(self):
        self.now = patch("bookings.availability._now", return_value=NOW)
        self.now.start()
        self.addCleanup(self.now.stop)

    def book(self, who, services, day, hhmm, staff=None):
        return wf.create_booking(customer=who, service_ids=[s.pk for s in services], start=at(day, hhmm), staff_id=staff.pk if staff else None)


class SlotRuleTests(EngineCase):
    def test_slots_follow_hours_and_duration(self):
        s = times(av.slots_for_date([self.facial], TUE, staff=self.A))
        self.assertEqual((s[0], s[-1], len(s)), ("10:00", "18:30", 35))   # 60-min service must end by 19:30
        s = times(av.slots_for_date([self.colour], TUE, staff=self.A))
        self.assertEqual(s[-1], "17:30")                                    # 120-min service
        s = times(av.slots_for_date([self.facial, self.peel], TUE, staff=self.A))
        self.assertEqual(s[-1], "18:00")                                    # durations combine: 90 min

    def test_closed_day_holiday_and_window(self):
        self.assertEqual(av.slots_for_date([self.facial], SUN), [])
        Holiday.objects.create(date=TUE, reason="Festival")
        self.assertEqual(av.slots_for_date([self.facial], TUE), [])
        self.assertEqual(av.slots_for_date([self.facial], dt.date(2026, 11, 22)), [])            # yesterday
        self.assertEqual(av.slots_for_date([self.facial], MON + dt.timedelta(days=61)), [])      # too far ahead

    def test_lead_time_hides_imminent_slots(self):
        with patch("bookings.availability._now", return_value=at(MON, "10:00")):
            self.assertEqual(times(av.slots_for_date([self.facial], MON, staff=self.A))[0], "11:00")   # 60-min notice

    def test_staff_working_hours_limit_slots(self):
        s = times(av.slots_for_date([self.facial], TUE, staff=self.B))
        self.assertEqual((s[0], s[-1]), ("10:00", "13:00"))                  # Kavya finishes at 14:00
        StaffSchedule.objects.filter(staff=self.B, weekday=1).delete()       # Tuesday off
        self.assertEqual(av.slots_for_date([self.facial], TUE, staff=self.B), [])

    def test_capability_filters_staff(self):
        self.assertEqual([p.name for p in av.eligible_staff([self.facial])], ["Dhanya", "Kavya"])
        self.assertEqual([p.name for p in av.eligible_staff([self.cut])], ["Priya"])
        self.assertEqual([p.name for p in av.eligible_staff([self.colour])], ["Dhanya", "Priya"])
        self.assertEqual(av.eligible_staff([self.facial, self.cut]), [])      # nobody does both
        with self.assertRaises(BookingError) as e:
            av.candidates([self.facial, self.cut])
        self.assertEqual(e.exception.code, "no_staff")
        with self.assertRaises(BookingError) as e:
            av.slots_for_date([self.facial], TUE, staff=self.C)              # Priya cannot do facials
        self.assertEqual(e.exception.code, "bad_staff")

    def test_inactive_staff_not_offered(self):
        StaffProfile.objects.filter(pk=self.B.pk).update(is_active=False)
        self.assertEqual([p.name for p in av.eligible_staff([self.facial])], ["Dhanya"])

    def test_leave_blocks_only_overlapping_slots(self):
        StaffLeave.objects.create(staff=self.A, start=at(TUE, "12:00"), end=at(TUE, "15:00"))
        s = times(av.slots_for_date([self.facial], TUE, staff=self.A))
        self.assertIn("11:00", s)          # ends exactly when leave starts
        self.assertNotIn("11:15", s)
        self.assertNotIn("14:45", s)
        self.assertIn("15:00", s)

    def test_unapproved_leave_does_not_block(self):
        StaffLeave.objects.create(staff=self.A, start=at(TUE, "10:00"), end=at(TUE, "19:30"), is_approved=False)
        self.assertEqual(len(av.slots_for_date([self.facial], TUE, staff=self.A)), 35)

    def test_multi_day_leave(self):
        StaffLeave.objects.create(staff=self.A, start=at(TUE, "00:00"), end=at(WED, "23:59"))
        self.assertEqual(av.slots_for_date([self.facial], WED, staff=self.A), [])
        self.assertTrue(av.slots_for_date([self.facial], SAT, staff=self.A))

    def test_existing_bookings_block_overlaps_but_allow_adjacent(self):
        self.book(self.alice, [self.facial], TUE, "12:00", self.A)          # 12:00-13:00
        s = times(av.slots_for_date([self.facial], TUE, staff=self.A))
        self.assertIn("11:00", s)
        self.assertNotIn("11:15", s)
        self.assertNotIn("12:45", s)
        self.assertIn("13:00", s)

    def test_pending_confirmed_block_cancelled_rejected_free(self):
        b = self.book(self.alice, [self.facial], TUE, "12:00", self.A)
        self.assertNotIn("12:00", times(av.slots_for_date([self.facial], TUE, staff=self.A)))       # pending blocks
        for status, blocks in (("confirmed", True), ("rejected", False), ("cancelled", False), ("completed", True)):
            Booking.objects.filter(pk=b.pk).update(status=status)
            self.assertEqual("12:00" not in times(av.slots_for_date([self.facial], TUE, staff=self.A)), blocks, status)

    def test_any_staff_slot_lists_who_is_free(self):
        self.book(self.alice, [self.facial], TUE, "12:00", self.A)
        slots = {t: s for t, s in zip(times(av.slots_for_date([self.facial], TUE, include_unavailable=True)), av.slots_for_date([self.facial], TUE, include_unavailable=True))}
        self.assertEqual(slots["12:00"].staff_ids, [self.B.pk])
        self.assertEqual(sorted(slots["10:00"].staff_ids), sorted([self.A.pk, self.B.pk]))
        self.assertEqual(slots["14:00"].staff_ids, [self.A.pk])             # Kavya has gone home

    def test_unavailable_slots_are_reported_when_asked(self):
        self.book(self.alice, [self.facial], TUE, "12:00", self.A)
        grid = av.slots_for_date([self.facial], TUE, staff=self.A, include_unavailable=True)
        taken = {t for t, s in zip(times(grid), grid) if not s.available}
        self.assertEqual(taken, {"11:15", "11:30", "11:45", "12:00", "12:15", "12:30", "12:45"})

    def test_bookable_dates(self):
        dates = av.bookable_dates([self.facial], staff=self.A)
        self.assertIn(MON, dates)
        self.assertIn(TUE, dates)
        self.assertNotIn(SUN, dates)                      # closed
        self.assertNotIn(dt.date(2026, 11, 22), dates)    # past
        self.assertLessEqual(dates[-1], MON + dt.timedelta(days=60))
        StaffLeave.objects.create(staff=self.A, start=at(TUE, "00:00"), end=at(WED, "00:00"))
        self.assertNotIn(TUE, av.bookable_dates([self.facial], staff=self.A))
        self.assertIn(TUE, av.bookable_dates([self.facial]))                 # Kavya still works
        StaffLeave.objects.create(staff=self.B, start=at(TUE, "00:00"), end=at(WED, "00:00"))
        self.assertNotIn(TUE, av.bookable_dates([self.facial]))


class CreateBookingTests(EngineCase):
    def test_happy_path_snapshots_server_side_values(self):
        b = self.book(self.alice, [self.facial, self.peel], TUE, "10:00", self.A)
        self.assertEqual((b.status, b.staff, b.total_minutes, b.total_price), ("pending", self.A, 90, Decimal("3200.00")))
        self.assertEqual(b.end - b.start, dt.timedelta(minutes=90))
        self.assertFalse(b.any_staff)
        self.assertEqual([(i.service_name, i.unit_price, i.duration_minutes) for i in b.items.all()],
                         [("Facial", Decimal("2200.00"), 60), ("Peel", Decimal("1000.00"), 30)])
        self.assertRegex(b.public_id, r"^DQ-261123-[A-HJ-NP-Z2-9]{4}$")

    def test_snapshot_survives_later_price_change(self):
        b = self.book(self.alice, [self.facial], TUE, "10:00", self.A)
        Service.objects.filter(pk=self.facial.pk).update(price=Decimal("9999"), duration_minutes=5)
        b.refresh_from_db()
        self.assertEqual(b.total_price, Decimal("2200.00"))
        self.assertEqual(b.items.get().unit_price, Decimal("2200.00"))
        self.assertEqual(b.total_minutes, 60)

    @override_settings(BOOKING_MAX_ACTIVE=50)
    def test_public_ids_unique_and_collisions_retried(self):
        ids = {self.book(self.alice if i % 2 else self.bob, [self.peel], TUE, f"{10 + i // 2}:{(i % 2) * 30:02d}", self.A).public_id for i in range(12)}
        self.assertEqual(len(ids), 12)
        first = Booking.objects.first().public_id
        seq = iter([first, first, "DQ-261123-ZZZZ"])
        with patch("bookings.workflow.generate_public_id", side_effect=lambda: next(seq)):
            b = self.book(self.bob, [self.peel], WED, "10:00", self.A)
        self.assertEqual(b.public_id, "DQ-261123-ZZZZ")

    def test_double_booking_same_staff_rejected(self):
        self.book(self.alice, [self.facial], TUE, "12:00", self.A)
        for hhmm in ("12:00", "12:30", "11:30"):
            with self.assertRaises(BookingError) as e:
                self.book(self.bob, [self.facial], TUE, hhmm, self.A)
            self.assertEqual(e.exception.code, "slot_unavailable", hhmm)
        self.assertEqual(Booking.objects.count(), 1)
        self.book(self.bob, [self.facial], TUE, "13:00", self.A)           # adjacent is fine

    def test_race_second_request_loses(self):
        """Both customers were shown 12:00; the later submit must be refused by the recheck."""
        shown = av.slots_for_date([self.peel], TUE, staff=self.A)
        self.assertIn("12:00", times(shown))
        self.book(self.alice, [self.peel], TUE, "12:00", self.A)
        with self.assertRaises(BookingError):
            self.book(self.bob, [self.peel], TUE, "12:00", self.A)

    def test_any_staff_fills_each_beautician_then_refuses(self):
        b1 = self.book(self.alice, [self.facial], TUE, "12:00")
        b2 = self.book(self.bob, [self.facial], TUE, "12:00")
        self.assertEqual((b1.staff, b2.staff), (self.A, self.B))           # tie broken by order, then the other
        self.assertTrue(b1.any_staff)
        carol = User.objects.create_user("carol", "c@x.com", "pw12345!x")
        with self.assertRaises(BookingError):
            self.book(carol, [self.facial], TUE, "12:00")

    def test_any_staff_picks_least_busy(self):
        self.book(self.alice, [self.peel], TUE, "10:00", self.A)           # A already has one that day
        b = self.book(self.bob, [self.facial], TUE, "12:00")
        self.assertEqual(b.staff, self.B)

    def test_staff_schedule_and_leave_enforced_on_create(self):
        with self.assertRaises(BookingError):
            self.book(self.alice, [self.facial], TUE, "14:00", self.B)      # B ends 14:00
        with self.assertRaises(BookingError):
            self.book(self.alice, [self.facial], SUN, "11:00", self.A)      # closed
        with self.assertRaises(BookingError):
            self.book(self.alice, [self.facial], TUE, "09:00", self.A)      # before opening
        with self.assertRaises(BookingError):
            self.book(self.alice, [self.facial], TUE, "18:45", self.A)      # would overrun closing
        StaffLeave.objects.create(staff=self.A, start=at(TUE, "12:00"), end=at(TUE, "15:00"))
        with self.assertRaises(BookingError):
            self.book(self.alice, [self.facial], TUE, "11:30", self.A)
        with self.assertRaises(BookingError):
            self.book(self.alice, [self.facial], TUE, "10:07", self.A)      # off the 15-minute grid
        self.assertEqual(Booking.objects.count(), 0)

    def test_past_and_too_soon_and_too_far_rejected(self):
        for day, hhmm in ((dt.date(2026, 11, 22), "11:00"), (MON, "08:30"), (MON, "09:30"), (MON + dt.timedelta(days=90), "11:00")):
            with self.assertRaises(BookingError):
                self.book(self.alice, [self.facial], day, hhmm, self.A)
        self.book(self.alice, [self.facial], MON, "10:00", self.A)          # 2 h notice is fine

    def test_client_cannot_choose_unbookable_inactive_or_bogus_services(self):
        for ids in ([self.academy.pk], [999999], ["abc"], [], None, [self.facial.pk, self.academy.pk]):
            with self.assertRaises(BookingError, msg=str(ids)):
                wf.create_booking(customer=self.alice, service_ids=ids, start=at(TUE, "10:00"))
        Service.objects.filter(pk=self.facial.pk).update(is_active=False)
        with self.assertRaises(BookingError):
            wf.create_booking(customer=self.alice, service_ids=[self.facial.pk], start=at(TUE, "10:00"))

    def test_staff_must_be_able_to_do_the_services(self):
        with self.assertRaises(BookingError) as e:
            self.book(self.alice, [self.facial], TUE, "10:00", self.C)
        self.assertEqual(e.exception.code, "bad_staff")
        with self.assertRaises(BookingError) as e:
            wf.create_booking(customer=self.alice, service_ids=[self.facial.pk], start=at(TUE, "10:00"), staff_id="x")
        self.assertEqual(e.exception.code, "bad_staff")

    def test_bad_start_values(self):
        for bad in ("2026-11-24 10:00", None, at(TUE, "10:00").date()):
            with self.assertRaises(BookingError):
                wf.create_booking(customer=self.alice, service_ids=[self.facial.pk], start=bad)
        naive = dt.datetime(2026, 11, 24, 10, 0)                              # naive is read as salon-local time
        self.assertEqual(wf.create_booking(customer=self.alice, service_ids=[self.facial.pk], start=naive, staff_id=self.A.pk).start, at(TUE, "10:00"))

    def test_customer_cannot_double_book_themselves(self):
        self.book(self.alice, [self.facial], TUE, "12:00", self.A)
        with self.assertRaises(BookingError) as e:
            self.book(self.alice, [self.facial], TUE, "12:30", self.B)
        self.assertEqual(e.exception.code, "customer_overlap")
        self.book(self.alice, [self.facial], TUE, "13:00", self.B)

    @override_settings(BOOKING_MAX_ACTIVE=2)
    def test_active_booking_cap(self):
        self.book(self.alice, [self.peel], TUE, "10:00", self.A)
        self.book(self.alice, [self.peel], TUE, "11:00", self.A)
        with self.assertRaises(BookingError) as e:
            self.book(self.alice, [self.peel], TUE, "12:00", self.A)
        self.assertEqual(e.exception.code, "too_many_active")
        self.book(self.bob, [self.peel], TUE, "12:00", self.A)                 # other customers unaffected
        wf.cancel_booking(Booking.objects.filter(customer=self.alice).first().public_id, self.alice)
        self.book(self.alice, [self.peel], TUE, "12:30", self.A)               # cancelling frees a place

    def test_cancelled_booking_frees_slot_for_others(self):
        b = self.book(self.alice, [self.facial], TUE, "12:00", self.A)
        wf.cancel_booking(b.public_id, self.alice)
        self.book(self.bob, [self.facial], TUE, "12:00", self.A)

    def test_db_constraints_back_up_the_rules(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            StaffSchedule.objects.create(staff=self.A, weekday=0, start_time=dt.time(10), end_time=dt.time(11))   # duplicate weekday
        with self.assertRaises(IntegrityError), transaction.atomic():
            StaffSchedule.objects.create(staff=self.A, weekday=6, start_time=dt.time(12), end_time=dt.time(11))
        with self.assertRaises(IntegrityError), transaction.atomic():
            StaffLeave.objects.create(staff=self.A, start=at(TUE, "12:00"), end=at(TUE, "11:00"))
        b = self.book(self.alice, [self.facial], TUE, "10:00", self.A)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.filter(pk=b.pk).update(end=b.start)


class CustomerChangeTests(EngineCase):
    def setUp(self):
        super().setUp()
        self.b = self.book(self.alice, [self.facial], TUE, "12:00", self.A)

    def test_ownership_is_enforced(self):
        for fn in (lambda: wf.cancel_booking(self.b.public_id, self.bob),
                   lambda: wf.request_reschedule(self.b.public_id, self.bob, "x"),
                   lambda: wf.get_customer_booking(self.b.public_id, self.bob),
                   lambda: wf.cancel_booking("DQ-000000-NOPE", self.alice)):
            with self.assertRaises(BookingError) as e:
                fn()
            self.assertEqual(e.exception.code, "not_found")
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, "pending")

    def test_cancel_before_cutoff(self):
        b = wf.cancel_booking(self.b.public_id, self.alice)
        self.assertEqual(b.status, "cancelled")
        self.assertIsNotNone(b.cancelled_at)
        with self.assertRaises(BookingError) as e:
            wf.cancel_booking(self.b.public_id, self.alice)
        self.assertEqual(e.exception.code, "not_changeable")

    def test_cancel_inside_four_hour_cutoff_refused(self):
        with patch("bookings.availability._now", return_value=at(TUE, "08:30")):       # 3.5 h before 12:00
            self.assertFalse(wf.can_change(self.b))
            with self.assertRaises(BookingError) as e:
                wf.cancel_booking(self.b.public_id, self.alice)
        self.assertEqual(e.exception.code, "too_late")
        with patch("bookings.availability._now", return_value=at(TUE, "08:00")):       # exactly 4 h: still allowed
            self.assertTrue(wf.can_change(self.b))
            wf.cancel_booking(self.b.public_id, self.alice)

    def test_finished_bookings_cannot_be_cancelled(self):
        for status in ("completed", "rejected", "cancelled"):
            Booking.objects.filter(pk=self.b.pk).update(status=status)
            with self.assertRaises(BookingError):
                wf.cancel_booking(self.b.public_id, self.alice)

    def test_reschedule_request(self):
        b = wf.request_reschedule(self.b.public_id, self.alice, "  Could we go later?  ")
        self.assertEqual(b.reschedule_note, "Could we go later?")
        self.assertIsNotNone(b.reschedule_requested_at)
        self.assertEqual(b.start, at(TUE, "12:00"))                                    # nothing moves until staff act
        with self.assertRaises(BookingError) as e:
            wf.request_reschedule(self.b.public_id, self.alice)
        self.assertEqual(e.exception.code, "already_requested")


class DemoSeedTests(EngineCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        StaffProfile.objects.all().delete()
        for i, n in enumerate(["Dhanya Q.", "Meenakshi R.", "Priya S.", "Kavya M."]):
            StaffProfile.objects.create(name=n, title="t", order=i)
        for cat, name, price, mins in (("Skin Care", "Signature Hydra Facial", 2200, 60), ("Hair Care", "Haircut and Styling", 700, 45),
                                       ("Bridal Makeup", "Bridal Makeup Trial", 3500, 90), ("PMU", "Lip Blush", 8000, 120)):
            c, _ = ServiceCategory.objects.get_or_create(name=cat)
            Service.objects.create(category=c, name=name, description="x", price=Decimal(price), duration_minutes=mins)
        User.objects.create_user("demo_customer", "dc@x.com", "pw12345!x")

    def test_seed_is_complete_idempotent_and_consistent(self):
        from bookings.demo import seed_booking_demo
        seed_booking_demo(); seed_booking_demo()
        self.assertEqual(Booking.objects.count(), 3)
        self.assertEqual(set(Booking.objects.values_list("status", flat=True)), {"completed", "confirmed", "pending"})
        self.assertEqual(StaffSchedule.objects.filter(staff__name="Priya S.").count(), 5)    # Wednesday off
        self.assertEqual(StaffLeave.objects.count(), 1)
        skin = Service.objects.get(name="Signature Hydra Facial")
        self.assertEqual({p.name for p in av.eligible_staff([skin])}, {"Dhanya Q.", "Kavya M."})
        for b in Booking.objects.all():                                                    # every booking sits inside real hours
            day = av.timezone.localtime(b.start).date()
            sched = StaffSchedule.objects.get(staff=b.staff, weekday=day.weekday())
            self.assertGreaterEqual(b.start, av.aware(day, max(sched.start_time, dt.time(10))))
            self.assertLessEqual(b.end, av.aware(day, min(sched.end_time, dt.time(19, 30))))
            self.assertFalse(Holiday.objects.filter(date=day).exists())
        for b in Booking.objects.exclude(status="completed"):
            self.assertGreater(b.start, NOW)
        self.assertLess(Booking.objects.get(status="completed").start, NOW)
