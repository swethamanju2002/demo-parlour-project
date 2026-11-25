from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone
from bookings.models import Booking, BookingItem
from accounts.permissions import salon_admin_required
from accounts.models import User
from bookings.models import Booking
from enquiries.models import Enquiry
from services.models import Service
from staff.models import StaffProfile


@login_required
@salon_admin_required
def dashboard(request):
    now = timezone.now()
    today = timezone.localdate()

    active_statuses = [
        Booking.Status.PENDING,
        Booking.Status.CONFIRMED,
    ]

    today_bookings = Booking.objects.filter(
        start__date=today
    ).exclude(
        status__in=[
            Booking.Status.CANCELLED,
            Booking.Status.REJECTED,
        ]
    ).count()

    upcoming_bookings = Booking.objects.filter(
        start__gte=now,
        status__in=active_statuses,
    ).select_related(
        "customer", "staff"
    ).prefetch_related(
        "items"
    ).order_by("start")[:6]

    status_counts = {
        item["status"]: item["total"]
        for item in Booking.objects.values("status").annotate(
            total=Count("id")
        )
    }
    status_rows = [
    {
        "label": label,
        "count": status_counts.get(status, 0),
    }
    for status, label in Booking.Status.choices
]
    stats = {
        "customers": User.objects.filter(
            role=User.Role.CUSTOMER,
            is_active=True,
        ).count(),

        "services": Service.objects.filter(
            is_active=True,
            category__is_active=True,
        ).count(),

        "beauticians": StaffProfile.objects.filter(
            is_active=True,
        ).count(),

        "today_bookings": today_bookings,

        "pending_bookings": status_counts.get(
            Booking.Status.PENDING, 0
        ),

        "new_enquiries": Enquiry.objects.filter(
            status=Enquiry.Status.NEW
        ).count(),
    }

    recent_enquiries = Enquiry.objects.order_by(
        "-created_at"
    )[:5]

    context = {
        "stats": stats,
        "status_counts": status_counts,
        "status_rows": status_rows,
        "upcoming_bookings": upcoming_bookings,
        "recent_enquiries": recent_enquiries,
        "today": today,
        
    }
    
    return render(
        request,
        "admin_panel/dashboard.html",
        context,
    )