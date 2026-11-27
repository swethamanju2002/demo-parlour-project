from django.db.models import Count, Sum, F
import csv
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.permissions import salon_admin_required
from bookings.models import Booking, BookingItem
from billing.models import Invoice, Payment
from expenses.models import Expense
from inventory.models import Product
from academy.models import Batch, Enrollment

ZERO = Decimal("0.00")


def get_date_range(request):
    """Resolve preset or custom date filters. Defaults to the current month."""
    today = timezone.localdate()
    period = request.GET.get("period", "month")

    if period == "today":
        start_date = end_date = today
    elif period == "last_month":
        first_this_month = today.replace(day=1)
        end_date = first_this_month - timedelta(days=1)
        start_date = end_date.replace(day=1)
    elif period == "year":
        start_date = today.replace(month=1, day=1)
        end_date = today
    elif period == "custom":
        try:
            start_date = date.fromisoformat(request.GET.get("start", ""))
            end_date = date.fromisoformat(request.GET.get("end", ""))
            if start_date > end_date:
                start_date, end_date = end_date, start_date
        except (ValueError, TypeError):
            start_date = today.replace(day=1)
            end_date = today
    else:
        start_date = today.replace(day=1)
        end_date = today
        period = "month"

    return start_date, end_date, period


def date_bounds(start_date, end_date):
    """Build timezone-aware inclusive date boundaries for DateTimeFields."""
    start = timezone.make_aware(
        datetime.combine(start_date, time.min),
        timezone.get_current_timezone(),
    )
    end = timezone.make_aware(
        datetime.combine(end_date + timedelta(days=1), time.min),
        timezone.get_current_timezone(),
    )
    return start, end


@login_required
@salon_admin_required
def dashboard(request):
    start_date, end_date, period = get_date_range(request)
    start_dt, end_dt = date_bounds(start_date, end_date)

    bookings = Booking.objects.filter(
        start__gte=start_dt,
        start__lt=end_dt,
    )

    booking_counts = {
        row["status"]: row["total"]
        for row in bookings.values("status").annotate(total=Count("id"))
    }

    total_bookings = bookings.count()
    completed_bookings = booking_counts.get(Booking.Status.COMPLETED, 0)
    pending_bookings = booking_counts.get(Booking.Status.PENDING, 0)
    confirmed_bookings = booking_counts.get(Booking.Status.CONFIRMED, 0)
    cancelled_bookings = booking_counts.get(Booking.Status.CANCELLED, 0)
    rejected_bookings = booking_counts.get(Booking.Status.REJECTED, 0)

    # Collected revenue is based on completed payment transactions only.
    payments = Payment.objects.filter(
        status=Payment.Status.COMPLETED,
        paid_at__gte=start_dt,
        paid_at__lt=end_dt,
        invoice__status=Invoice.Status.ISSUED,
    )

    collected_revenue = payments.aggregate(
        total=Sum("amount")
    )["total"] or ZERO

    # Expense records use DateField, so filter using inclusive dates.
    expenses = Expense.objects.filter(
        expense_date__gte=start_date,
        expense_date__lte=end_date,
    )

    paid_expenses = expenses.filter(
        payment_status="paid"
    ).aggregate(total=Sum("amount"))["total"] or ZERO

    pending_expenses = expenses.filter(
        payment_status="pending"
    ).aggregate(total=Sum("amount"))["total"] or ZERO

    total_expenses = expenses.aggregate(
        total=Sum("amount")
    )["total"] or ZERO

    operating_estimate = collected_revenue - paid_expenses

    # Outstanding balances are calculated per issued invoice, using
    # completed payments only. Refunded/failed/pending payments are excluded.
    outstanding_invoices = Invoice.objects.filter(
        status=Invoice.Status.ISSUED,
    ).prefetch_related("payments")

    outstanding_balance = ZERO
    outstanding_invoice_count = 0

    for invoice in outstanding_invoices:
        paid = sum(
            (
                payment.amount
                for payment in invoice.payments.all()
                if payment.status == Payment.Status.COMPLETED
            ),
            ZERO,
        )
        balance = max(invoice.total_amount - paid, ZERO)
        if balance > ZERO:
            outstanding_balance += balance
            outstanding_invoice_count += 1

    # Customer repeat-booking analysis for the selected period.
    customer_booking_counts = list(
        bookings.values("customer_id")
        .annotate(total=Count("id"))
    )
    unique_customers = len(customer_booking_counts)
    repeat_customers = sum(
        1 for row in customer_booking_counts if row["total"] > 1
    )

    # Top services use BookingItem snapshots, not mutable current prices/names.
    top_services = (
        BookingItem.objects.filter(
            booking__start__gte=start_dt,
            booking__start__lt=end_dt,
        )
        .values("service_name")
        .annotate(bookings_count=Count("booking_id", distinct=True))
        .order_by("-bookings_count", "service_name")[:8]
    )

    # Academy overview: counts reflect current state, not historical period.
    academy_summary = {
        "active_batches": Batch.objects.filter(
            status="ongoing"
        ).count(),
        "active_enrollments": Enrollment.objects.filter(
            status="active"
        ).count(),
        "total_enrollments": Enrollment.objects.count(),
    }

    # Inventory overview: current stock position.
    inventory_summary = {
        "products": Product.objects.count(),
        "low_stock": Product.objects.filter(
            quantity_on_hand__lte=F("reorder_level"),
            is_active=True,
        ).count(),
    }


    # Revenue by calendar month within the selected date range.
    monthly_revenue_rows = (
        payments.values("paid_at__year", "paid_at__month")
        .annotate(total=Sum("amount"))
        .order_by("paid_at__year", "paid_at__month")
    )

    monthly_revenue = [
        {
            "label": f'{row["paid_at__month"]:02d}/{row["paid_at__year"]}',
            "amount": row["total"] or ZERO,
        }
        for row in monthly_revenue_rows
    ]

    status_rows = [
        {"label": label, "count": booking_counts.get(value, 0)}
        for value, label in Booking.Status.choices
    ]

    context = {
        "start_date": start_date,
        "end_date": end_date,
        "period": period,
        "total_bookings": total_bookings,
        "completed_bookings": completed_bookings,
        "pending_bookings": pending_bookings,
        "confirmed_bookings": confirmed_bookings,
        "cancelled_bookings": cancelled_bookings,
        "rejected_bookings": rejected_bookings,
        "booking_counts": booking_counts,
        "status_rows": status_rows,
        "collected_revenue": collected_revenue,
        "paid_expenses": paid_expenses,
        "pending_expenses": pending_expenses,
        "total_expenses": total_expenses,
        "operating_estimate": operating_estimate,
        "outstanding_balance": outstanding_balance,
        "outstanding_invoice_count": outstanding_invoice_count,
        "unique_customers": unique_customers,
        "repeat_customers": repeat_customers,
        "top_services": top_services,
        "academy_summary": academy_summary,
        "inventory_summary": inventory_summary,
        "monthly_revenue": monthly_revenue,
    }

    return render(
        request,
        "admin_panel/analytics/dashboard.html",
        context,
    )


