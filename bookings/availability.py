"""Appointment availability: the single source of truth for "can this beautician take this slot?".

Both the wizard's slot picker and the final booking recheck call the same functions, so what a
customer is shown is exactly what the backend will accept. Nothing here trusts client input:
callers pass service IDs and a start time, and prices/durations/capabilities come from the database.

Tunable policy (all optional settings, read at call time):
    BOOKING_SLOT_MINUTES   grid step between start times            (default 15)
    BOOKING_LEAD_MINUTES   minimum notice before an appointment     (default 60)
    BOOKING_ADVANCE_DAYS   how far ahead customers may book         (default 60)
    BOOKING_MAX_SERVICES   services allowed in one booking          (default 8)
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from core.models import BusinessHour, Holiday
from services.models import Service
from staff.models import StaffLeave, StaffProfile, StaffSchedule

from .models import BLOCKING_STATUSES, Booking


class BookingError(Exception):
    """A booking rule was broken. `message` is safe to show to the customer; `code` is for the UI/tests."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


def policy(name: str, default: int) -> int:
    return getattr(settings, name, default)


def _now() -> dt.datetime:
    """Single clock for the whole booking engine (tests patch this)."""
    return timezone.now()


def local_today() -> dt.date:
    return timezone.localdate(_now())


def aware(day: dt.date, t: dt.time) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, t), timezone.get_current_timezone())


# ── Services and staff ────────────────────────────────────────────────────────

def resolve_services(service_ids) -> list[Service]:
    """Turn client-submitted IDs into real, bookable Service rows (order kept, duplicates dropped)."""
    ids: list[int] = []
    for raw in service_ids or []:
        try:
            i = int(raw)
        except (TypeError, ValueError):
            raise BookingError("That service selection is not valid.", "bad_service")
        if i not in ids:
            ids.append(i)
    if not ids:
        raise BookingError("Choose at least one service.", "no_service")
    if len(ids) > policy("BOOKING_MAX_SERVICES", 8):
        raise BookingError("Too many services in one booking. Please split them into separate visits.", "too_many")
    found = {s.pk: s for s in Service.objects.bookable().filter(pk__in=ids)}
    if any(i not in found for i in ids):
        raise BookingError("One or more of the selected services cannot be booked online.", "bad_service")
    return [found[i] for i in ids]


def total_minutes(services) -> int:
    return sum(s.duration_minutes for s in services)


def eligible_staff(services) -> list[StaffProfile]:
    """Active beauticians who can perform *every* selected service."""
    ids = [s.pk for s in services]
    return list(
        StaffProfile.objects.filter(is_active=True, services__in=ids)
        .annotate(matched=Count("services", distinct=True))
        .filter(matched=len(ids))
        .order_by("order", "name")
    )


def candidates(services, staff=None) -> list[StaffProfile]:
    """Eligible beauticians, narrowed to one if the customer chose a specific person."""
    pool = eligible_staff(services)
    if staff is not None:
        try:
            sid = int(getattr(staff, "pk", staff))
        except (TypeError, ValueError):
            raise BookingError("That beautician is not available for the selected services.", "bad_staff")
        pool = [p for p in pool if p.pk == sid]
        if not pool:
            raise BookingError("That beautician is not available for the selected services.", "bad_staff")
    if not pool:
        raise BookingError("No beautician is available for this combination of services. Try booking them separately.", "no_staff")
    return pool


# ── Data loading (one set of queries per request, not per slot) ───────────────

@dataclass
class Context:
    hours: dict
    holidays: set
    schedules: dict
    blocks: dict = field(default_factory=lambda: defaultdict(list))   # staff_id -> [(start, end)] leave + bookings
    bookings: dict = field(default_factory=lambda: defaultdict(list))  # staff_id -> [(start, end)] bookings only


