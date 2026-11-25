
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from bookings.models import Booking, BLOCKING_STATUSES
from accounts.permissions import salon_admin_required

from .admin_forms import (
    StaffProfileAdminForm,
    StaffScheduleAdminForm,
    StaffLeaveAdminForm,
)
from .models import StaffProfile, StaffSchedule, StaffLeave


# ==========================================
# STAFF DIRECTORY
# ==========================================

@salon_admin_required
def staff_list(request):
    staff_members = StaffProfile.objects.prefetch_related(
        "services"
    ).order_by("order", "name")

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if query:
        staff_members = staff_members.filter(
            Q(name__icontains=query)
            | Q(title__icontains=query)
            | Q(bio__icontains=query)
        )

    if status == "active":
        staff_members = staff_members.filter(
            is_active=True
        )
    elif status == "inactive":
        staff_members = staff_members.filter(
            is_active=False
        )

    paginator = Paginator(staff_members, 12)
    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "admin_panel/staff.html",
        {
            "staff_members": page_obj,
            "query": query,
            "status": status,
            "page_obj": page_obj,
            "total_count": paginator.count,
        },
    )


@salon_admin_required
def staff_create(request):
    form = StaffProfileAdminForm(
        request.POST or None,
        request.FILES or None,
    )

    if request.method == "POST" and form.is_valid():
        staff = form.save()

        messages.success(
            request,
            f"{staff.name}'s profile was created successfully.",
        )

        return redirect(
            "admin_panel:staff_detail",
            staff_id=staff.pk,
        )

    return render(
        request,
        "admin_panel/staff_form.html",
        {
            "form": form,
            "page_title": "Add Staff Member",
            "form_description": "Create a beautician profile and assign their services.",
            "submit_label": "Create staff profile",
        },
    )


@salon_admin_required
def staff_edit(request, staff_id):
    staff = get_object_or_404(
        StaffProfile,
        pk=staff_id,
    )

    form = StaffProfileAdminForm(
        request.POST or None,
        request.FILES or None,
        instance=staff,
    )

    if request.method == "POST" and form.is_valid():
        form.save()

        messages.success(
            request,
            f"{staff.name}'s profile was updated successfully.",
        )

        return redirect(
            "admin_panel:staff_detail",
            staff_id=staff.pk,
        )

    return render(
        request,
        "admin_panel/staff_form.html",
        {
            "form": form,
            "staff": staff,
            "page_title": "Edit Staff Profile",
            "form_description": "Update profile information, photograph and service assignments.",
            "submit_label": "Save changes",
        },
    )


@salon_admin_required
@require_POST
def staff_toggle_active(request, staff_id):
    staff = get_object_or_404(
        StaffProfile,
        pk=staff_id,
    )

    staff.is_active = not staff.is_active
    staff.save(update_fields=["is_active"])

    messages.success(
        request,
        f"{staff.name} is now {'active' if staff.is_active else 'inactive'}.",
    )

    return redirect("admin_panel:staff")


# ==========================================
# STAFF PROFILE DETAIL
# ==========================================

@salon_admin_required
def staff_detail(request, staff_id):
    staff = get_object_or_404(
        StaffProfile.objects.prefetch_related(
            "services",
            "schedules",
            "leaves",
        ),
        pk=staff_id,
    )

    schedules = staff.schedules.all().order_by("weekday")

    leaves = staff.leaves.all().order_by("-start")

    recent_bookings = (
        staff.bookings
        .select_related("customer")
        .prefetch_related("items")
        .order_by("-start")[:10]
    )

    return render(
        request,
        "admin_panel/staff_detail.html",
        {
            "staff": staff,
            "schedules": schedules,
            "leaves": leaves,
            "recent_bookings": recent_bookings,
            "total_bookings": staff.bookings.count(),
        },
    )



# ==========================================
# WEEKLY STAFF SCHEDULE MANAGEMENT
# ==========================================

@salon_admin_required
def schedule_create(request, staff_id):
    staff = get_object_or_404(
        StaffProfile,
        pk=staff_id,
    )

    form = StaffScheduleAdminForm(
        request.POST or None,
    )

    if request.method == "POST" and form.is_valid():
        weekday = form.cleaned_data["weekday"]

        duplicate = StaffSchedule.objects.filter(
            staff=staff,
            weekday=weekday,
        ).exists()

        if duplicate:
            form.add_error(
                "weekday",
                "A working schedule already exists for this day. "
                "Please edit the existing schedule instead.",
            )
        else:
            schedule = form.save(commit=False)
            schedule.staff = staff
            schedule.save()

            messages.success(
                request,
                f"{schedule.get_weekday_display()} schedule added for {staff.name}.",
            )

            return redirect(
                "admin_panel:staff_detail",
                staff_id=staff.pk,
            )

    return render(
        request,
        "admin_panel/schedule_form.html",
        {
            "form": form,
            "staff": staff,
            "page_title": "Add Working Schedule",
            "submit_label": "Add schedule",
        },
    )


