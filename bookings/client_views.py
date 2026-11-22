"""Customer portal pages. Every query is scoped to request.user; other customers' bookings are invisible."""
import itertools

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import customer_required
from offers.models import Offer
from services.models import Service

from . import availability as av
from . import workflow as wf
from .api import booking_payload, error_response
from .availability import BookingError
from .models import Booking

CANCELLABLE = wf.CANCELLABLE


def _mine(request):
    return Booking.objects.filter(customer=request.user).select_related("staff").prefetch_related("items")


def _decorate(bookings):
    for b in bookings:
        b.can_change = wf.can_change(b)
        b.change_deadline = wf.change_deadline(b)
    return bookings


@customer_required
def dashboard(request):
    sid = request.GET.get("service", "")
    if sid.isdigit():  # existing "Book now" links point here with ?service=<pk>; hand them to the wizard
        return redirect(f"{reverse('client:book')}?service={sid}")
    now = av._now()
    mine = _mine(request)
    upcoming = _decorate(list(mine.filter(status__in=CANCELLABLE, end__gt=now).order_by("start")))
    past = _decorate(list(mine.exclude(pk__in=[b.pk for b in upcoming]).order_by("-start")[:5]))
    timeline = [(day, list(items)) for day, items in itertools.groupby(upcoming, key=lambda b: timezone.localtime(b.start).date())]
    return render(request, "client/dashboard.html", {
        "next_booking": upcoming[0] if upcoming else None,
        "upcoming": upcoming, "timeline": timeline,
        "pending": [b for b in upcoming if b.status == Booking.Status.PENDING],
        "confirmed": [b for b in upcoming if b.status == Booking.Status.CONFIRMED],
        "completed": [b for b in past if b.status == Booking.Status.COMPLETED],
        "history": past,
        "offers": Offer.objects.current().prefetch_related("services")[:3],
        "invoices": [],   # Phase 5 (billing) fills this
        "totals": {"all": mine.count(), "completed": mine.filter(status=Booking.Status.COMPLETED).count()},
    })


@customer_required
def book(request):
    """Wizard shell. Data and actions come from the JSON endpoints in bookings/api.py."""
    raw = request.GET.get("service", "")
    preselect = int(raw) if raw.isdigit() and Service.objects.bookable().filter(pk=int(raw)).exists() else None
    return render(request, "client/book.html", {"preselect_service": preselect, "max_services": av.policy("BOOKING_MAX_SERVICES", 8)})


@customer_required
def bookings(request):
    now = av._now()
    tab = request.GET.get("tab", "upcoming")
    qs = _mine(request)
    if tab == "upcoming":
        qs = qs.filter(status__in=CANCELLABLE, end__gt=now).order_by("start")
    elif tab == "past":
        qs = qs.exclude(status__in=CANCELLABLE, end__gt=now)
    else:
        tab = "all"
    page = Paginator(qs, 10).get_page(request.GET.get("page"))
    _decorate(page.object_list)
    return render(request, "client/bookings.html", {"page": page, "tab": tab})


@customer_required
def booking_detail(request, public_id):
    try:
        b = wf.get_customer_booking(public_id, request.user)
    except BookingError:
        raise Http404
    _decorate([b])
    return render(request, "client/booking_detail.html", {"booking": b, "items": b.items.all()})


def _change(request, public_id, action, done_message, **kwargs):
    """Cancel / reschedule share one endpoint for both fetch (JSON) and plain form posts."""
    wants_json = request.headers.get("x-requested-with") == "fetch"
    try:
        b = action(public_id, request.user, **kwargs)
    except BookingError as e:
        if wants_json:
            return error_response(e)
        messages.error(request, e.message)
        return redirect("client:bookings" if e.code == "not_found" else "client:booking_detail", *([] if e.code == "not_found" else [public_id]))
    if wants_json:
        return JsonResponse({"ok": True, "message": done_message, "booking": booking_payload(b)})
    messages.success(request, done_message)
    return redirect("client:booking_detail", public_id)


@customer_required
@require_POST
def booking_cancel(request, public_id):
    return _change(request, public_id, wf.cancel_booking, "Your booking has been cancelled.")


@customer_required
@require_POST
def booking_reschedule(request, public_id):
    return _change(request, public_id, wf.request_reschedule,
                   "Thanks, we have your reschedule request and will be in touch.", note=request.POST.get("note", ""))


@customer_required
def offers(request):
    return render(request, "client/offers.html", {"offers": Offer.objects.current().prefetch_related("services")})


@customer_required
def billing(request):
    return render(request, "client/billing.html", {"invoices": []})   # Phase 5 fills this