@login_required
@salon_admin_required
def export_report(request):
    """Export a date-filtered summary as CSV."""
    start_date, end_date, period = get_date_range(request)
    start_dt, end_dt = date_bounds(start_date, end_date)

    bookings = Booking.objects.filter(
        start__gte=start_dt,
        start__lt=end_dt,
    )

    payments = Payment.objects.filter(
        status=Payment.Status.COMPLETED,
        paid_at__gte=start_dt,
        paid_at__lt=end_dt,
        invoice__status=Invoice.Status.ISSUED,
    )

    expenses = Expense.objects.filter(
        expense_date__gte=start_date,
        expense_date__lte=end_date,
    )

    revenue = payments.aggregate(total=Sum("amount"))["total"] or ZERO
    paid_expense = expenses.filter(
        payment_status="paid"
    ).aggregate(total=Sum("amount"))["total"] or ZERO
    pending_expense = expenses.filter(
        payment_status="pending"
    ).aggregate(total=Sum("amount"))["total"] or ZERO

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="dq_aesthetic_report_{start_date}_{end_date}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow(["DQ Aesthetic - Business Analytics Report"])
    writer.writerow(["Period", start_date, "to", end_date])
    writer.writerow([])
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Total bookings", bookings.count()])
    writer.writerow([
        "Completed bookings",
        bookings.filter(status=Booking.Status.COMPLETED).count(),
    ])
    writer.writerow([
        "Pending bookings",
        bookings.filter(status=Booking.Status.PENDING).count(),
    ])
    writer.writerow([
        "Confirmed bookings",
        bookings.filter(status=Booking.Status.CONFIRMED).count(),
    ])
    writer.writerow([
        "Cancelled bookings",
        bookings.filter(status=Booking.Status.CANCELLED).count(),
    ])
    writer.writerow(["Collected revenue", revenue])
    writer.writerow(["Paid expenses", paid_expense])
    writer.writerow(["Pending expenses", pending_expense])
    writer.writerow(["Operating estimate", revenue - paid_expense])

    return response
