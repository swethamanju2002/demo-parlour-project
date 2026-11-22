"""Fictional scheduling and booking data for the demo. Idempotent: safe to run on every `seed_demo`."""
import datetime as dt

from django.utils import timezone

from accounts.models import User
from core.models import BusinessHour, Holiday
from services.models import Service
from staff.models import StaffLeave, StaffProfile, StaffSchedule

from .availability import aware
from .models import Booking, BookingItem
from .workflow import generate_public_id

# staff name -> service categories they can perform (Skin Care is shared so "any available" has a real choice)
CAPABILITIES = {
    "Dhanya Q.": ["Skin Care"],
    "Meenakshi R.": ["Bridal Makeup"],
    "Priya S.": ["Hair Care"],
    "Kavya M.": ["PMU", "Skin Care"],
}
OPEN, CLOSE = dt.time(10, 0), dt.time(19, 30)
# per-person exceptions to Mon-Sat 10:00-19:30: {name: {weekday: (start, end) or None for a day off}}
EXCEPTIONS = {
    "Meenakshi R.": {d: (dt.time(11, 0), CLOSE) for d in range(6)},
    "Priya S.": {2: None},                       # Wednesday off
    "Kavya M.": {5: (OPEN, dt.time(15, 0))},     # short Saturday
}


def _works(staff, day):
    hours = BusinessHour.objects.filter(weekday=day.weekday(), is_closed=False).exists()
    return (hours and not Holiday.objects.filter(date=day).exists()
            and StaffSchedule.objects.filter(staff=staff, weekday=day.weekday()).exists())


def _find_day(staff, start_offset, step=1):
    day = timezone.localdate() + dt.timedelta(days=start_offset)
    for _ in range(21):
        if _works(staff, day):
            return day
        day += dt.timedelta(days=step)
    return None


def _make(customer, staff, service_names, day, at, status):
    services = [Service.objects.filter(name=n).first() for n in service_names]
    if day is None or not all(services):
        return None
    start = aware(day, at)
    minutes = sum(s.duration_minutes for s in services)
    b = Booking.objects.create(
        public_id=generate_public_id(), customer=customer, staff=staff, start=start,
        end=start + dt.timedelta(minutes=minutes), status=status, total_minutes=minutes,
        total_price=sum(s.price for s in services), notes="Demo booking",
    )
    BookingItem.objects.bulk_create([
        BookingItem(booking=b, service=s, service_name=s.name, unit_price=s.price, duration_minutes=s.duration_minutes, position=i)
        for i, s in enumerate(services)])
    return b


def seed_booking_demo(write=lambda msg: None):
    staff = {s.name: s for s in StaffProfile.objects.all()}
    for name, cats in CAPABILITIES.items():
        if name in staff:
            staff[name].services.add(*Service.objects.filter(category__name__in=cats, is_bookable=True))
    for name, s in staff.items():
        overrides = EXCEPTIONS.get(name, {})
        for weekday in range(6):
            window = overrides.get(weekday, (OPEN, CLOSE))
            if window is None:
                continue
            StaffSchedule.objects.update_or_create(staff=s, weekday=weekday,
                                                   defaults=dict(start_time=window[0], end_time=window[1]))
    kavya = staff.get("Kavya M.")
    if kavya and not kavya.leaves.exists():
        day = timezone.localdate() + dt.timedelta(days=9)
        StaffLeave.objects.create(staff=kavya, start=aware(day, dt.time.min), end=aware(day + dt.timedelta(days=1), dt.time.min),
                                  reason="Training day (demo)", is_approved=True)

    customer = User.objects.filter(username="demo_customer").first()
    if customer and not Booking.objects.filter(customer=customer).exists() and {"Dhanya Q.", "Priya S.", "Meenakshi R."} <= staff.keys():
        S = Booking.Status
        _make(customer, staff["Dhanya Q."], ["Signature Hydra Facial"], _find_day(staff["Dhanya Q."], -5, -1), dt.time(11, 0), S.COMPLETED)
        _make(customer, staff["Priya S."], ["Haircut and Styling"], _find_day(staff["Priya S."], 1), dt.time(15, 0), S.CONFIRMED)
        _make(customer, staff["Meenakshi R."], ["Bridal Makeup Trial"], _find_day(staff["Meenakshi R."], 3), dt.time(12, 0), S.PENDING)
    write("Scheduling and demo bookings ready.")
