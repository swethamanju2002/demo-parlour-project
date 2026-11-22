from django.shortcuts import render

from .models import Service, ServiceCategory


def service_list(request):
    cats = ServiceCategory.objects.filter(is_active=True).prefetch_related("services")
    groups = []
    for c in cats:
        items = [s for s in c.services.all() if s.is_active]
        if items:
            groups.append((c, items))
    return render(request, "public/services.html", {"groups": groups})
