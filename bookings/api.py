"""JSON endpoints behind the booking wizard (all under /client/api/).

Read endpoints are GET; the one write endpoint (`book`) is POST with a JSON body and needs the CSRF
header. Every response is {"ok": true, ...} or {"ok": false, "error": <customer-safe text>, "code": <id>}.
Nothing the browser sends about price, duration, status or customer is ever used.
"""
from __future__ import annotations

import datetime as dt
import json
from functools import wraps

from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from services.models import Service, ServiceCategory

from . import availability as av
from . import workflow as wf
from .availability import BookingError

HTTP_STATUS = {
    "not_found": 404, "slot_unavailable": 409, "customer_overlap": 409, "too_many_active": 409,
    "too_late": 409, "not_changeable": 409, "already_requested": 409,
}


def error_response(e: BookingError) -> JsonResponse:
    return JsonResponse({"ok": False, "error": e.message, "code": e.code}, status=HTTP_STATUS.get(e.code, 400))


def customer_api(view):
    """JSON-friendly access control: 401/403 as JSON (not a login redirect), BookingError as 4xx JSON."""
    @wraps(view)
    def wrapper(request, *a, **kw):
        u = request.user
        if not u.is_authenticated:
            return JsonResponse({"ok": False, "error": "Please sign in to continue.", "code": "auth_required"}, status=401)
        if not u.is_active or u.role != "customer":
            return JsonResponse({"ok": False, "error": "Online booking is for customer accounts.", "code": "forbidden"}, status=403)
        try:
            return view(request, *a, **kw)
        except BookingError as e:
            return error_response(e)
    return wrapper


# ── parsing ───────────────────────────────────────────────────────────────────

def _service_ids(request) -> list[str]:
    return [x for x in request.GET.get("services", "").split(",") if x.strip()]


def _staff_param(raw):
    return None if raw in (None, "", "any") else raw


def _date(raw) -> dt.date:
    try:
        return dt.date.fromisoformat(raw or "")
    except ValueError:
        raise BookingError("Choose a valid date.", "bad_date")


def _datetime(raw) -> dt.datetime:
    if not isinstance(raw, str):
        raise BookingError("Choose a valid appointment time.", "bad_time")
    try:
        return dt.datetime.fromisoformat(raw)
    except ValueError:
        raise BookingError("Choose a valid appointment time.", "bad_time")


def _json_body(request) -> dict:
    if request.content_type != "application/json":
        raise BookingError("Unsupported request.", "bad_request")
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        raise BookingError("Malformed request.", "bad_request")
    if not isinstance(data, dict):
        raise BookingError("Malformed request.", "bad_request")
    return data


# ── serialisation ─────────────────────────────────────────────────────────────

def clock_label(value: dt.datetime) -> str:
    t = timezone.localtime(value)
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _service(s: Service) -> dict:
    return {"id": s.pk, "name": s.name, "description": s.description, "price": str(s.price),
            "duration_minutes": s.duration_minutes, "duration_label": s.duration_label,
            "image": s.image.url if s.image else "", "category": s.category_id}


def _staff(p) -> dict:
    return {"id": p.pk, "name": p.name, "title": p.title, "years_experience": p.years_experience,
            "photo": p.photo.url if p.photo else ""}


def booking_payload(b) -> dict:
    return {
        "public_id": b.public_id, "status": b.status, "status_label": b.get_status_display(),
        "start": timezone.localtime(b.start).isoformat(), "end": timezone.localtime(b.end).isoformat(),
        "time_label": clock_label(b.start), "staff": {"id": b.staff_id, "name": b.staff.name, "title": b.staff.title},
        "any_staff": b.any_staff, "total_price": str(b.total_price), "total_minutes": b.total_minutes,
        "items": [{"name": i.service_name, "price": str(i.unit_price), "duration_minutes": i.duration_minutes} for i in b.items.all()],
        "can_change": wf.can_change(b), "change_deadline": timezone.localtime(wf.change_deadline(b)).isoformat(),
        "reschedule_requested": bool(b.reschedule_requested_at),
        "url": reverse("client:booking_detail", args=[b.public_id]),
    }


# ── endpoints ─────────────────────────────────────────────────────────────────

