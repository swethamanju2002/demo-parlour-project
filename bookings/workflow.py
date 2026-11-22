"""Booking actions: create, cancel, request reschedule.

Every function re-validates against the database inside a transaction. Customers only ever send
service IDs, a start time and (optionally) a beautician ID. Price, duration, end time and who is
allowed to touch which booking are all decided here.
"""
from __future__ import annotations

import datetime as dt
import secrets
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from staff.models import StaffProfile

from . import availability as av
from .availability import BookingError
from .models import BLOCKING_STATUSES, Booking, BookingItem

_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I, easier to read out over the phone
CANCELLABLE = (Booking.Status.PENDING, Booking.Status.CONFIRMED)


def generate_public_id(on: dt.date | None = None) -> str:
    on = on or av.local_today()
    return f"DQ-{on:%y%m%d}-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(4))


def _normalise_start(start) -> dt.datetime:
    if not isinstance(start, dt.datetime):
        raise BookingError("Choose a valid appointment time.", "bad_time")
    return timezone.make_aware(start) if timezone.is_naive(start) else start


def create_booking(*, customer, service_ids, start, staff_id=None, notes: str = "") -> Booking:
    """Create a PENDING booking, or raise BookingError. Safe against double booking."""
    services = av.resolve_services(service_ids)
    start = _normalise_start(start)
    minutes = av.total_minutes(services)
    end = start + dt.timedelta(minutes=minutes)
    day = timezone.localtime(start).date()
    if not av._within_booking_window(day):
        raise BookingError("That date is outside the booking window.", "bad_date")

    with transaction.atomic():
        pool = av.candidates(services, staff_id)
        # Serialise competing bookings for the same beauticians (a real lock on PostgreSQL; SQLite is
        # serialised by the IMMEDIATE transaction mode set in settings). Fixed order avoids deadlocks.
        list(StaffProfile.objects.select_for_update().filter(pk__in=[p.pk for p in pool]).order_by("pk"))

        limit = av.policy("BOOKING_MAX_ACTIVE", 5)
        if Booking.objects.filter(customer=customer, status__in=CANCELLABLE, end__gt=av._now()).count() >= limit:
            raise BookingError(f"You have {limit} upcoming bookings already. Please attend or cancel one before booking another.", "too_many_active")

        if Booking.objects.filter(customer=customer, status__in=BLOCKING_STATUSES, start__lt=end, end__gt=start).exists():
            raise BookingError("You already have an appointment that overlaps this time.", "customer_overlap")

        now = av._now()
        ctx = av.load_context(pool, day, day)
        free = [p for p in pool if start in av.free_starts(ctx, p.pk, day, minutes, now)]
        if not free:
            raise BookingError("Sorry, that time is no longer available. Please pick another slot.", "slot_unavailable")

        def load(p):  # appointments already on that day: spread work evenly when the salon chooses
            return sum(1 for s, _ in ctx.bookings.get(p.pk, []) if timezone.localtime(s).date() == day)

        chosen = min(free, key=lambda p: (load(p), p.order, p.name))

        for _ in range(8):
            try:
                with transaction.atomic():
                    booking = Booking.objects.create(
                        public_id=generate_public_id(), customer=customer, staff=chosen, start=start, end=end,
                        status=Booking.Status.PENDING, any_staff=staff_id in (None, ""),
                        total_price=sum((s.price for s in services), Decimal("0.00")),
                        total_minutes=minutes, notes=(notes or "").strip()[:1000],
                    )
                break
            except IntegrityError:  # public-id collision: draw another
                continue
        else:
            raise BookingError("We could not create your booking just now. Please try again.", "id_collision")

        BookingItem.objects.bulk_create([
            BookingItem(booking=booking, service=s, service_name=s.name, unit_price=s.price,
                        duration_minutes=s.duration_minutes, position=i)
            for i, s in enumerate(services)
        ])
    return booking


# ── Customer-side changes ─────────────────────────────────────────────────────

def get_customer_booking(public_id: str, customer, *, lock: bool = False) -> Booking:
    """Fetch a booking only if it belongs to `customer`. Someone else's ID looks identical to a missing one."""
    qs = Booking.objects.select_for_update() if lock else Booking.objects
    booking = qs.filter(public_id=public_id, customer=customer).first()
    if booking is None:
        raise BookingError("We could not find that booking.", "not_found")
    return booking


def change_deadline(booking: Booking) -> dt.datetime:
    return booking.start - dt.timedelta(hours=av.policy("BOOKING_CANCEL_HOURS", 4))


def can_change(booking: Booking) -> bool:
    return booking.status in CANCELLABLE and av._now() <= change_deadline(booking)


def _check_changeable(booking: Booking, verb: str) -> None:
    if booking.status not in CANCELLABLE:
        raise BookingError(f"This booking can no longer be {verb}.", "not_changeable")
    if av._now() > change_deadline(booking):
        hours = av.policy("BOOKING_CANCEL_HOURS", 4)
        raise BookingError(f"Changes are only possible up to {hours} hours before the appointment. Please contact the salon.", "too_late")


def cancel_booking(public_id: str, customer) -> Booking:
    with transaction.atomic():
        booking = get_customer_booking(public_id, customer, lock=True)
        _check_changeable(booking, "cancelled")
        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = av._now()
        booking.save(update_fields=["status", "cancelled_at", "updated_at"])
    return booking


def request_reschedule(public_id: str, customer, note: str = "") -> Booking:
    """Flag a booking for the salon to move. The slot stays reserved until staff act on the request."""
    with transaction.atomic():
        booking = get_customer_booking(public_id, customer, lock=True)
        _check_changeable(booking, "rescheduled")
        if booking.reschedule_requested_at:
            raise BookingError("You have already asked to reschedule this booking. We will be in touch.", "already_requested")
        booking.reschedule_requested_at = av._now()
        booking.reschedule_note = (note or "").strip()[:300]
        booking.save(update_fields=["reschedule_requested_at", "reschedule_note", "updated_at"])
    return booking
