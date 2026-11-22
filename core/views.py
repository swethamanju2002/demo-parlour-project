from django.contrib import messages
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from enquiries.forms import EnquiryForm
from gallery.models import GalleryItem
from offers.models import Offer
from services.models import Service, ServiceCategory
from staff.models import StaffProfile

from .models import FAQ, BusinessHour, Testimonial


def _hours():
    return list(BusinessHour.objects.all()), timezone.localdate().weekday()


def home(request):
    hours, today = _hours()
    staff = StaffProfile.objects.filter(is_active=True, is_featured=True)
    ctx = {
        "categories": ServiceCategory.objects.filter(is_active=True),
        "featured": Service.objects.active().filter(is_featured=True).select_related("category")[:5],
        "popular": Service.objects.active().filter(is_popular=True).select_related("category")[:6],
        "ba_item": GalleryItem.objects.filter(is_active=True).exclude(before_image="").first(),
        "gallery": GalleryItem.objects.filter(is_active=True, is_featured=True)[:6],
        "offers": Offer.objects.current()[:3],
        "testimonials": Testimonial.objects.filter(is_active=True),
        "staff": staff[:4],
        "stats": {
            "services": Service.objects.active().count(),
            "specialists": staff.count(),
            "experience": staff.aggregate(t=Sum("years_experience"))["t"] or 0,
            "categories": ServiceCategory.objects.filter(is_active=True).count(),
        },
        "hours": hours, "today": today,
    }
    return render(request, "public/home.html", ctx)


def about(request):
    return render(request, "public/about.html", {
        "staff": StaffProfile.objects.filter(is_active=True),
        "gallery": GalleryItem.objects.filter(is_active=True)[:4],
    })


def contact(request):
    form = EnquiryForm(request.POST or None)
    wants_json = request.headers.get("x-requested-with") == "fetch"
    if request.method == "POST":
        if form.is_valid():
            form.save()
            if wants_json:
                return JsonResponse({"ok": True, "message": "Thanks, we have your message and will call you soon."})
            messages.success(request, "Thanks, we have your message and will call you soon.")
            return redirect("core:contact")
        if wants_json:
            return JsonResponse({"ok": False, "errors": {k: v[0] for k, v in form.errors.items()}}, status=400)
    hours, today = _hours()
    return render(request, "public/contact.html", {
        "form": form, "hours": hours, "today": today, "faqs": FAQ.objects.filter(is_active=True),
    })