@require_GET
@customer_api
def services(request):
    cats = []
    for c in ServiceCategory.objects.filter(is_active=True):
        items = [s for s in Service.objects.bookable().filter(category=c)]
        if items:
            cats.append({"id": c.pk, "name": c.name, "slug": c.slug, "tagline": c.tagline, "description": c.description,
                         "services": [_service(s) for s in items]})
    return JsonResponse({"ok": True, "categories": cats, "max_services": av.policy("BOOKING_MAX_SERVICES", 8)})


@require_GET
@customer_api
def dates(request):
    svcs = av.resolve_services(_service_ids(request))
    found = av.bookable_dates(svcs, staff=_staff_param(request.GET.get("staff")))
    today = av.local_today()
    return JsonResponse({"ok": True, "dates": [d.isoformat() for d in found], "total_minutes": av.total_minutes(svcs),
                         "window": {"first": today.isoformat(), "last": (today + dt.timedelta(days=av.policy("BOOKING_ADVANCE_DAYS", 60))).isoformat()}})


@require_GET
@customer_api
def slots(request):
    svcs = av.resolve_services(_service_ids(request))
    day = _date(request.GET.get("date"))
    found = av.slots_for_date(svcs, day, staff=_staff_param(request.GET.get("staff")), include_unavailable=True)
    return JsonResponse({"ok": True, "date": day.isoformat(), "total_minutes": av.total_minutes(svcs), "slots": [
        {"start": timezone.localtime(s.start).isoformat(), "time": timezone.localtime(s.start).strftime("%H:%M"),
         "label": clock_label(s.start), "available": s.available, "staff_ids": s.staff_ids} for s in found]})


@require_GET
@customer_api
def staff(request):
    """Beauticians who can do every selected service; with `start`, also whether each is free then."""
    svcs = av.resolve_services(_service_ids(request))
    pool = av.eligible_staff(svcs)
    if not pool:
        raise BookingError("No beautician is available for this combination of services. Try booking them separately.", "no_staff")
    free_ids = None
    if request.GET.get("start"):
        start = _datetime(request.GET["start"])
        start = timezone.make_aware(start) if timezone.is_naive(start) else start
        match = [s for s in av.slots_for_date(svcs, timezone.localtime(start).date()) if s.start == start]
        free_ids = set(match[0].staff_ids) if match else set()
    return JsonResponse({"ok": True, "any_available": free_ids is None or bool(free_ids), "staff": [
        {**_staff(p), "available": True if free_ids is None else p.pk in free_ids} for p in pool]})


@require_GET
@customer_api
def summary(request):
    """What the booking would be, computed from the database. Also confirms the slot is still free."""
    svcs = av.resolve_services(_service_ids(request))
    staff_param = _staff_param(request.GET.get("staff"))
    pool = av.candidates(svcs, staff_param)
    out = {"ok": True, "services": [{"id": s.pk, "name": s.name, "price": str(s.price), "duration_minutes": s.duration_minutes} for s in svcs],
           "total_price": str(sum(s.price for s in svcs)), "total_minutes": av.total_minutes(svcs),
           "staff": _staff(pool[0]) if staff_param is not None else None, "assignment": "specific" if staff_param is not None else "auto"}
    if request.GET.get("start"):
        start = _datetime(request.GET["start"])
        start = timezone.make_aware(start) if timezone.is_naive(start) else start
        match = [s for s in av.slots_for_date(svcs, timezone.localtime(start).date(), staff=staff_param) if s.start == start]
        if not match:
            raise BookingError("Sorry, that time is no longer available. Please pick another slot.", "slot_unavailable")
        out.update(start=timezone.localtime(start).isoformat(), end=timezone.localtime(match[0].end).isoformat(), time_label=clock_label(start))
    return JsonResponse(out)


@require_POST
@customer_api
def book(request):
    data = _json_body(request)
    services_ = data.get("services")
    if not isinstance(services_, list):
        raise BookingError("Choose at least one service.", "no_service")
    booking = wf.create_booking(
        customer=request.user, service_ids=services_, start=_datetime(data.get("start")),
        staff_id=_staff_param(data.get("staff")), notes=data.get("notes") if isinstance(data.get("notes"), str) else "",
    )
    return JsonResponse({"ok": True, "message": "Your booking request is in. We will confirm it shortly.", "booking": booking_payload(booking)}, status=201)