def load_context(staff_list, first_day: dt.date, last_day: dt.date) -> Context:
    lo = aware(first_day, dt.time.min)
    hi = aware(last_day + dt.timedelta(days=1), dt.time.min)
    ctx = Context(
        hours={h.weekday: h for h in BusinessHour.objects.all()},
        holidays=set(Holiday.objects.filter(date__range=(first_day, last_day)).values_list("date", flat=True)),
        schedules={(s.staff_id, s.weekday): s for s in StaffSchedule.objects.filter(staff__in=staff_list)},
    )
    for sid, s, e in StaffLeave.objects.filter(staff__in=staff_list, is_approved=True, start__lt=hi, end__gt=lo).values_list("staff_id", "start", "end"):
        ctx.blocks[sid].append((s, e))
    for sid, s, e in Booking.objects.filter(staff__in=staff_list, status__in=BLOCKING_STATUSES, start__lt=hi, end__gt=lo).values_list("staff_id", "start", "end"):
        ctx.blocks[sid].append((s, e))
        ctx.bookings[sid].append((s, e))
    return ctx


# ── Slot computation ──────────────────────────────────────────────────────────

def day_grid(ctx: Context, staff_id: int, day: dt.date, minutes: int, now: dt.datetime) -> list[tuple[dt.datetime, bool]]:
    """Every start time on the grid for this beautician and day, flagged free or not."""
    if day in ctx.holidays:
        return []
    hours = ctx.hours.get(day.weekday())
    sched = ctx.schedules.get((staff_id, day.weekday()))
    if not hours or hours.is_closed or not hours.opens or not hours.closes or not sched:
        return []
    window_start = aware(day, max(hours.opens, sched.start_time))
    window_end = aware(day, min(hours.closes, sched.end_time))
    step = dt.timedelta(minutes=policy("BOOKING_SLOT_MINUTES", 15))
    length = dt.timedelta(minutes=minutes)
    earliest = now + dt.timedelta(minutes=policy("BOOKING_LEAD_MINUTES", 60))
    blocks = ctx.blocks.get(staff_id, [])
    out, cur = [], window_start
    while cur + length <= window_end:
        end = cur + length
        free = cur >= earliest and not any(b0 < end and b1 > cur for b0, b1 in blocks)
        out.append((cur, free))
        cur += step
    return out


def free_starts(ctx: Context, staff_id: int, day: dt.date, minutes: int, now: dt.datetime) -> set[dt.datetime]:
    return {t for t, free in day_grid(ctx, staff_id, day, minutes, now) if free}


def _within_booking_window(day: dt.date) -> bool:
    today = local_today()
    return today <= day <= today + dt.timedelta(days=policy("BOOKING_ADVANCE_DAYS", 60))


@dataclass
class Slot:
    start: dt.datetime
    end: dt.datetime
    staff_ids: list[int]

    @property
    def available(self) -> bool:
        return bool(self.staff_ids)


def slots_for_date(services, day: dt.date, staff=None, include_unavailable: bool = False) -> list[Slot]:
    """Start times for `day`. Each Slot lists the beauticians free at that time (empty = unavailable).

    With `staff=None` a time is available if *any* eligible beautician is free, which is what
    "assign the best available" needs; `staff_ids` then says who.
    """
    pool = candidates(services, staff)
    if not _within_booking_window(day):
        return []
    minutes = total_minutes(services)
    now = _now()
    ctx = load_context(pool, day, day)
    merged: dict[dt.datetime, list[int]] = {}
    for p in pool:
        for start, free in day_grid(ctx, p.pk, day, minutes, now):
            merged.setdefault(start, [])
            if free:
                merged[start].append(p.pk)
    length = dt.timedelta(minutes=minutes)
    slots = [Slot(s, s + length, ids) for s, ids in sorted(merged.items())]
    return slots if include_unavailable else [s for s in slots if s.available]


def bookable_dates(services, staff=None, start: dt.date | None = None, days: int | None = None) -> list[dt.date]:
    """Dates in the booking window with at least one free slot (drives the calendar's enabled days)."""
    pool = candidates(services, staff)
    today = local_today()
    first = max(start or today, today)
    last = today + dt.timedelta(days=days if days is not None else policy("BOOKING_ADVANCE_DAYS", 60))
    minutes, now = total_minutes(services), _now()
    ctx = load_context(pool, first, last)
    out, day = [], first
    while day <= last:
        if any(free_starts(ctx, p.pk, day, minutes, now) for p in pool):
            out.append(day)
        day += dt.timedelta(days=1)
    return out
