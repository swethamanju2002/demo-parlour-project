from django.contrib import admin

from .models import Enquiry

admin.site.register(Enquiry, type("E", (admin.ModelAdmin,), {"list_display": ("name", "phone", "status", "created_at"), "list_filter": ("status",)}))
