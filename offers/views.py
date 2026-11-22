from django.shortcuts import render

from .models import Offer


def offer_list(request):
    return render(request, "public/offers.html", {"offers": Offer.objects.current().prefetch_related("services")})