@salon_admin_required
def schedule_edit(request, staff_id, schedule_id):
    staff = get_object_or_404(
        StaffProfile,
        pk=staff_id,
    )

    schedule = get_object_or_404(
        StaffSchedule,
        pk=schedule_id,
        staff=staff,
    )

    form = StaffScheduleAdminForm(
        request.POST or None,
        instance=schedule,
    )

    if request.method == "POST" and form.is_valid():
        weekday = form.cleaned_data["weekday"]

        duplicate = StaffSchedule.objects.filter(
            staff=staff,
            weekday=weekday,
        ).exclude(
            pk=schedule.pk,
        ).exists()

        if duplicate:
            form.add_error(
                "weekday",
                "Another working schedule already exists for this day.",
            )
        else:
            form.save()

            messages.success(
                request,
                f"{staff.name}'s working schedule was updated.",
            )

            return redirect(
                "admin_panel:staff_detail",
                staff_id=staff.pk,
            )

    return render(
        request,
        "admin_panel/schedule_form.html",
        {
            "form": form,
            "staff": staff,
            "schedule": schedule,
            "page_title": "Edit Working Schedule",
            "submit_label": "Save changes",
        },
    )


@salon_admin_required
@require_POST
def schedule_delete(request, staff_id, schedule_id):
    staff = get_object_or_404(
        StaffProfile,
        pk=staff_id,
    )

    schedule = get_object_or_404(
        StaffSchedule,
        pk=schedule_id,
        staff=staff,
    )

    weekday = schedule.get_weekday_display()
    schedule.delete()

    messages.success(
        request,
        f"{weekday} schedule removed for {staff.name}.",
    )

    return redirect(
        "admin_panel:staff_detail",
        staff_id=staff.pk,
    )


def has_staff_booking_conflict(staff, start, end):
    """
    Check whether a staff member has an existing blocking
    appointment overlapping the requested leave period.
    """
    return Booking.objects.filter(
        staff=staff,
        status__in=BLOCKING_STATUSES,
        start__lt=end,
        end__gt=start,
    ).exists()

# ==========================================
# STAFF LEAVE MANAGEMENT
# ==========================================


@salon_admin_required
def leave_create(request, staff_id):
    staff = get_object_or_404(
        StaffProfile,
        pk=staff_id,
    )

    form = StaffLeaveAdminForm(
        request.POST or None,
    )

    if request.method == "POST" and form.is_valid():
        start = form.cleaned_data["start"]
        end = form.cleaned_data["end"]
        is_approved = form.cleaned_data["is_approved"]

        if is_approved and has_staff_booking_conflict(staff, start, end):
            form.add_error(
                None,
                "This leave period overlaps existing appointments. "
                "Review the appointment schedule before approving leave.",
            )
        else:
            leave = form.save(commit=False)
            leave.staff = staff
            leave.save()

            messages.success(
                request,
                f"Leave record added for {staff.name}.",
            )

            return redirect(
                "admin_panel:staff_detail",
                staff_id=staff.pk,
            )

    return render(
        request,
        "admin_panel/leave_form.html",
        {
            "form": form,
            "staff": staff,
            "page_title": "Add Staff Leave",
            "submit_label": "Save leave",
        },
    )


@salon_admin_required
def leave_edit(request, staff_id, leave_id):
    staff = get_object_or_404(
        StaffProfile,
        pk=staff_id,
    )

    leave = get_object_or_404(
        StaffLeave,
        pk=leave_id,
        staff=staff,
    )

    form = StaffLeaveAdminForm(
        request.POST or None,
        instance=leave,
    )

    if request.method == "POST" and form.is_valid():
        start = form.cleaned_data["start"]
        end = form.cleaned_data["end"]
        is_approved = form.cleaned_data["is_approved"]

        if is_approved and has_staff_booking_conflict(staff, start, end):
            form.add_error(
                None,
                "This leave period overlaps existing appointments. "
                "Review the appointment schedule before approving leave.",
            )
        else:
            form.save()

            messages.success(
                request,
                f"Leave record updated for {staff.name}.",
            )

            return redirect(
                "admin_panel:staff_detail",
                staff_id=staff.pk,
            )

    return render(
        request,
        "admin_panel/leave_form.html",
        {
            "form": form,
            "staff": staff,
            "leave": leave,
            "page_title": "Edit Staff Leave",
            "submit_label": "Save changes",
        },
    )

@salon_admin_required
@require_POST
def leave_toggle_approval(request, staff_id, leave_id):
    staff = get_object_or_404(
        StaffProfile,
        pk=staff_id,
    )

    leave = get_object_or_404(
        StaffLeave,
        pk=leave_id,
        staff=staff,
    )

    # Check conflicts only when approving leave.
    if not leave.is_approved and has_staff_booking_conflict(
        staff,
        leave.start,
        leave.end,
    ):
        messages.error(
            request,
            "Cannot approve this leave because existing appointments "
            "overlap with the leave period.",
        )

        return redirect(
            "admin_panel:staff_detail",
            staff_id=staff.pk,
        )

    leave.is_approved = not leave.is_approved
    leave.save(update_fields=["is_approved"])

    messages.success(
        request,
        f"Leave is now {'approved' if leave.is_approved else 'not approved'}.",
    )

    return redirect(
        "admin_panel:staff_detail",
        staff_id=staff.pk,
    )


@salon_admin_required
@require_POST
def leave_delete(request, staff_id, leave_id):
    staff = get_object_or_404(
        StaffProfile,
        pk=staff_id,
    )

    leave = get_object_or_404(
        StaffLeave,
        pk=leave_id,
        staff=staff,
    )

    leave.delete()

    messages.success(
        request,
        f"Leave record removed for {staff.name}.",
    )

    return redirect(
        "admin_panel:staff_detail",
        staff_id=staff.pk,
    )
