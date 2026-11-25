
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from accounts.permissions import salon_admin_required


User = get_user_model()


@salon_admin_required
def customer_list(request):
    customers = (
        User.objects
        .filter(role=User.Role.CUSTOMER)
        .annotate(booking_count=Count("bookings"))
        .order_by("-date_joined")
    )

    search = request.GET.get("q", "").strip()
    account_status = request.GET.get("account_status", "").strip()

    if search:
        customers = customers.filter(
            Q(username__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone__icontains=search)
        )

    if account_status == "active":
        customers = customers.filter(is_active=True)
    elif account_status == "inactive":
        customers = customers.filter(is_active=False)

    paginator = Paginator(customers, 12)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "admin_panel/customers.html",
        {
            "page": page,
            "search": search,
            "account_status": account_status,
            "total_count": paginator.count,
        },
    )


@salon_admin_required
def customer_detail(request, customer_id):
    customer = get_object_or_404(
        User,
        pk=customer_id,
        role=User.Role.CUSTOMER,
    )

    bookings = (
        customer.bookings
        .select_related("staff")
        .prefetch_related("items")
        .order_by("-start")
    )

    return render(
        request,
        "admin_panel/customer_detail.html",
        {
            "customer": customer,
            "bookings": bookings,
            "total_bookings": bookings.count(),
        },
    )
