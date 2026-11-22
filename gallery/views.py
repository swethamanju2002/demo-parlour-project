from django.shortcuts import render

from .models import GalleryCategory, GalleryItem


def gallery_list(request):
    return render(request, "public/gallery.html", {
        "categories": GalleryCategory.objects.all(),
        "items": GalleryItem.objects.filter(is_active=True).select_related("category"),
    })
