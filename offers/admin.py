from django.contrib import admin

from .models import Offer


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("title", "discount_type", "discount_value", "valid_from", "valid_to", "is_active")
    filter_horizontal = ("services",)
