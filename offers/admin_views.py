
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from accounts.permissions import salon_admin_required

from .models import Offer
from .admin_forms import OfferAdminForm


# ==========================================
# OFFER LIST / SEARCH / FILTER
# ==========================================

@salon_admin_required
def offer_list(request):
    offers = Offer.objects.prefetch_related(
        "services"
    ).order_by("-valid_from", "title")

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    offer_type = request.GET.get("type", "").strip()

    today = timezone.localdate()

    if query:
        offers = offers.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(description__icontains=query)
            | Q(coupon_code__icontains=query)
        ).distinct()

    if status == "active":
        offers = offers.filter(is_active=True)

    elif status == "inactive":
        offers = offers.filter(is_active=False)

    elif status == "current":
        offers = offers.filter(
            is_active=True,
            valid_from__lte=today,
            valid_to__gte=today,
        )

    elif status == "upcoming":
        offers = offers.filter(
            is_active=True,
            valid_from__gt=today,
        )

    elif status == "expired":
        offers = offers.filter(
            valid_to__lt=today,
        )

    if offer_type == "package":
        offers = offers.filter(is_package=True)

    elif offer_type == "regular":
        offers = offers.filter(is_package=False)

    paginator = Paginator(offers, 12)

    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "admin_panel/offers.html",
        {
            "offers": page_obj,
            "page_obj": page_obj,
            "query": query,
            "status": status,
            "offer_type": offer_type,
            "total_count": paginator.count,
            "today": today,
        },
    )


# ==========================================
# OFFER CREATE
# ==========================================

@salon_admin_required
def offer_create(request):
    form = OfferAdminForm(
        request.POST or None,
        request.FILES or None,
    )

    if request.method == "POST" and form.is_valid():
        offer = form.save()

        messages.success(
            request,
            f"'{offer.title}' was created successfully.",
        )

        return redirect(
            "admin_panel:offer_detail",
            offer_id=offer.pk,
        )

    return render(
        request,
        "admin_panel/offer_form.html",
        {
            "form": form,
            "page_title": "Create New Offer",
            "form_description": (
                "Create a promotional offer or special salon package."
            ),
            "submit_label": "Create offer",
        },
    )


# ==========================================
# OFFER DETAIL
# ==========================================

@salon_admin_required
def offer_detail(request, offer_id):
    offer = get_object_or_404(
        Offer.objects.prefetch_related("services"),
        pk=offer_id,
    )

    today = timezone.localdate()

    if not offer.is_active:
        offer_status = "Inactive"

    elif offer.valid_to < today:
        offer_status = "Expired"

    elif offer.valid_from > today:
        offer_status = "Upcoming"

    else:
        offer_status = "Current"

    return render(
        request,
        "admin_panel/offer_detail.html",
        {
            "offer": offer,
            "offer_status": offer_status,
            "today": today,
        },
    )


# ==========================================
# OFFER EDIT
# ==========================================

@salon_admin_required
def offer_edit(request, offer_id):
    offer = get_object_or_404(
        Offer,
        pk=offer_id,
    )

    form = OfferAdminForm(
        request.POST or None,
        request.FILES or None,
        instance=offer,
    )

    if request.method == "POST" and form.is_valid():
        updated_offer = form.save()

        messages.success(
            request,
            f"'{updated_offer.title}' was updated successfully.",
        )

        return redirect(
            "admin_panel:offer_detail",
            offer_id=updated_offer.pk,
        )

    return render(
        request,
        "admin_panel/offer_form.html",
        {
            "form": form,
            "offer": offer,
            "page_title": "Edit Offer",
            "form_description": (
                "Update the promotional details, discount and validity."
            ),
            "submit_label": "Save changes",
        },
    )


# ==========================================
# OFFER ACTIVE / INACTIVE
# ==========================================

@salon_admin_required
@require_POST
def offer_toggle_active(request, offer_id):
    offer = get_object_or_404(
        Offer,
        pk=offer_id,
    )

    offer.is_active = not offer.is_active

    offer.save(
        update_fields=["is_active"]
    )

    messages.success(
        request,
        f"'{offer.title}' is now "
        f"{'active' if offer.is_active else 'inactive'}.",
    )

    return redirect(
        "admin_panel:offer_detail",
        offer_id=offer.pk,
    )
