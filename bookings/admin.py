from django.contrib import admin

from .models import Booking, BookingItem


class BookingItemInline(admin.TabularInline):
    model = BookingItem
    extra = 0
    can_delete = False
    readonly_fields = ("service", "service_name", "unit_price", "duration_minutes", "position")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("public_id", "customer", "staff", "start", "status", "total_price")
    list_filter = ("status", "staff")
    search_fields = ("public_id", "customer__username", "customer__email", "customer__first_name")
    date_hierarchy = "start"
    readonly_fields = ("public_id", "total_price", "total_minutes", "created_at", "updated_at", "cancelled_at")
    inlines = [BookingItemInline]
