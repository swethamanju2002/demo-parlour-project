from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    public_id = models.CharField("Booking ID", max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    staff = models.ForeignKey("staff.StaffProfile", on_delete=models.PROTECT, related_name="bookings")
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    any_staff = models.BooleanField(default=False, help_text="The customer let the salon choose the beautician.")
    # Snapshots taken when the booking is made; later price/duration edits never change them.
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_minutes = models.PositiveSmallIntegerField()
    notes = models.TextField(blank=True, help_text="Customer notes.")
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    reschedule_requested_at = models.DateTimeField(null=True, blank=True)
    reschedule_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-start"]
        constraints = [models.CheckConstraint(condition=Q(end__gt=F("start")), name="booking_end_after_start")]
        indexes = [models.Index(fields=["staff", "start"]), models.Index(fields=["customer", "start"])]

    def __str__(self):
        return self.public_id


# Statuses that occupy the beautician's time. Rejected and cancelled bookings free the slot.
BLOCKING_STATUSES = (Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.COMPLETED)


class BookingItem(models.Model):
    """One service within a booking, with its name, price and duration frozen at booking time."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey("services.Service", on_delete=models.PROTECT, related_name="booking_items")
    service_name = models.CharField(max_length=120)
    unit_price = models.DecimalField(max_digits=9, decimal_places=2)
    duration_minutes = models.PositiveSmallIntegerField()
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.booking_id} · {self.service_name}"
