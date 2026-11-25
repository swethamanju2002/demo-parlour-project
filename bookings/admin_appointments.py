
from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import salon_admin_required
from .models import Booking


@salon_admin_required
def appointment_list(request):
    bookings = Booking.objects.select_related(
        "customer", "staff"
    ).prefetch_related("items")

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    date_value = request.GET.get("date", "").strip()

    if search:
        bookings = bookings.filter(
            Q(public_id__icontains=search)
            | Q(customer__first_name__icontains=search)
            | Q(customer__last_name__icontains=search)
            | Q(customer__username__icontains=search)
            | Q(customer__email__icontains=search)
            | Q(customer__phone__icontains=search)
            | Q(staff__name__icontains=search)
        )

    if status in Booking.Status.values:
        bookings = bookings.filter(status=status)

    if date_value:
        try:
            selected_date = date.fromisoformat(date_value)
            bookings = bookings.filter(start__date=selected_date)
        except ValueError:
            messages.warning(request, "Please choose a valid date.")

    paginator = Paginator(bookings, 12)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "admin_panel/appointments.html", {
        "page": page,
        "search": search,
        "selected_status": status,
        "selected_date": date_value,
        "status_choices": Booking.Status.choices,
        "total_count": paginator.count,
    })


@salon_admin_required
def appointment_detail(request, public_id):
    booking = get_object_or_404(
        Booking.objects.select_related(
            "customer", "staff"
        ).prefetch_related("items"),
        public_id=public_id,
    )

    return render(request, "admin_panel/appointment_detail.html", {
        "booking": booking,
        "items": booking.items.all(),
    })


@salon_admin_required
@require_POST
def update_appointment(request, public_id):
    booking = get_object_or_404(
        Booking,
        public_id=public_id,
    )

    new_status = request.POST.get("status", "").strip()
    admin_note = request.POST.get("admin_note", "").strip()

    allowed_transitions = {
        Booking.Status.PENDING: {
            Booking.Status.CONFIRMED,
            Booking.Status.REJECTED,
            Booking.Status.CANCELLED,
        },
        Booking.Status.CONFIRMED: {
            Booking.Status.COMPLETED,
            Booking.Status.CANCELLED,
        },
    }

    if new_status != booking.status:
        allowed = allowed_transitions.get(booking.status, set())

        if new_status not in allowed:
            messages.error(
                request,
                "This appointment status change is not permitted.",
            )
            return redirect(
                "admin_panel:appointment_detail",
                public_id=public_id,
            )

        booking.status = new_status

    booking.admin_note = admin_note[:2000]

    update_fields = ["admin_note", "updated_at", "status"]

    booking.save(update_fields=update_fields)

    messages.success(request, "Appointment details updated successfully.")

    return redirect(
        "admin_panel:appointment_detail",
        public_id=public_id,
    )
