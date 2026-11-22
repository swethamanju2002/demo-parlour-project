from django.contrib import admin

from .models import GalleryCategory, GalleryItem

admin.site.register(GalleryCategory, type("A", (admin.ModelAdmin,), {"prepopulated_fields": {"slug": ("name",)}}))
admin.site.register(GalleryItem, type("B", (admin.ModelAdmin,), {"list_display": ("title", "category", "is_featured", "is_active")}))
